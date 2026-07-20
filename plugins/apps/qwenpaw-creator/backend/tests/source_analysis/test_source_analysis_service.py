# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=protected-access,use-implicit-booleaness-not-comparison
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
import pytest

from api.dependencies import project_file_services
from api.file_asset_routes import (
    _AssetInput,
    _ingest_many_sync,
    _register_remote_asset_sync,
)
from api.file_execution_routes import _cancel_task_sync
from api.file_source_intelligence_routes import router as source_router
from domain.enums import SpecialistRunStatus, TaskStatus
from domain.errors import StorageIntegrityError
from schemas.assets import SourceMediaMetadata, SourceModelRunRef
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    IndexedFile,
    Project,
    SourceAssetVersion,
)
from services.project_files.store import ProjectNotFound
from services.runtime_files.models import ChangeOrigin, ReviewPolicy
from services.source_analysis import (
    DefaultSourceMediaAnalyzer,
    SourceAnalyzerConfigurationError,
    SourceAnalyzerOutput,
    SourceMediaAnalysisInput,
    SourceMediaAnalysisService,
    clear_source_analysis_service_registry,
    recover_interrupted_source_analysis,
    shutdown_source_analysis_services,
    source_analysis_service,
)
from services.runtime_files.execution_models import TaskAttemptStatus


def _services_with_source(
    tmp_path: Path,
) -> tuple[CreatorFileServices, str, str]:
    services = CreatorFileServices.create(tmp_path.resolve())
    services.projects.create(Project.new(project_id="project-1", name="One"))
    result, _ = _ingest_many_sync(
        services,
        project_id="project-1",
        key="asset-1",
        inputs=[
            _AssetInput(
                name="source.mp4",
                content=b"verified-source-bytes",
                media_type="video/mp4",
            ),
        ],
        attach_source=True,
        scope="source-analysis-test",
    )
    item = result["items"][0]
    return services, item["assetId"], item["assetVersionId"]


def _output(evidence_ref: str) -> SourceAnalyzerOutput:
    coverage = {
        "visual": {
            "mode": "available",
            "producer": "model_native",
            "ratio": 1.0,
        },
        "asr": {"mode": "unavailable", "producer": None, "ratio": None},
        "ocr": {"mode": "unavailable", "producer": None, "ratio": None},
        "audio": {"mode": "unavailable", "producer": None, "ratio": None},
    }
    run = SourceModelRunRef(id="fake-run-1", provider="fake", model="fake-v1")
    return SourceAnalyzerOutput(
        raw={
            "summary": "海边日落与人物行走",
            "coverage": coverage,
            "shots": [
                {
                    "id": "shot-000001",
                    "startMs": 0,
                    "endMs": 5000,
                    "description": "人物在海边日落中行走",
                    "events": ["行走", "日落"],
                    "keyframeRef": evidence_ref,
                    "confidence": 0.9,
                    "modelRunId": run.id,
                    "evidenceFrameRefs": [evidence_ref],
                },
            ],
            "transcript": [],
            "words": [],
            "ocrSegments": [],
            "audioEvents": [],
            "entities": [],
            "semanticEntries": [
                {
                    "id": "semantic-000001",
                    "text": "海边 日落 人物 行走",
                    "tags": ["海边", "日落"],
                    "confidence": 0.9,
                    "modelRunId": run.id,
                    "evidenceFrameRefs": [evidence_ref],
                },
            ],
        },
        media=SourceMediaMetadata(
            mediaKind="video",
            mediaType="video/mp4",
            durationMs=5000,
            width=1920,
            height=1080,
        ),
        model_runs=(run,),
        coverage_policy=coverage,
        provenance_refs=(evidence_ref,),
    )


class FakeAnalyzer:
    def __init__(self) -> None:
        self.observed_bytes: bytes | None = None
        self.observed_path: Path | None = None

    async def analyze(
        self,
        request: SourceMediaAnalysisInput,
    ) -> SourceAnalyzerOutput:
        self.observed_bytes = request.local_path.read_bytes()
        self.observed_path = request.local_path
        return _output(request.evidence_ref)


