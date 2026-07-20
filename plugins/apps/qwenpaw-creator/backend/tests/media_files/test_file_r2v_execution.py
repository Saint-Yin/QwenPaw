# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=missing-kwoa,protected-access,too-many-statements
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import threading

import pytest

from domain.enums import SpecialistRunStatus, TaskStatus
from services.media_files import r2v_execution
from services.media_files.image_execution import FileImageExecutionService
from services.media_files.r2v_execution import (
    FileR2VExecutionService,
    recover_interrupted_image_tasks,
)
from services.project_files.assets import AssetFileStore
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    ArtifactSlot,
    ArtifactVersion,
    EntityCollection,
    IndexedFile,
    Production,
    Project,
    R2VProduction,
    Section,
    Shot,
    Story,
    Unit,
)
from services.runtime_files.execution_store import ProjectExecutionStore
from services.runtime_files.execution_models import TaskAttemptStatus
from services.runtime_files.errors import RecordNotFoundError
from services.runtime_files.models import ChangeOrigin, ReviewPolicy
from utils.paths import unique_task_work_path


pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"storyboard" * 32
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"file-native-r2v" * 64


@pytest.fixture(autouse=True)
def _creator_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))


class FakeR2VProvider:
    def __init__(
        self,
        output_path: Path,
        *,
        poll_hook: Callable[[], Awaitable[None] | None] | None = None,
        block_first_poll: bool = False,
        duration_seconds: float = 4,
    ) -> None:
        self.output_path = output_path
        self.poll_hook = poll_hook
        self.block_first_poll = block_first_poll
        self.duration_seconds = duration_seconds
        self.poll_entered = asyncio.Event()
        self.submit_calls: list[dict] = []
        self.poll_calls: list[str] = []

    async def submit(self, **kwargs) -> str:
        self.submit_calls.append(kwargs)
        return "provider-r2v-task-1"

    async def poll(self, provider_task_id: str):
        self.poll_calls.append(provider_task_id)
        self.poll_entered.set()
        if self.block_first_poll:
            self.block_first_poll = False
            await asyncio.Event().wait()
        if self.poll_hook is not None:
            outcome = self.poll_hook()
            if outcome is not None:
                await outcome
        scoped_output = unique_task_work_path(
            "video",
            ".mp4",
            prefix="provider-",
        )
        scoped_output.write_bytes(_MP4)
        return {
            "task_id": provider_task_id,
            "status": "SUCCEEDED",
            "result_url": scoped_output.resolve().as_uri(),
            "media_type": "video/mp4",
            "durationSeconds": self.duration_seconds,
        }


class RemoteURLR2VProvider:
    def __init__(self) -> None:
        self.submit_calls = 0
        self.poll_calls = 0

    async def submit(self, **_kwargs) -> str:
        self.submit_calls += 1
        return "provider-remote-r2v-task-1"

    async def poll(self, provider_task_id: str):
        self.poll_calls += 1
        return {
            "task_id": provider_task_id,
            "status": "SUCCEEDED",
            "result_url": "https://video.example.test/result.mp4",
            "media_type": "video/mp4",
            "durationSeconds": 4,
        }


class BlockingImageProvider:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        self.entered.set()
        await asyncio.Event().wait()


def _services(tmp_path: Path) -> CreatorFileServices:
    services = CreatorFileServices.create(tmp_path.resolve())
    shot = Shot(
        shot_id="shot-1",
        description="雨夜街道中的角色",
        camera="⊙ 静止",
        framing="全景",
        duration_seconds=4,
    )
    unit = Unit(
        unit_id="unit-1",
        title="开场",
        route="r2v",
        duration_seconds=4,
        narrative="角色走入雨夜街道",
        shots=EntityCollection(
            items={shot.shot_id: shot},
            order=[shot.shot_id],
        ),
    )
    section = Section(
        section_id="section-1",
        title="第一幕",
        units=EntityCollection(
            items={unit.unit_id: unit},
            order=[unit.unit_id],
        ),
    )
    project = Project.new(project_id="project-1", name="File R2V")
    project.story = Story(
        sections=EntityCollection(
            items={section.section_id: section},
            order=[section.section_id],
        ),
    )
    project.production = Production(
        units_by_id={
            unit.unit_id: R2VProduction(
                storyboard_prompt="电影分镜，雨夜街道",
                video_prompt="主角从雨夜街道缓慢走向镜头",
            ),
        },
    )
    services.projects.create(project)
    _install_storyboard(services)
    return services


def _install_storyboard(services: CreatorFileServices) -> None:
    project_root = services.projects.project_root("project-1")
    checksum = hashlib.sha256(_PNG).hexdigest()
    indexed = IndexedFile(
        file_id="storyboard-file-1",
        kind="artifact_payload",
        relative_uri="assets/artifacts/storyboard-file-1.png",
        sha256=checksum,
        size_bytes=len(_PNG),
        media_type="image/png",
        created_at=datetime.now(UTC),
    )
    staged = AssetFileStore(project_root).stage_bytes(
        _PNG,
        staging_id="seed-storyboard",
    )
    AssetFileStore(project_root).publish(
        staged,
        indexed.relative_uri,
        expected_sha256=checksum,
        expected_size_bytes=len(_PNG),
    )
    artifact = ArtifactVersion(
        version_id="storyboard-version-1",
        slot_id="unit:unit-1:storyboard",
        kind="r2v_storyboard_image",
        owner_ref="unit:unit-1",
        name="开场分镜",
        file_id=indexed.file_id,
        checksum=checksum,
        based_on_generation=0,
        created_at=datetime.now(UTC),
    )
    slot = ArtifactSlot(
        slot_id=artifact.slot_id,
        kind=artifact.kind,
        owner_ref=artifact.owner_ref,
        version_ids=[artifact.version_id],
        selected_version_id=artifact.version_id,
    )
    base = services.projects.read("project-1")
    candidate = base.project.model_dump(mode="json")
    candidate["assets"]["files_by_id"][indexed.file_id] = indexed.model_dump(
        mode="json",
    )
    candidate["assets"]["artifact_versions_by_id"][
        artifact.version_id
    ] = artifact.model_dump(mode="json")
    candidate["assets"]["artifact_slots_by_id"][
        slot.slot_id
    ] = slot.model_dump(
        mode="json",
    )
    candidate["production"]["units_by_id"]["unit-1"][
        "selected_storyboard_artifact_version_id"
    ] = artifact.version_id
    services.commits.commit(
        base=base,
        candidate=candidate,
        origin=ChangeOrigin.FRONTEND_EDIT,
        review_policy=ReviewPolicy.AUTO_FIX,
        caused_by_request_id="seed-storyboard",
        round_id="round-seed-storyboard",
        transaction_id="transaction-seed-storyboard",
        advance_accepted_baseline=True,
    )


def _video(tmp_path: Path) -> Path:
    path = tmp_path / "provider-output.mp4"
    path.write_bytes(_MP4)
    return path


async def _seed_materialized_descriptor(
    worker: FileR2VExecutionService,
    *,
    idempotency_key: str,
    publish_asset: bool,
    claim_expires_at: float,
):
    dispatch = await worker.dispatch(
        project_id="project-1",
        target_ref="unit:unit-1",
        arguments={},
        idempotency_key=idempotency_key,
        start=False,
    )
    stable = r2v_execution._ids("project-1", idempotency_key)  # noqa: SLF001
    project_root = worker.services.projects.project_root("project-1")
    scratch = project_root / "runtime" / "task-work" / dispatch.task_id
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / "dead-owner-materialized.mp4"
    source.write_bytes(_MP4)

    def provider_succeeded(current):
        dumped = current.model_dump(mode="python")
        dumped.update(
            {
                "phase": "PROVIDER_SUCCEEDED",
                "provider_task_id": "provider-dead-owner",
                "provider_result": {
                    "status": "SUCCEEDED",
                    "result_url": source.as_uri(),
                    "media_type": "video/mp4",
                    "durationSeconds": 4,
                },
            },
        )
        return dumped

    seeded = worker._update_state_sync(  # noqa: SLF001
        "project-1",
        dispatch.task_id,
        provider_succeeded,
    )
    task = worker.executions.get_task("project-1", dispatch.task_id)
    materialized = r2v_execution.MaterializedVideo(
        path=source,
        sha256=hashlib.sha256(_MP4).hexdigest(),
        size_bytes=len(_MP4),
        media_type="video/mp4",
        container="mp4",
        source_kind="local",
    )
    (
        indexed,
        published,
    ) = worker._build_materialized_publication(  # noqa: SLF001
        task,
        seeded,
        stable=stable,
        materialized=materialized,
        actual_duration=4,
    )
    if publish_asset:
        file_store = AssetFileStore(project_root)
        with source.open("rb") as stream:
            staged = file_store.stage_stream(
                stream,
                staging_id=dispatch.task_id[:80],
            )
        file_store.publish(
            staged,
            indexed.relative_uri,
            expected_sha256=indexed.sha256,
            expected_size_bytes=indexed.size_bytes,
        )

    def descriptor(current):
        dumped = current.model_dump(mode="python")
        dumped.update(
            {
                "materialize_owner": "dead-owner",
                "materialize_claim_token": "dead-token",
                "materialize_claimed_at_epoch": worker.clock(),
                "materialize_claim_expires_at_epoch": claim_expires_at,
                "materialized_result": {
                    "path": str(source),
                    "sha256": indexed.sha256,
                    "sizeBytes": indexed.size_bytes,
                    "mediaType": indexed.media_type,
                    "container": "mp4",
                    "publishedResult": published,
                },
            },
        )
        return dumped

    worker._update_state_sync(  # noqa: SLF001
        "project-1",
        dispatch.task_id,
        descriptor,
    )
    return dispatch, source, indexed, published


def test_r2v_dispatch_submits_polls_and_commits_exact_project_versions(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            poll_lease_seconds=0.1,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="r2v-command-1",
        )
        response = dispatch.command_response("client-r2v-1")
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        replay = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="r2v-command-1",
        )
        await worker.shutdown()
        return dispatch, response, task, replay

    dispatch, response, task, replay = asyncio.run(scenario())
    assert response["status"] == "QUEUED"
    assert task.status is TaskStatus.SUCCEEDED
    assert replay.task_id == dispatch.task_id
    assert replay.replayed is True
    assert len(provider.submit_calls) == 1
    assert provider.submit_calls[0]["reference_image_urls"] == (
        (
            services.projects.project_root("project-1")
            / "assets"
            / "artifacts"
            / "storyboard-file-1.png"
        )
        .resolve()
        .as_uri(),
    )
    assert provider.poll_calls

    runtime = ProjectExecutionStore(services.root)
    attempts = runtime.list_attempts("project-1", task.task_id)
    assert [attempt.status.value for attempt in attempts] == [
        "RUNNING",
        "SUCCEEDED",
    ]
    assert attempts[-1].provider_task_id == "provider-r2v-task-1"
    assert (
        runtime.get_run("project-1", dispatch.run_id).status
        is SpecialistRunStatus.SUCCEEDED
    )
    project = services.projects.read("project-1").project
    selected = project.production.units_by_id[
        "unit-1"
    ].selected_video_artifact_version_id
    assert selected is not None
    version = project.assets.artifact_versions_by_id[selected]
    assert version.kind == "unit_video"
    assert version.provenance_refs == ["artifact-version:storyboard-version-1"]
    assert (
        project.assets.artifact_slots_by_id[
            "unit:unit-1:video"
        ].selected_version_id
        == selected
    )
    assert (
        AssetFileStore(services.projects.project_root("project-1"))
        .inspect(
            project.assets.files_by_id[version.file_id],
        )
        .available
    )
    assert (
        services.projects.project_root("project-1")
        / "runtime"
        / "tasks"
        / task.task_id
        / "r2v-state.json"
    ).is_file()