class BlockingAnalyzer(FakeAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def analyze(
        self,
        request: SourceMediaAnalysisInput,
    ) -> SourceAnalyzerOutput:
        self.observed_bytes = request.local_path.read_bytes()
        self.observed_path = request.local_path
        self.started.set()
        await self.release.wait()
        return _output(request.evidence_ref)


class RemoteFakeAnalyzer:
    def __init__(self) -> None:
        self.observed_url: str | None = None
        self.observed_local_path: Path | None = None

    async def analyze(
        self,
        request: SourceMediaAnalysisInput,
    ) -> SourceAnalyzerOutput:
        self.observed_url = request.source_url
        self.observed_local_path = request.local_path
        return _output(request.evidence_ref)


def _dispatch(
    service: SourceMediaAnalysisService,
    asset_id: str,
    command_id: str,
):
    return service.dispatch(
        project_id="project-1",
        target_ref=f"asset:{asset_id}",
        command_id=command_id,
        start=False,
    )


def test_fake_provider_publishes_one_canonical_index_and_read_apis(
    tmp_path,
) -> None:
    services, asset_id, asset_version_id = _services_with_source(tmp_path)
    analyzer = FakeAnalyzer()
    service = SourceMediaAnalysisService(services, analyzer=analyzer)

    async def scenario():
        dispatch = await _dispatch(service, asset_id, "analyze-1")
        completed = await service.execute(dispatch.job)
        replay = await _dispatch(service, asset_id, "analyze-1")
        return dispatch, completed, replay

    dispatch, completed, replay = asyncio.run(scenario())
    assert completed.status is TaskStatus.SUCCEEDED
    assert replay.task.status is TaskStatus.SUCCEEDED
    assert replay.job.input_generation == dispatch.job.input_generation
    assert analyzer.observed_bytes == b"verified-source-bytes"
    assert analyzer.observed_path is not None
    assert not analyzer.observed_path.exists()

    snapshot = services.projects.read("project-1")
    source = next(iter(snapshot.project.sources.sources.items.values()))
    intelligence_id = source.current_intelligence_version_id
    assert snapshot.generation == 2
    assert intelligence_id == dispatch.job.intelligence_version_id
    intelligence = snapshot.project.assets.intelligence_versions_by_id[
        intelligence_id
    ]
    assert intelligence.source_asset_version_id == asset_version_id
    indexed = snapshot.project.assets.files_by_id[intelligence.file_id]
    assert indexed.kind == "source_intelligence"
    assert indexed.relative_uri.endswith(f"/{intelligence_id}.json")
    assert service.load("project-1", asset_id).summary == "海边日落与人物行走"
    query = service.query("project-1", asset_id, "日落")
    assert {item.kind for item in query.items} >= {
        "summary",
        "shot",
        "semantic",
    }

    app = FastAPI()
    app.include_router(source_router)
    app.dependency_overrides[project_file_services] = lambda: services

    async def read_api():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            current = await client.get(
                f"/projects/project-1/assets/{asset_id}/understanding",
            )
            exact = await client.get(
                f"/projects/project-1/assets/{asset_id}/understanding/{intelligence_id}",
            )
            queried = await client.get(
                f"/projects/project-1/assets/{asset_id}/source-index/query",
                params={"query": "日落"},
            )
        return current, exact, queried

    current, exact, queried = asyncio.run(read_api())
    assert (
        current.status_code == exact.status_code == queried.status_code == 200
    )
    assert current.json()["id"] == exact.json()["id"] == intelligence_id
    assert queried.json()["items"]


def test_url_backed_source_is_analyzed_before_runtime_cache_exists(
    tmp_path,
) -> None:
    services = CreatorFileServices.create(tmp_path.resolve())
    services.projects.create(Project.new(project_id="project-1", name="One"))
    item = _register_remote_asset_sync(
        services,
        project_id="project-1",
        key="remote-source",
        url="https://assets.example/source.mp4",
        requested_name="source.mp4",
        attach_source=True,
        scope="POST-assets",
    )
    analyzer = RemoteFakeAnalyzer()
    service = SourceMediaAnalysisService(services, analyzer=analyzer)

    async def scenario():
        dispatch = await _dispatch(service, item["assetId"], "analyze-remote")
        return dispatch, await service.execute(dispatch.job)

    dispatch, completed = asyncio.run(scenario())
    assert dispatch.job.indexed_file is None
    assert completed.status is TaskStatus.SUCCEEDED
    assert analyzer.observed_local_path is None
    assert analyzer.observed_url == "https://assets.example/source.mp4"
    project = services.projects.read("project-1").project
    assert (
        project.assets.source_versions_by_id[item["assetVersionId"]].file_id
        is None
    )
    source = next(iter(project.sources.sources.items.values()))
    assert source.current_intelligence_version_id is not None


def test_materialize_after_project_delete_does_not_recreate_project(
    tmp_path,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())
    dispatch = asyncio.run(_dispatch(service, asset_id, "deleted-before-copy"))
    project_root = services.projects.project_root("project-1")

    services.projects.delete("project-1")
    assert not project_root.exists()
    with pytest.raises(ProjectNotFound):
        service._materialize_verified_input_sync(dispatch.job)
    assert not project_root.exists()


def test_materialize_rejects_symlinked_source_temp_directory(tmp_path) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())
    dispatch = asyncio.run(_dispatch(service, asset_id, "symlinked-copy"))
    external = tmp_path / "outside"
    external.mkdir()
    temp_parent = (
        services.projects.project_root("project-1")
        / "runtime"
        / "temp"
        / "source-analysis"
    )
    temp_parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(StorageIntegrityError, match="symlink"):
        service._materialize_verified_input_sync(dispatch.job)
    assert list(external.iterdir()) == []