def test_r2v_remote_provider_has_task_scratch_before_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = RemoteURLR2VProvider()

    async def materialize_remote(
        output,
        *,
        project_root,
        project_id,
        task_id,
        **_kwargs,
    ):
        assert output["result_url"] == "https://video.example.test/result.mp4"
        assert project_id == "project-1"
        scratch = project_root / "runtime" / "task-work" / task_id
        assert scratch.is_dir()
        path = scratch / "remote-provider-result.mp4"
        path.write_bytes(_MP4)
        return r2v_execution.MaterializedVideo(
            path=path,
            sha256=hashlib.sha256(_MP4).hexdigest(),
            size_bytes=len(_MP4),
            media_type="video/mp4",
            container="mp4",
            source_kind="remote",
        )

    monkeypatch.setattr(
        r2v_execution,
        "materialize_r2v_video",
        materialize_remote,
    )

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="remote-provider-r2v",
        )
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return dispatch, task

    dispatch, task = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert provider.submit_calls == 1
    assert provider.poll_calls >= 1
    assert (
        services.projects.project_root("project-1")
        / "runtime"
        / "task-work"
        / dispatch.task_id
    ).is_dir()


def test_r2v_replay_recreates_missing_active_task_scratch(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = RemoteURLR2VProvider()

    async def scenario():
        worker = FileR2VExecutionService(services, provider=provider)
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="recover-missing-r2v-scratch",
            start=False,
        )
        scratch = (
            services.projects.project_root("project-1")
            / "runtime"
            / "task-work"
            / dispatch.task_id
        )
        assert scratch.is_dir()
        scratch.rmdir()
        replay = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="recover-missing-r2v-scratch",
            start=False,
        )
        await worker.shutdown()
        return dispatch, replay, scratch

    dispatch, replay, scratch = asyncio.run(scenario())
    assert replay.task_id == dispatch.task_id
    assert replay.replayed is True
    assert scratch.is_dir()
    assert provider.submit_calls == 0


def test_r2v_restart_recovers_provider_task_without_duplicate_submit(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path), block_first_poll=True)

    async def scenario():
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            poll_lease_seconds=0.03,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="restart-r2v-1",
        )
        await asyncio.wait_for(provider.poll_entered.wait(), timeout=2)
        await first.shutdown()
        await asyncio.sleep(0.04)
        recovered = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            poll_lease_seconds=0.03,
        )
        assert await recovered.recover_all() == 1
        task = await recovered.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await recovered.shutdown()
        return task

    task = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert len(provider.submit_calls) == 1
    assert len(provider.poll_calls) >= 2


def test_r2v_project_change_quarantines_published_unindexed_output(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)

    async def mutate_project() -> None:
        base = services.projects.read("project-1")
        candidate = base.project.model_dump(mode="json")
        candidate["strategy"]["creative_brief"] = "concurrent edit"
        services.commits.commit(
            base=base,
            candidate=candidate,
            origin=ChangeOrigin.FRONTEND_EDIT,
            review_policy=ReviewPolicy.AUTO_FIX,
            caused_by_request_id="concurrent-r2v-edit",
            round_id="round-concurrent-r2v-edit",
            transaction_id="transaction-concurrent-r2v-edit",
        )

    provider = FakeR2VProvider(_video(tmp_path), poll_hook=mutate_project)

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="stale-r2v-1",
        )
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return task

    task = asyncio.run(scenario())
    assert task.status is TaskStatus.QUARANTINED
    runtime = ProjectExecutionStore(services.root)
    assert (
        runtime.get_quarantine_record(
            "project-1",
            task.task_id,
        ).reason
        == "PROJECT_INPUT_SNAPSHOT_STALE"
    )
    assert (
        runtime.get_run("project-1", task.run_id).status
        is SpecialistRunStatus.STALE
    )
    project = services.projects.read("project-1").project
    assert (
        project.production.units_by_id[
            "unit-1"
        ].selected_video_artifact_version_id
        is None
    )
    assert all(
        item.kind != "unit_video"
        for item in project.assets.artifact_versions_by_id.values()
    )
    assert any(
        path.suffix == ".mp4"
        for path in (
            services.projects.project_root("project-1")
            / "assets"
            / "artifacts"
        ).iterdir()
    )


def test_r2v_cancel_during_success_quarantines_late_output(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    runtime = ProjectExecutionStore(services.root)

    async def cancel_task() -> None:
        task = next(
            item
            for item in runtime.list_tasks("project-1")
            if item.kind.value == "r2v_generation"
        )
        runtime.transition_task(
            "project-1",
            task.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "TEST_CANCELLED"}},
        )

    provider = FakeR2VProvider(_video(tmp_path), poll_hook=cancel_task)

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="cancel-r2v-1",
        )
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return task

    task = asyncio.run(scenario())
    assert task.status is TaskStatus.CANCELLED
    assert (
        runtime.get_quarantine_record(
            "project-1",
            task.task_id,
        ).reason
        == "TASK_CANCELLED_BEFORE_IMPORT"
    )
    assert (
        runtime.get_run("project-1", task.run_id).status
        is SpecialistRunStatus.CANCELLED
    )
    assert (
        services.projects.read("project-1")
        .project.production.units_by_id["unit-1"]
        .selected_video_artifact_version_id
        is None
    )


def test_r2v_duplicate_supervisors_share_submit_and_materialize_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))
    original_materialize = r2v_execution.materialize_r2v_video
    materialize_calls = 0

    async def delayed_materialize(*args, **kwargs):
        nonlocal materialize_calls
        materialize_calls += 1
        await asyncio.sleep(0.05)
        return await original_materialize(*args, **kwargs)

    monkeypatch.setattr(
        r2v_execution,
        "materialize_r2v_video",
        delayed_materialize,
    )

    async def scenario():
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="duplicate-r2v-1",
            start=False,
        )
        second = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        first.start_task("project-1", dispatch.task_id)
        second.start_task("project-1", dispatch.task_id)
        task = await first.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await first.shutdown()
        await second.shutdown()
        return task

    task = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert len(provider.submit_calls) == 1
    assert materialize_calls == 1


def test_r2v_materialize_heartbeat_covers_stage_publish_and_state_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))
    original_stage = r2v_execution._stage_materialized_video  # noqa: SLF001
    entered = threading.Event()
    release = threading.Event()
    stage_calls = 0
    call_lock = threading.Lock()

    def blocking_stage(*args, **kwargs):
        nonlocal stage_calls
        with call_lock:
            stage_calls += 1
            current = stage_calls
        if current == 1:
            entered.set()
            assert release.wait(timeout=3)
        return original_stage(*args, **kwargs)

    monkeypatch.setattr(
        r2v_execution,
        "_stage_materialized_video",
        blocking_stage,
    )

    async def scenario():
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="materialize-full-critical-section",
        )
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.sleep(0.2)
        second = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        second.start_task("project-1", dispatch.task_id)
        await asyncio.sleep(0.08)
        assert stage_calls == 1
        release.set()
        task = await first.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        state = first._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        await first._fail(  # noqa: SLF001 - stale worker regression
            task,
            code="STALE_WORKER_MUST_NOT_OVERWRITE",
            message="stale worker",
        )
        state_after_stale_fail = first._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        await first.shutdown()
        await second.shutdown()
        return dispatch, task, state, state_after_stale_fail

    dispatch, task, state, state_after_stale_fail = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert state.phase == "SUCCEEDED"
    assert state_after_stale_fail.phase == "SUCCEEDED"
    assert stage_calls == 1
    scratch = (
        services.projects.project_root("project-1")
        / "runtime"
        / "task-work"
        / dispatch.task_id
    )
    assert list(scratch.glob("r2v-materialized-*")) == []
    assert (
        list(
            (
                services.projects.project_root("project-1")
                / "assets"
                / ".staging"
            ).iterdir(),
        )
        == []
    )


def test_r2v_cancel_during_published_file_waits_for_owner_then_quarantines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))
    original_publish = AssetFileStore.publish
    entered = threading.Event()
    release = threading.Event()
    publish_calls = 0
    call_lock = threading.Lock()

    def publish_then_block(self, *args, **kwargs):
        nonlocal publish_calls
        result = original_publish(self, *args, **kwargs)
        with call_lock:
            publish_calls += 1
            current = publish_calls
        if current == 1:
            entered.set()
            assert release.wait(timeout=3)
        return result

    monkeypatch.setattr(AssetFileStore, "publish", publish_then_block)

    async def scenario():
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        second = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="cancel-after-asset-publish",
            start=False,
        )
        first.start_task("project-1", dispatch.task_id)
        second.start_task("project-1", dispatch.task_id)
        assert await asyncio.to_thread(entered.wait, 2)
        running = first.executions.get_task("project-1", dispatch.task_id)
        assert running.status is TaskStatus.RUNNING
        first.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED_DURING_PUBLISH"}},
        )
        await asyncio.sleep(0.08)
        deferred = first._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        assert deferred.phase == "PROVIDER_SUCCEEDED"
        assert deferred.materialize_claim_token is not None
        release.set()
        deadline = asyncio.get_running_loop().time() + 3
        while True:
            state = first._read_state_sync(  # noqa: SLF001
                "project-1",
                dispatch.task_id,
            )
            if state.phase == "QUARANTINED":
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("R2V cancellation did not reach quarantine")
            await asyncio.sleep(0.01)
        task = first.executions.get_task("project-1", dispatch.task_id)
        quarantine = first.executions.get_quarantine_record(
            "project-1",
            dispatch.task_id,
        )
        run = first.executions.get_run("project-1", dispatch.run_id)
        await first.shutdown()
        await second.shutdown()
        return dispatch, task, state, quarantine, run

    dispatch, task, state, quarantine, run = asyncio.run(scenario())
    assert publish_calls == 1
    assert task.status is TaskStatus.CANCELLED
    assert run.status is SpecialistRunStatus.CANCELLED
    assert state.phase == "QUARANTINED"
    assert quarantine.reason == "TASK_CANCELLED_BEFORE_IMPORT"
    indexed = state.published_result["indexedFile"]
    assert (
        indexed["file_id"]
        not in services.projects.read(
            "project-1",
        ).project.assets.files_by_id
    )
    asset_path = (
        services.projects.project_root("project-1") / indexed["relative_uri"]
    )
    assert asset_path.is_file()
    scratch = (
        services.projects.project_root("project-1")
        / "runtime"
        / "task-work"
        / dispatch.task_id
    )
    assert list(scratch.glob("r2v-materialized-*")) == []


def test_r2v_invalid_duration_fails_before_materialization_without_scratch_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path), duration_seconds=-1)
    materialize_calls = 0
    original = r2v_execution.materialize_r2v_video

    async def counted(*args, **kwargs):
        nonlocal materialize_calls
        materialize_calls += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(r2v_execution, "materialize_r2v_video", counted)

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="invalid-provider-duration",
        )
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return dispatch, task

    dispatch, task = asyncio.run(scenario())
    assert task.status is TaskStatus.FAILED
    assert materialize_calls == 0
    scratch = (
        services.projects.project_root("project-1")
        / "runtime"
        / "task-work"
        / dispatch.task_id
    )
    assert list(scratch.glob("r2v-materialized-*")) == []


def test_r2v_submit_heartbeat_starts_before_attempt_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    async def scenario():
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            submit_timeout_seconds=0.1,
            submit_claim_seconds=0.15,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="submit-heartbeat-before-attempt",
            start=False,
        )
        original_append = first.executions.append_attempt

        def blocking_append(*args, **kwargs):
            result = original_append(*args, **kwargs)
            if kwargs.get("status") is TaskAttemptStatus.RUNNING:
                entered.set()
                assert release.wait(timeout=3)
            return result

        monkeypatch.setattr(
            first.executions,
            "append_attempt",
            blocking_append,
        )
        first.start_task("project-1", dispatch.task_id)
        assert await asyncio.to_thread(entered.wait, 2)
        await asyncio.sleep(0.2)
        second = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            submit_timeout_seconds=0.1,
            submit_claim_seconds=0.15,
        )
        second.start_task("project-1", dispatch.task_id)
        await asyncio.sleep(0.08)
        assert provider.submit_calls == []
        release.set()
        task = await first.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        state = first._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        await first.shutdown()
        await second.shutdown()
        return task, state

    task, state = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert len(provider.submit_calls) == 1
    assert state.provider_task_id == "provider-r2v-task-1"
    assert state.phase == "SUCCEEDED"