def test_changed_project_head_quarantines_late_provider_result(
    tmp_path,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    analyzer = BlockingAnalyzer()
    service = SourceMediaAnalysisService(services, analyzer=analyzer)

    async def scenario():
        dispatch = await _dispatch(service, asset_id, "analyze-stale")
        worker = asyncio.create_task(service.execute(dispatch.job))
        await analyzer.started.wait()
        base = services.projects.read("project-1")
        candidate = base.project.model_dump(mode="json")
        candidate["description"] = "user changed while provider was running"
        services.commits.commit(
            base=base,
            candidate=candidate,
            origin=ChangeOrigin.FRONTEND_EDIT,
            review_policy=ReviewPolicy.AUTO_FIX,
            caused_by_request_id="frontend-change",
            round_id="round-frontend-change",
            transaction_id="commit-frontend-change",
            advance_accepted_baseline=True,
        )
        analyzer.release.set()
        return dispatch, await worker

    dispatch, completed = asyncio.run(scenario())
    assert completed.status is TaskStatus.QUARANTINED
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.STALE
    )
    quarantine = service.executions.get_quarantine_record(
        "project-1",
        dispatch.job.task_id,
    )
    assert "generation/ETag" in quarantine.reason
    project = services.projects.read("project-1").project
    assert not project.assets.intelligence_versions_by_id
    assert (
        next(
            iter(project.sources.sources.items.values()),
        ).current_intelligence_version_id
        is None
    )


def test_cancelled_task_quarantines_provider_result_without_project_commit(
    tmp_path,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    analyzer = BlockingAnalyzer()
    service = SourceMediaAnalysisService(services, analyzer=analyzer)

    async def scenario():
        dispatch = await _dispatch(service, asset_id, "analyze-cancel")
        worker = asyncio.create_task(service.execute(dispatch.job))
        await analyzer.started.wait()
        await asyncio.to_thread(
            _cancel_task_sync,
            services,
            "project-1",
            dispatch.job.task_id,
            "stop",
        )
        analyzer.release.set()
        return dispatch, await worker

    dispatch, completed = asyncio.run(scenario())
    assert completed.status is TaskStatus.CANCELLED
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.CANCELLED
    )
    service.executions.get_quarantine_record("project-1", dispatch.job.task_id)
    project = services.projects.read("project-1").project
    assert project.generation == 1
    assert not project.assets.intelligence_versions_by_id