def test_r2v_expired_materialize_claim_can_be_taken_over(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="expired-materialize-takeover",
            start=False,
        )
        stable = r2v_execution._ids(  # noqa: SLF001
            "project-1",
            "expired-materialize-takeover",
        )
        worker.executions.append_attempt(
            "project-1",
            dispatch.task_id,
            event_id=stable["attempt_started_event_id"],
            attempt_id=stable["attempt_id"],
            status=TaskAttemptStatus.RUNNING,
            input=worker._read_state_sync(  # noqa: SLF001
                "project-1",
                dispatch.task_id,
            ).request,
        )
        run = worker.executions.get_run("project-1", dispatch.run_id)
        run = worker.executions.transition_run(
            "project-1",
            dispatch.run_id,
            expected_status=run.status,
            status=SpecialistRunStatus.RUNNING_MODEL,
        )
        worker.executions.transition_run(
            "project-1",
            dispatch.run_id,
            expected_status=run.status,
            status=SpecialistRunStatus.WAITING_RUNTIME,
        )
        scratch = (
            services.projects.project_root("project-1")
            / "runtime"
            / "task-work"
            / dispatch.task_id
        )
        scratch.mkdir(parents=True, exist_ok=True)
        source = scratch / "expired-owner-output.mp4"
        source.write_bytes(_MP4)

        def expired(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "PROVIDER_SUCCEEDED",
                    "provider_task_id": "provider-expired-owner",
                    "provider_result": {
                        "status": "SUCCEEDED",
                        "result_url": source.as_uri(),
                        "media_type": "video/mp4",
                        "durationSeconds": 4,
                    },
                    "materialize_owner": "dead-owner",
                    "materialize_claim_token": "dead-token",
                    "materialize_claimed_at_epoch": 1.0,
                    "materialize_claim_expires_at_epoch": 2.0,
                },
            )
            return dumped

        worker._update_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
            expired,
        )
        worker.start_task("project-1", dispatch.task_id)
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        state = worker._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        await worker.shutdown()
        return task, state

    task, state = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert state.phase == "SUCCEEDED"
    assert state.materialize_owner is None
    assert state.materialize_claim_token is None


def test_r2v_cancelled_task_adopts_asset_from_expired_materialize_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def unexpected_materialize(*_args, **_kwargs):
        raise AssertionError(
            "published descriptor recovery must not redownload",
        )

    monkeypatch.setattr(
        r2v_execution,
        "materialize_r2v_video",
        unexpected_materialize,
    )

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="cancelled-expired-published-descriptor",
            start=False,
        )
        stable = r2v_execution._ids(  # noqa: SLF001
            "project-1",
            "cancelled-expired-published-descriptor",
        )
        scratch = (
            services.projects.project_root("project-1")
            / "runtime"
            / "task-work"
            / dispatch.task_id
        )
        scratch.mkdir(parents=True, exist_ok=True)
        source = scratch / "dead-owner-materialized.mp4"
        source.write_bytes(_MP4)

        def provider_succeeded(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "PROVIDER_SUCCEEDED",
                    "provider_task_id": "provider-dead-owner",
                    "provider_result": {
                        "status": "SUCCEEDED",
                        "result_url": source.as_uri(),
                        "media_type": "video/mp4",
                        "durationSeconds": 4,
                    },
                },
            )
            return dumped

        seeded = worker._update_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
            provider_succeeded,
        )
        task = worker.executions.get_task("project-1", dispatch.task_id)
        materialized = r2v_execution.MaterializedVideo(
            path=source,
            sha256=hashlib.sha256(_MP4).hexdigest(),
            size_bytes=len(_MP4),
            media_type="video/mp4",
            container="mp4",
            source_kind="local",
        )
        (
            indexed,
            published,
        ) = worker._build_materialized_publication(  # noqa: SLF001
            task,
            seeded,
            stable=stable,
            materialized=materialized,
            actual_duration=4,
        )
        file_store = AssetFileStore(
            services.projects.project_root("project-1"),
        )
        with source.open("rb") as stream:
            staged = file_store.stage_stream(
                stream,
                staging_id=dispatch.task_id[:80],
            )
        file_store.publish(
            staged,
            indexed.relative_uri,
            expected_sha256=indexed.sha256,
            expected_size_bytes=indexed.size_bytes,
        )

        def dead_descriptor(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "materialize_owner": "dead-owner",
                    "materialize_claim_token": "dead-token",
                    "materialize_claimed_at_epoch": 1.0,
                    "materialize_claim_expires_at_epoch": 2.0,
                    "materialized_result": {
                        "path": str(source),
                        "sha256": indexed.sha256,
                        "sizeBytes": indexed.size_bytes,
                        "mediaType": indexed.media_type,
                        "container": "mp4",
                        "publishedResult": published,
                    },
                },
            )
            return dumped

        worker._update_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
            dead_descriptor,
        )
        worker.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED"}},
        )
        await worker.recover_all()
        state = worker._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        quarantine = worker.executions.get_quarantine_record(
            "project-1",
            dispatch.task_id,
        )
        await worker.shutdown()
        return state, quarantine, indexed

    state, quarantine, indexed = asyncio.run(scenario())
    assert state.phase == "QUARANTINED"
    assert quarantine.reason == "TASK_CANCELLED_BEFORE_IMPORT"
    assert (
        indexed.file_id
        not in services.projects.read(
            "project-1",
        ).project.assets.files_by_id
    )


def test_r2v_recovery_converges_terminal_state_and_terminal_task_both_ways(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        state_first = FileR2VExecutionService(services, provider=provider)
        failed_dispatch = await state_first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="terminal-state-first",
            start=False,
        )

        def failed_state(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "FAILED",
                    "last_error": {
                        "code": "FAULT_INJECTED_STATE_FAILED",
                        "message": "state persisted before Task",
                    },
                },
            )
            return dumped

        state_first._update_state_sync(  # noqa: SLF001
            "project-1",
            failed_dispatch.task_id,
            failed_state,
        )
        await state_first.recover_all()
        failed_task = await state_first.wait_for_task(
            "project-1",
            failed_dispatch.task_id,
            timeout_seconds=3,
        )
        await state_first.shutdown()

        task_first = FileR2VExecutionService(services, provider=provider)
        cancelled_dispatch = await task_first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="terminal-task-first",
            start=False,
        )
        task_first.executions.transition_task(
            "project-1",
            cancelled_dispatch.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "FAULT_INJECTED_CANCEL"}},
        )

        def stale_submit_state(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "SUBMIT_CLAIMED",
                    "submit_owner": "dead-owner",
                    "submit_claim_token": "dead-token",
                    "submit_claim_expires_at_epoch": 2.0,
                },
            )
            return dumped

        task_first._update_state_sync(  # noqa: SLF001
            "project-1",
            cancelled_dispatch.task_id,
            stale_submit_state,
        )
        await task_first.recover_all()
        cancelled_state = task_first._read_state_sync(  # noqa: SLF001
            "project-1",
            cancelled_dispatch.task_id,
        )
        cancelled_run = task_first.executions.get_run(
            "project-1",
            cancelled_dispatch.run_id,
        )
        await task_first.shutdown()
        return failed_task, cancelled_state, cancelled_run

    failed_task, cancelled_state, cancelled_run = asyncio.run(scenario())
    assert failed_task.status is TaskStatus.FAILED
    assert failed_task.error["code"] == "FAULT_INJECTED_STATE_FAILED"
    assert cancelled_state.phase == "CANCELLED"
    assert cancelled_state.submit_claim_token is None
    assert cancelled_run.status is SpecialistRunStatus.CANCELLED


def test_r2v_fail_terminalization_is_atomic_against_concurrent_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    async def scenario():
        worker = FileR2VExecutionService(services, provider=provider)
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="fail-vs-cancel-atomic",
            start=False,
        )
        stable = r2v_execution._ids(  # noqa: SLF001
            "project-1",
            "fail-vs-cancel-atomic",
        )
        state = worker._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        worker.executions.append_attempt(
            "project-1",
            dispatch.task_id,
            event_id=stable["attempt_started_event_id"],
            attempt_id=stable["attempt_id"],
            status=TaskAttemptStatus.RUNNING,
            input=state.request,
        )
        task = worker.executions.get_task("project-1", dispatch.task_id)
        original_append = worker.executions.append_attempt

        def blocking_failed_append(*args, **kwargs):
            if kwargs.get("status") is TaskAttemptStatus.FAILED:
                entered.set()
                assert release.wait(timeout=3)
            return original_append(*args, **kwargs)

        monkeypatch.setattr(
            worker.executions,
            "append_attempt",
            blocking_failed_append,
        )
        failing = asyncio.create_task(
            worker._fail(  # noqa: SLF001 - deterministic terminal race
                task,
                code="FAULT_INJECTED_FAILURE",
                message="failure raced cancellation",
            ),
        )
        assert await asyncio.to_thread(entered.wait, 2)
        cancelling = asyncio.create_task(
            asyncio.to_thread(
                worker.executions.transition_task,
                "project-1",
                dispatch.task_id,
                expected_status=TaskStatus.RUNNING,
                status=TaskStatus.CANCELLED,
                updates={"error": {"code": "CONCURRENT_CANCEL"}},
            ),
        )
        await asyncio.sleep(0.05)
        assert not cancelling.done()
        release.set()
        await failing
        await asyncio.gather(cancelling, return_exceptions=True)
        latest_task = worker.executions.get_task("project-1", dispatch.task_id)
        latest_state = worker._read_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
        )
        latest_run = worker.executions.get_run("project-1", dispatch.run_id)
        await worker.shutdown()
        return latest_task, latest_state, latest_run

    task, state, run = asyncio.run(scenario())
    assert task.status is TaskStatus.FAILED
    assert task.error["code"] == "FAULT_INJECTED_FAILURE"
    assert state.phase == "FAILED"
    assert state.last_error["code"] == "FAULT_INJECTED_FAILURE"
    assert run.status is SpecialistRunStatus.FAILED


def test_r2v_expired_submit_claim_without_provider_id_fails_closed(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="unsafe-submit-r2v-1",
            start=False,
        )

        def expire(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "SUBMIT_CLAIMED",
                    "submit_owner": "dead-process",
                    "submit_claimed_at_epoch": 1.0,
                    "submit_claim_expires_at_epoch": 2.0,
                },
            )
            return dumped

        worker._update_state_sync(  # noqa: SLF001 - explicit crash fixture
            "project-1",
            dispatch.task_id,
            expire,
        )
        assert await worker.recover_all() == 1
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return task

    task = asyncio.run(scenario())
    assert task.status is TaskStatus.FAILED
    assert task.error["code"] == "R2V_PROVIDER_SUBMISSION_UNRECOVERABLE"
    assert provider.submit_calls == []


def test_r2v_admission_recovers_run_without_task_or_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(services, provider=provider)
        original = worker.executions.create_task

        def crash_after_run(*_args, **_kwargs):
            raise RuntimeError("fault after Run")

        monkeypatch.setattr(worker.executions, "create_task", crash_after_run)
        with pytest.raises(RuntimeError, match="fault after Run"):
            await worker.dispatch(
                project_id="project-1",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="admission-run-only",
                start=False,
            )
        monkeypatch.setattr(worker.executions, "create_task", original)
        replay = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="admission-run-only",
            start=False,
        )
        task = worker.executions.get_task("project-1", replay.task_id)
        state = worker._read_state_sync(
            "project-1",
            replay.task_id,
        )  # noqa: SLF001
        await worker.shutdown()
        return replay, task, state

    replay, task, state = asyncio.run(scenario())
    assert replay.replayed is True
    assert task.status is TaskStatus.QUEUED
    assert state.phase == "ADMITTED"
    assert provider.submit_calls == []