def test_default_provider_fails_explicitly_without_vlm_configuration(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not-probed-when-config-is-missing")
    version = SourceAssetVersion(
        version_id="version-1",
        logical_asset_id="asset-1",
        name="source.mp4",
        file_id="file-1",
        checksum="a" * 64,
        media_kind="video",
        media_type="video/mp4",
        created_at=datetime.now(UTC),
    )
    indexed = IndexedFile(
        file_id="file-1",
        kind="source_original",
        relative_uri="assets/sources/source.mp4",
        sha256="a" * 64,
        size_bytes=source.stat().st_size,
        media_type="video/mp4",
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "services.source_analysis.service.model_config.get_vlm_api_key",
        lambda: "",
    )
    with pytest.raises(
        SourceAnalyzerConfigurationError,
        match="creator_vlm_model",
    ):
        asyncio.run(
            DefaultSourceMediaAnalyzer().analyze(
                SourceMediaAnalysisInput(
                    project_id="project-1",
                    source_id="source-1",
                    logical_asset_id="asset-1",
                    source_version=version,
                    indexed_file=indexed,
                    local_path=source,
                    evidence_ref="asset://asset-1@version-1",
                ),
            ),
        )


def test_missing_media_tools_fail_task_and_run_once_without_retry(
    tmp_path,
    monkeypatch,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    monkeypatch.setattr(
        "services.source_analysis.service.model_config.get_vlm_api_key",
        lambda: "configured",
    )
    monkeypatch.setattr(
        "services.runtime_files.media_probe.resolve_ffprobe",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "services.runtime_files.media_probe.resolve_ffmpeg",
        lambda: None,
    )
    service = SourceMediaAnalysisService(
        services,
        analyzer=DefaultSourceMediaAnalyzer(),
    )

    async def scenario():
        dispatch = await _dispatch(service, asset_id, "missing-ffprobe")
        completed = await service.execute(dispatch.job)
        replay = await service.execute(dispatch.job)
        return dispatch, completed, replay

    dispatch, completed, replay = asyncio.run(scenario())
    assert completed.status is replay.status is TaskStatus.FAILED
    assert completed.error == {
        "code": "SOURCEANALYZERCONFIGURATIONERROR",
        "message": "视频处理工具 ffprobe/ffmpeg 未就绪，暂时无法完成该视频。",
        "retryable": False,
    }
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.FAILED
    )
    assert [
        attempt.status
        for attempt in service.executions.list_attempts(
            "project-1",
            dispatch.job.task_id,
        )
    ] == [TaskAttemptStatus.RUNNING, TaskAttemptStatus.FAILED]


def test_analyze_endpoint_dispatches_directly(
    tmp_path,
    monkeypatch,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    calls: list[dict[str, object]] = []

    class Dispatcher:
        async def dispatch(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                job=SimpleNamespace(
                    round_id="round-source",
                    input_generation=0,
                    input_etag="sha256:input",
                ),
                task=SimpleNamespace(
                    task_id="task-source",
                    status=TaskStatus.QUEUED,
                ),
                run=SimpleNamespace(run_id="run-source"),
            )

    monkeypatch.setattr(
        "api.file_source_intelligence_routes.source_analysis_service",
        lambda _services: Dispatcher(),
    )
    app = FastAPI()
    app.include_router(source_router)
    app.dependency_overrides[project_file_services] = lambda: services

    async def submit():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(
                f"/projects/project-1/assets/{asset_id}/analyze",
                headers={"Idempotency-Key": "analyze-command"},
                json={
                    "clientRequestId": "analyze-command",
                },
            )

    response = asyncio.run(submit())
    assert response.status_code == 202
    assert response.json() == {
        "taskId": "task-source",
        "runId": "run-source",
        "status": "QUEUED",
        "transactionId": "round-source",
        "inputGeneration": 0,
        "inputEtag": "sha256:input",
    }
    assert calls[0]["target_ref"] == f"asset:{asset_id}"


def test_source_admission_replay_repairs_run_created_before_task(
    tmp_path,
    monkeypatch,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())
    create_task = service.executions.create_task
    attempts = 0

    def fail_first_task_create(record):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated task write interruption")
        return create_task(record)

    monkeypatch.setattr(
        service.executions,
        "create_task",
        fail_first_task_create,
    )
    with pytest.raises(OSError, match="task write interruption"):
        asyncio.run(_dispatch(service, asset_id, "repair-orphan-run"))

    replay = asyncio.run(_dispatch(service, asset_id, "repair-orphan-run"))
    assert replay.run.run_id == replay.job.run_id
    assert replay.task.task_id == replay.job.task_id
    assert replay.task.run_id == replay.run.run_id
    assert attempts == 2


def test_startup_recovery_repairs_then_fails_closed_orphan_source_run(
    tmp_path,
    monkeypatch,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())
    create_task = service.executions.create_task

    def interrupted_task_create(_record):
        raise OSError("simulated admission interruption")

    monkeypatch.setattr(
        service.executions,
        "create_task",
        interrupted_task_create,
    )
    with pytest.raises(OSError, match="admission interruption"):
        asyncio.run(_dispatch(service, asset_id, "startup-repair-orphan-run"))
    monkeypatch.setattr(service.executions, "create_task", create_task)

    assert recover_interrupted_source_analysis(services) == 1
    replay = asyncio.run(
        _dispatch(service, asset_id, "startup-repair-orphan-run"),
    )
    assert replay.task.status is TaskStatus.FAILED
    assert replay.run.status is SpecialistRunStatus.FAILED
    assert replay.task.error["code"] == "SOURCE_ANALYSIS_PROCESS_RESTARTED"


def test_startup_recovery_converges_project_commit_before_task_completion(
    tmp_path,
    monkeypatch,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())
    complete_task = service._complete_task_sync

    def interrupted_completion(_job, _published):
        raise OSError("simulated completion write interruption")

    monkeypatch.setattr(service, "_complete_task_sync", interrupted_completion)
    dispatch = asyncio.run(_dispatch(service, asset_id, "recover-published"))
    with pytest.raises(OSError, match="completion write interruption"):
        asyncio.run(service.execute(dispatch.job))

    project = services.projects.read("project-1").project
    assert (
        next(
            iter(project.sources.sources.items.values()),
        ).current_intelligence_version_id
        == dispatch.job.intelligence_version_id
    )
    assert (
        service.executions.get_task(
            "project-1",
            dispatch.job.task_id,
        ).status
        is TaskStatus.RUNNING
    )
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.RUNNING_MODEL
    )

    monkeypatch.setattr(service, "_complete_task_sync", complete_task)
    assert recover_interrupted_source_analysis(services) == 1
    assert recover_interrupted_source_analysis(services) == 0
    assert (
        service.executions.get_task(
            "project-1",
            dispatch.job.task_id,
        ).status
        is TaskStatus.SUCCEEDED
    )
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.SUCCEEDED
    )