def test_r2v_admission_recovers_run_and_task_without_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(services, provider=provider)
        original = worker._create_or_validate_state_sync  # noqa: SLF001

        def crash_after_task(*_args, **_kwargs):
            raise RuntimeError("fault after Task")

        monkeypatch.setattr(
            worker,
            "_create_or_validate_state_sync",
            crash_after_task,
        )
        with pytest.raises(RuntimeError, match="fault after Task"):
            await worker.dispatch(
                project_id="project-1",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="admission-task-only",
                start=False,
            )
        monkeypatch.setattr(worker, "_create_or_validate_state_sync", original)
        replay = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="admission-task-only",
            start=False,
        )
        task = worker.executions.get_task("project-1", replay.task_id)
        state = worker._read_state_sync(
            "project-1",
            replay.task_id,
        )  # noqa: SLF001
        await worker.shutdown()
        return replay, task, state

    replay, task, state = asyncio.run(scenario())
    assert replay.replayed is True
    assert task.status is TaskStatus.QUEUED
    assert state.phase == "ADMITTED"
    assert provider.submit_calls == []


def test_image_restart_recovery_never_resubmits_one_shot_provider(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = BlockingImageProvider()

    async def scenario():
        worker = FileImageExecutionService(services, provider=provider)
        execution = asyncio.create_task(
            worker.execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="interrupted-image-1",
            ),
        )
        await asyncio.wait_for(provider.entered.wait(), timeout=2)
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
        assert await recover_interrupted_image_tasks(services) == 1

    asyncio.run(scenario())
    runtime = ProjectExecutionStore(services.root)
    image_task = next(
        item
        for item in runtime.list_tasks("project-1")
        if item.kind.value == "image_generation"
    )
    assert image_task.status is TaskStatus.FAILED
    assert provider.calls == 1


def test_r2v_terminal_reaper_waits_for_live_materialize_lease_then_quarantines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)

    async def unexpected_materialize(*_args, **_kwargs):
        raise AssertionError(
            "cancelled descriptor recovery must not redownload",
        )

    monkeypatch.setattr(
        r2v_execution,
        "materialize_r2v_video",
        unexpected_materialize,
    )

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=FakeR2VProvider(_video(tmp_path)),
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        (
            dispatch,
            _source,
            indexed,
            _published,
        ) = await _seed_materialized_descriptor(
            worker,
            idempotency_key="terminal-live-materialize-reaper",
            publish_asset=True,
            claim_expires_at=worker.clock() + 0.12,
        )
        worker.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED"}},
        )
        await worker.recover_all()
        deferred = worker._read_state_sync(
            "project-1",
            dispatch.task_id,
        )  # noqa: SLF001
        assert deferred.phase == "PROVIDER_SUCCEEDED"
        deadline = asyncio.get_running_loop().time() + 2
        while True:
            state = worker._read_state_sync(
                "project-1",
                dispatch.task_id,
            )  # noqa: SLF001
            if state.phase == "QUARANTINED":
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    "terminal materialize reaper did not converge",
                )
            await asyncio.sleep(0.01)
        quarantine = worker.executions.get_quarantine_record(
            "project-1",
            dispatch.task_id,
        )
        await worker.shutdown()
        return state, quarantine, indexed

    state, quarantine, indexed = asyncio.run(scenario())
    assert state.phase == "QUARANTINED"
    assert quarantine.reason == "TASK_CANCELLED_BEFORE_IMPORT"
    assert (
        indexed.file_id
        not in services.projects.read(
            "project-1",
        ).project.assets.files_by_id
    )


def test_r2v_cancel_during_live_submit_preserves_and_binds_provider_id(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)

    class BlockingSubmitProvider(FakeR2VProvider):
        def __init__(self, output_path: Path) -> None:
            super().__init__(output_path)
            self.submit_entered = asyncio.Event()
            self.submit_release = asyncio.Event()

        async def submit(self, **kwargs) -> str:
            self.submit_calls.append(kwargs)
            self.submit_entered.set()
            await self.submit_release.wait()
            return "paid-provider-task-id"

    async def scenario():
        provider = BlockingSubmitProvider(_video(tmp_path))
        first = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            submit_timeout_seconds=0.5,
            submit_claim_seconds=0.7,
        )
        second = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
            submit_timeout_seconds=0.5,
            submit_claim_seconds=0.7,
        )
        dispatch = await first.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="cancel-during-live-submit",
            start=False,
        )
        first.start_task("project-1", dispatch.task_id)
        await asyncio.wait_for(provider.submit_entered.wait(), timeout=1)
        first.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED"}},
        )
        await second.recover_all()
        protected = second._read_state_sync(
            "project-1",
            dispatch.task_id,
        )  # noqa: SLF001
        assert protected.phase == "SUBMIT_CLAIMED"
        assert protected.submit_claim_token is not None
        provider.submit_release.set()
        deadline = asyncio.get_running_loop().time() + 2
        while True:
            state = first._read_state_sync(
                "project-1",
                dispatch.task_id,
            )  # noqa: SLF001
            if state.phase == "CANCELLED" and state.provider_task_id:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("cancelled submit did not bind provider id")
            await asyncio.sleep(0.01)
        await first.shutdown()
        await second.shutdown()
        return provider, state

    provider, state = asyncio.run(scenario())
    assert len(provider.submit_calls) == 1
    assert state.provider_task_id == "paid-provider-task-id"
    assert state.submit_claim_token is None


def test_r2v_cancelled_missing_descriptor_output_never_redownloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)

    async def unexpected_materialize(*_args, **_kwargs):
        raise AssertionError("cancelled missing output must not redownload")

    monkeypatch.setattr(
        r2v_execution,
        "materialize_r2v_video",
        unexpected_materialize,
    )

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=FakeR2VProvider(_video(tmp_path)),
            materialize_timeout_seconds=0.1,
            materialize_claim_seconds=0.15,
        )
        (
            dispatch,
            source,
            _indexed,
            _published,
        ) = await _seed_materialized_descriptor(
            worker,
            idempotency_key="cancelled-missing-late-output",
            publish_asset=False,
            claim_expires_at=2.0,
        )
        source.unlink()
        worker.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED"}},
        )
        await worker.recover_all()
        state = worker._read_state_sync(
            "project-1",
            dispatch.task_id,
        )  # noqa: SLF001
        await worker.shutdown()
        return state

    state = asyncio.run(scenario())
    assert state.phase == "CANCELLED"
    assert state.last_error["code"] == "R2V_CANCELLED_LATE_OUTPUT_MISSING"


def test_r2v_active_recovery_reuses_verified_descriptor_scratch_before_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    calls: list[dict] = []
    original = r2v_execution.materialize_r2v_video

    async def counted(output, **kwargs):
        calls.append(dict(output))
        return await original(output, **kwargs)

    monkeypatch.setattr(r2v_execution, "materialize_r2v_video", counted)

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=FakeR2VProvider(_video(tmp_path)),
            poll_interval_seconds=0.01,
            materialize_timeout_seconds=0.2,
            materialize_claim_seconds=0.3,
        )
        (
            dispatch,
            source,
            _indexed,
            _published,
        ) = await _seed_materialized_descriptor(
            worker,
            idempotency_key="active-descriptor-scratch-reuse",
            publish_asset=False,
            claim_expires_at=2.0,
        )

        def stale_provider_url(current):
            dumped = current.model_dump(mode="python")
            provider_result = dict(current.provider_result or {})
            provider_result["result_url"] = (
                source.parent / "gone.mp4"
            ).as_uri()
            dumped["provider_result"] = provider_result
            return dumped

        worker._update_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
            stale_provider_url,
        )
        worker.start_task("project-1", dispatch.task_id)
        task = await worker.wait_for_task(
            "project-1",
            dispatch.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return task, source

    task, source = asyncio.run(scenario())
    assert task.status is TaskStatus.SUCCEEDED
    assert len(calls) == 1
    assert calls[0]["path"] == str(source)


def test_r2v_terminal_quarantined_task_repairs_missing_quarantine_record(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=FakeR2VProvider(_video(tmp_path)),
        )
        (
            dispatch,
            _source,
            _indexed,
            published,
        ) = await _seed_materialized_descriptor(
            worker,
            idempotency_key="repair-quarantine-record",
            publish_asset=True,
            claim_expires_at=2.0,
        )
        stable = r2v_execution._ids(  # noqa: SLF001
            "project-1",
            "repair-quarantine-record",
        )
        state = worker._read_state_sync(
            "project-1",
            dispatch.task_id,
        )  # noqa: SLF001
        worker.executions.append_attempt(
            "project-1",
            dispatch.task_id,
            event_id=stable["attempt_started_event_id"],
            attempt_id=stable["attempt_id"],
            status=TaskAttemptStatus.RUNNING,
            input=state.request,
        )
        worker.executions.append_attempt(
            "project-1",
            dispatch.task_id,
            event_id=stable["attempt_quarantined_event_id"],
            attempt_id=stable["attempt_id"],
            status=TaskAttemptStatus.QUARANTINED,
            output=published,
            error={"code": "PROJECT_INPUT_SNAPSHOT_STALE"},
        )
        with pytest.raises(RecordNotFoundError):
            worker.executions.get_quarantine_record(
                "project-1",
                dispatch.task_id,
            )
        await worker.recover_all()
        record = worker.executions.get_quarantine_record(
            "project-1",
            dispatch.task_id,
        )
        await worker.shutdown()
        return record

    record = asyncio.run(scenario())
    assert record.reason == "PROJECT_INPUT_SNAPSHOT_STALE"


def test_r2v_terminal_reaper_waits_for_dead_submit_lease_without_resubmit(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        dispatch = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="dead-submit-terminal-reaper",
            start=False,
        )
        worker.executions.transition_task(
            "project-1",
            dispatch.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "USER_CANCELLED"}},
        )

        def live_dead_submit(current):
            dumped = current.model_dump(mode="python")
            dumped.update(
                {
                    "phase": "SUBMIT_CLAIMED",
                    "submit_owner": "dead-owner",
                    "submit_claim_token": "dead-token",
                    "submit_claim_expires_at_epoch": worker.clock() + 0.1,
                },
            )
            return dumped

        worker._update_state_sync(  # noqa: SLF001
            "project-1",
            dispatch.task_id,
            live_dead_submit,
        )
        await worker.recover_all()
        deferred = worker._read_state_sync(
            "project-1",
            dispatch.task_id,
        )  # noqa: SLF001
        assert deferred.phase == "SUBMIT_CLAIMED"
        deadline = asyncio.get_running_loop().time() + 2
        while True:
            state = worker._read_state_sync(
                "project-1",
                dispatch.task_id,
            )  # noqa: SLF001
            if state.phase == "CANCELLED":
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("terminal submit reaper did not converge")
            await asyncio.sleep(0.01)
        await worker.shutdown()
        return state

    state = asyncio.run(scenario())
    assert state.provider_task_id is None
    assert provider.submit_calls == []


def test_r2v_recover_all_isolates_one_terminal_task_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    provider = FakeR2VProvider(_video(tmp_path))

    async def scenario():
        worker = FileR2VExecutionService(
            services,
            provider=provider,
            poll_interval_seconds=0.01,
        )
        bad = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="isolated-terminal-recovery-failure",
            start=False,
        )
        worker.executions.transition_task(
            "project-1",
            bad.task_id,
            expected_status=TaskStatus.QUEUED,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "FAULT_INJECTED"}},
        )
        good = await worker.dispatch(
            project_id="project-1",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="recovery-continues-after-isolated-failure",
            start=False,
        )
        original = worker._align_state_to_terminal_task  # noqa: SLF001

        async def fail_one(task):
            if task.task_id == bad.task_id:
                raise RuntimeError("fault-injected terminal recovery")
            return await original(task)

        monkeypatch.setattr(worker, "_align_state_to_terminal_task", fail_one)
        recovered = await worker.recover_all()
        good_task = await worker.wait_for_task(
            "project-1",
            good.task_id,
            timeout_seconds=3,
        )
        await worker.shutdown()
        return recovered, good_task

    recovered, good_task = asyncio.run(scenario())
    assert recovered == 1
    assert good_task.status is TaskStatus.SUCCEEDED