def test_startup_recovery_fails_closed_queued_and_running_source_tasks(
    tmp_path,
) -> None:
    services, asset_id, _ = _services_with_source(tmp_path)
    service = SourceMediaAnalysisService(services, analyzer=FakeAnalyzer())

    async def prepare():
        queued = await _dispatch(service, asset_id, "queued-before-restart")
        running = await _dispatch(service, asset_id, "running-before-restart")
        service.executions.transition_run(
            "project-1",
            running.job.run_id,
            expected_status=SpecialistRunStatus.QUEUED,
            status=SpecialistRunStatus.RUNNING_MODEL,
        )
        service.executions.append_attempt(
            "project-1",
            running.job.task_id,
            event_id=f"{running.job.attempt_id}-running",
            attempt_id=running.job.attempt_id,
            status=TaskAttemptStatus.RUNNING,
            input={
                "sourceAssetVersionId": running.job.source_version.version_id,
            },
        )
        return queued, running

    queued, running = asyncio.run(prepare())
    assert recover_interrupted_source_analysis(services) == 2
    assert recover_interrupted_source_analysis(services) == 0
    for dispatch in (queued, running):
        task = service.executions.get_task("project-1", dispatch.job.task_id)
        run = service.executions.get_run("project-1", dispatch.job.run_id)
        assert task.status is TaskStatus.FAILED
        assert task.error["code"] == "SOURCE_ANALYSIS_PROCESS_RESTARTED"
        assert run.status is SpecialistRunStatus.FAILED
    assert [
        item.status
        for item in service.executions.list_attempts(
            "project-1",
            running.job.task_id,
        )
    ] == [TaskAttemptStatus.RUNNING, TaskAttemptStatus.FAILED]


def test_shutdown_cancels_and_awaits_registered_source_workers(
    tmp_path,
) -> None:
    clear_source_analysis_service_registry()
    services, asset_id, _ = _services_with_source(tmp_path)
    analyzer = BlockingAnalyzer()

    async def scenario():
        service = source_analysis_service(services)
        service.analyzer = analyzer
        dispatch = await service.dispatch(
            project_id="project-1",
            target_ref=f"asset:{asset_id}",
            command_id="shutdown-running",
            start=True,
        )
        await analyzer.started.wait()
        await shutdown_source_analysis_services()
        return service, dispatch

    service, dispatch = asyncio.run(scenario())
    assert (
        service.executions.get_task(
            "project-1",
            dispatch.job.task_id,
        ).status
        is TaskStatus.CANCELLED
    )
    assert (
        service.executions.get_run(
            "project-1",
            dispatch.job.run_id,
        ).status
        is SpecialistRunStatus.CANCELLED
    )
