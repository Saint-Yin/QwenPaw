from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest

from domain.enums import CreatorCommandType, SpecialistRunStatus, TaskStatus
from domain.errors import ConflictError, StorageIntegrityError, ValidationError
from services.media_files.overlay import OverlayRenderResult
from services.media_files.local_execution import (
    FileLocalMediaExecutionService,
    FfmpegLocalMediaRunner,
    LocalMediaInput,
    LocalMediaExecutionSpec,
)
from services.project_files.assets import AssetFileStore
from services.project_files.facade import CreatorFileServices
from services.project_files.models import Project
from services.project_files.remote_cache import RemoteCacheEntry
from services.runtime_files.execution_store import ProjectExecutionStore
from services.runtime_files.atomic_store import AtomicJsonRecordStore
from services.runtime_files.models import ChangeOrigin, ReviewPolicy


pytestmark = pytest.mark.unit


class FakeLocalMediaRunner:
    def __init__(
        self,
        hook: Callable[[LocalMediaExecutionSpec], Awaitable[None] | None] | None = None,
    ) -> None:
        self.calls: list[LocalMediaExecutionSpec] = []
        self.hook = hook

    async def render(self, spec: LocalMediaExecutionSpec):
        self.calls.append(spec)
        if self.hook is not None:
            pending = self.hook(spec)
            if pending is not None:
                await pending
        spec.output_path.write_bytes(
            b"file-native-video:" + spec.command.value.encode("ascii")
        )
        return {
            "media_type": "video/mp4",
            "duration_seconds": spec.expected_duration_seconds,
            "metadata": {"provider": "fake"},
        }


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _indexed_file(file_id: str, uri: str, content: bytes) -> dict:
    return {
        "file_id": file_id,
        "kind": "source_original" if "source" in file_id else "artifact_payload",
        "relative_uri": uri,
        "sha256": _sha(content),
        "size_bytes": len(content),
        "media_type": "video/mp4",
        "created_at": "2026-07-15T08:00:00Z",
    }


def _services(
    tmp_path: Path,
    *,
    source_content: bytes = b"source-video",
    duplicate_source_clip: bool = False,
) -> CreatorFileServices:
    unit_content = b"unit-video"
    section_content = b"section-video"
    raw = Project.new(
        project_id="project-1",
        name="Local Media",
        scenario="video_edit",
        now=datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc),
    ).model_dump(mode="json")
    raw["assets"] = {
        "files_by_id": {
            "file-source": _indexed_file(
                "file-source", "assets/sources/source.mp4", source_content
            ),
            "file-unit": _indexed_file(
                "file-unit", "assets/artifacts/unit.mp4", unit_content
            ),
            "file-section": _indexed_file(
                "file-section", "assets/artifacts/section.mp4", section_content
            ),
        },
        "source_versions_by_id": {
            "source-version-1": {
                "version_id": "source-version-1",
                "logical_asset_id": "logical-source-1",
                "name": "source.mp4",
                "file_id": "file-source",
                "checksum": _sha(source_content),
                "media_kind": "video",
                "media_type": "video/mp4",
                "duration_seconds": 2,
                "created_at": "2026-07-15T08:00:00Z",
            }
        },
        "artifact_slots_by_id": {
            "unit:unit-1:video": {
                "slot_id": "unit:unit-1:video",
                "kind": "unit_video",
                "owner_ref": "unit:unit-1",
                "version_ids": ["unit-video-1"],
                "selected_version_id": "unit-video-1",
            },
            "section:section-1:video": {
                "slot_id": "section:section-1:video",
                "kind": "section_video",
                "owner_ref": "section:section-1",
                "version_ids": ["section-video-1"],
                "selected_version_id": "section-video-1",
            },
        },
        "artifact_versions_by_id": {
            "unit-video-1": {
                "version_id": "unit-video-1",
                "slot_id": "unit:unit-1:video",
                "kind": "unit_video",
                "owner_ref": "unit:unit-1",
                "name": "Unit video",
                "file_id": "file-unit",
                "checksum": _sha(unit_content),
                "based_on_generation": 0,
                "duration_seconds": 1,
                "created_at": "2026-07-15T08:00:00Z",
            },
            "section-video-1": {
                "version_id": "section-video-1",
                "slot_id": "section:section-1:video",
                "kind": "section_video",
                "owner_ref": "section:section-1",
                "name": "Section video",
                "file_id": "file-section",
                "checksum": _sha(section_content),
                "based_on_generation": 0,
                "duration_seconds": 1,
                "created_at": "2026-07-15T08:00:00Z",
            },
        },
    }
    raw["story"] = {
        "sections": {
            "items": {
                "section-1": {
                    "section_id": "section-1",
                    "title": "第一段",
                    "units": {
                        "items": {
                            "unit-1": {
                                "unit_id": "unit-1",
                                "title": "剪辑单元",
                                "route": "edit",
                                "duration_seconds": 1,
                            }
                        },
                        "order": ["unit-1"],
                    },
                }
            },
            "order": ["section-1"],
        }
    }
    raw["production"] = {
        "units_by_id": {
            "unit-1": {
                "route": "edit",
                "source_asset_version_ids": ["source-version-1"],
                "plan": {
                    "plan_id": "plan-1",
                    "timeline": {
                        "items": {
                            "clip-1": {
                                "clip_id": "clip-1",
                                "source_asset_version_id": "source-version-1",
                                "source_in_seconds": 0,
                                "source_out_seconds": 1,
                            }
                        },
                        "order": ["clip-1"],
                    },
                },
            }
        }
    }
    if duplicate_source_clip:
        plan = raw["production"]["units_by_id"]["unit-1"]["plan"]
        plan["timeline"]["items"]["clip-2"] = {
            "clip_id": "clip-2",
            "source_asset_version_id": "source-version-1",
            "source_in_seconds": 1,
            "source_out_seconds": 2,
        }
        plan["timeline"]["order"].append("clip-2")
    raw["post_production"] = {
        "sections_by_id": {
            "section-1": {
                "sequence": {
                    "items": {
                        "selection-unit": {
                            "selection_id": "selection-unit",
                            "source_ref": "project://unit/unit-1",
                            "source_kind": "unit_video",
                            "artifact_version_id": "unit-video-1",
                        }
                    },
                    "order": ["selection-unit"],
                }
            }
        },
        "final": {
            "sequence": {
                "items": {
                    "selection-section": {
                        "selection_id": "selection-section",
                        "source_ref": "project://section/section-1",
                        "source_kind": "section_video",
                        "artifact_version_id": "section-video-1",
                    }
                },
                "order": ["selection-section"],
            }
        },
    }
    project = Project.model_validate(raw)
    services = CreatorFileServices.create(tmp_path.resolve())
    services.projects.create(project)
    store = AssetFileStore(services.projects.project_root("project-1"))
    for content, uri in (
        (source_content, "assets/sources/source.mp4"),
        (unit_content, "assets/artifacts/unit.mp4"),
        (section_content, "assets/artifacts/section.mp4"),
    ):
        staged = store.stage_bytes(content)
        store.publish(staged, uri)
    return services


def test_execute_edit_persists_task_attempt_output_and_replays(tmp_path: Path) -> None:
    services = _services(tmp_path)
    runner = FakeLocalMediaRunner()
    worker = FileLocalMediaExecutionService(services, runner=runner)

    async def scenario():
        first = await worker.execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={"planVersionId": "plan-1"},
            idempotency_key="execute-edit-1",
        )
        replay = await worker.execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={"planVersionId": "plan-1"},
            idempotency_key="execute-edit-1",
        )
        return first, replay

    first, replay = asyncio.run(scenario())
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.task_id == first.task_id
    assert len(runner.calls) == 1
    spec = runner.calls[0]
    project_root = services.projects.project_root("project-1")
    assert spec.work_dir == project_root / "runtime" / "task-work" / first.task_id
    assert all(path.path.is_relative_to(spec.work_dir) for path in spec.inputs)

    runtime = ProjectExecutionStore(services.root)
    task = runtime.get_task("project-1", first.task_id)
    run = runtime.get_run("project-1", first.run_id)
    assert task.status is TaskStatus.SUCCEEDED
    assert run.status is SpecialistRunStatus.SUCCEEDED
    assert [
        item.status.value for item in runtime.list_attempts("project-1", task.task_id)
    ] == [
        "RUNNING",
        "SUCCEEDED",
    ]
    snapshot = services.projects.read("project-1")
    production = snapshot.project.production.units_by_id["unit-1"]
    assert production.rendered_video_artifact_version_id == first.artifact_version_id
    artifact = snapshot.project.assets.artifact_versions_by_id[
        first.artifact_version_id
    ]
    indexed = snapshot.project.assets.files_by_id[artifact.file_id]
    assert artifact.slot_id == "unit:unit-1:video"
    assert artifact.metadata["editPlanId"] == "plan-1"
    assert AssetFileStore(project_root).inspect(indexed).available


def test_execute_edit_reports_clip_progress_through_file_native_task(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path, duplicate_source_clip=True)
    runtime = ProjectExecutionStore(services.root)
    observed: list[float | None] = []

    def report_progress(spec: LocalMediaExecutionSpec) -> None:
        assert spec.on_clip_done is not None
        spec.on_clip_done(1, 2)
        observed.append(runtime.list_tasks("project-1")[0].progress)
        spec.on_clip_done(2, 2)
        observed.append(runtime.list_tasks("project-1")[0].progress)

    result = asyncio.run(
        FileLocalMediaExecutionService(
            services,
            runner=FakeLocalMediaRunner(hook=report_progress),
        ).execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={"planVersionId": "plan-1"},
            idempotency_key="execute-edit-progress",
        )
    )

    assert observed == [0.5, 1.0]
    assert runtime.get_task("project-1", result.task_id).progress == 1.0


def test_execute_edit_can_materialize_url_source_without_ingest_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path, duplicate_source_clip=True)
    remote_url = "https://assets.example/source.mp4"
    base = services.projects.read("project-1")
    candidate = base.project.model_dump(mode="json")
    version = candidate["assets"]["source_versions_by_id"]["source-version-1"]
    version["file_id"] = None
    version["checksum"] = _sha(remote_url.encode("utf-8"))
    version["metadata"] = {
        "sourceKind": "remote_url",
        "publicSourceUrl": remote_url,
        "checksumKind": "source_url_sha256",
    }
    services.commits.commit(
        base=base,
        candidate=candidate,
        origin=ChangeOrigin.FRONTEND_EDIT,
        review_policy=ReviewPolicy.AUTO_FIX,
        caused_by_request_id="make-remote-source",
        round_id="round-make-remote-source",
        transaction_id="make-remote-source",
        advance_accepted_baseline=True,
    )
    observed_urls: list[str] = []

    def fake_download(url: str, local_path: str) -> None:
        observed_urls.append(url)
        Path(local_path).write_bytes(b"remote-source-video")

    monkeypatch.setattr(
        "services.media_files.local_execution.download_remote_file",
        fake_download,
    )
    runner = FakeLocalMediaRunner()
    worker = FileLocalMediaExecutionService(services, runner=runner)

    result = asyncio.run(
        worker.execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={"planVersionId": "plan-1"},
            idempotency_key="execute-remote-edit",
        )
    )

    assert result.replayed is False
    assert observed_urls == [remote_url]
    assert all(item.file_id is None for item in runner.calls[0].inputs)
    assert len({item.path for item in runner.calls[0].inputs}) == 1
    assert runner.calls[0].inputs[0].path.read_bytes() == b"remote-source-video"


def test_execute_edit_prefers_existing_remote_runtime_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    remote_url = "https://assets.example/source.mp4"
    base = services.projects.read("project-1")
    candidate = base.project.model_dump(mode="json")
    version = candidate["assets"]["source_versions_by_id"]["source-version-1"]
    version["file_id"] = None
    version["checksum"] = _sha(remote_url.encode("utf-8"))
    version["metadata"] = {
        "sourceKind": "remote_url",
        "publicSourceUrl": remote_url,
        "checksumKind": "source_url_sha256",
    }
    snapshot = services.commits.commit(
        base=base,
        candidate=candidate,
        origin=ChangeOrigin.FRONTEND_EDIT,
        review_policy=ReviewPolicy.AUTO_FIX,
        caused_by_request_id="make-cached-remote-source",
        round_id="round-make-cached-remote-source",
        transaction_id="make-cached-remote-source",
        advance_accepted_baseline=True,
    ).snapshot
    project_root = services.projects.project_root("project-1")
    cache_path = project_root / "runtime" / "asset-cache" / "source-version-1.mp4"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"cached-remote-source")
    cache_entry = RemoteCacheEntry(
        path=cache_path,
        relative_uri="runtime/asset-cache/source-version-1.mp4",
        sha256=_sha(cache_path.read_bytes()),
        size_bytes=cache_path.stat().st_size,
        media_type="video/mp4",
    )
    monkeypatch.setattr(
        "services.media_files.local_execution.resolve_remote_cache",
        lambda *_args: cache_entry,
    )
    monkeypatch.setattr(
        "services.media_files.local_execution.download_remote_file",
        lambda *_args: pytest.fail("existing cache must avoid a second download"),
    )
    runner = FakeLocalMediaRunner()

    result = asyncio.run(
        FileLocalMediaExecutionService(services, runner=runner).execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={"planVersionId": "plan-1"},
            idempotency_key=f"execute-cached-remote-{snapshot.generation}",
        )
    )

    assert result.replayed is False
    assert runner.calls[0].inputs[0].path == cache_path


def test_section_and_final_compose_select_explicit_output_versions(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    runner = FakeLocalMediaRunner()
    worker = FileLocalMediaExecutionService(services, runner=runner)

    async def scenario():
        section = await worker.execute(
            project_id="project-1",
            command="STITCH_SECTION",
            target_ref="post:section-1",
            arguments={},
            idempotency_key="stitch-section-1",
        )
        final = await worker.execute(
            project_id="project-1",
            command="COMPOSE_FINAL_VIDEO",
            target_ref="post:final",
            arguments={},
            idempotency_key="compose-final-1",
        )
        return section, final

    section, final = asyncio.run(scenario())
    project = services.projects.read("project-1").project
    assert (
        project.post_production.sections_by_id[
            "section-1"
        ].rendered_video_artifact_version_id
        == section.artifact_version_id
    )
    assert (
        project.post_production.final is not None
        and project.post_production.final.rendered_video_artifact_version_id
        == final.artifact_version_id
    )
    section_artifact = project.assets.artifact_versions_by_id[
        section.artifact_version_id
    ]
    final_artifact = project.assets.artifact_versions_by_id[final.artifact_version_id]
    assert (section_artifact.kind, section_artifact.slot_id) == (
        "section_video",
        "section:section-1:video",
    )
    assert (final_artifact.kind, final_artifact.slot_id) == (
        "final_video",
        "project:final:video",
    )
    assert (
        section_artifact.metadata["sourceSelections"][0]["artifactVersionId"]
        == "unit-video-1"
    )
    assert (
        final_artifact.metadata["sourceSelections"][0]["artifactVersionId"]
        == "section-video-1"
    )


def test_project_change_during_runner_quarantines_unindexed_output(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)

    async def mutate(_spec: LocalMediaExecutionSpec) -> None:
        base = services.projects.read("project-1")
        candidate = base.project.model_dump(mode="json")
        candidate["description"] = "concurrent edit"
        services.commits.commit(
            base=base,
            candidate=candidate,
            origin=ChangeOrigin.FRONTEND_EDIT,
            review_policy=ReviewPolicy.AUTO_FIX,
            caused_by_request_id="concurrent-edit",
            round_id="round-concurrent-edit",
            transaction_id="transaction-concurrent-edit",
        )

    runner = FakeLocalMediaRunner(mutate)
    worker = FileLocalMediaExecutionService(services, runner=runner)
    with pytest.raises(ConflictError, match="结果已隔离"):
        asyncio.run(
            worker.execute(
                project_id="project-1",
                command="EXECUTE_EDIT",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="stale-edit-1",
            )
        )
    runtime = ProjectExecutionStore(services.root)
    task = runtime.list_tasks("project-1")[0]
    quarantine = runtime.get_quarantine_record("project-1", task.task_id)
    assert task.status is TaskStatus.QUARANTINED
    assert quarantine.reason == "PROJECT_INPUT_SNAPSHOT_STALE"
    artifact_id = task.metadata["artifactVersionId"]
    project = services.projects.read("project-1").project
    assert artifact_id not in project.assets.artifact_versions_by_id
    indexed = quarantine.result["indexedFile"]
    assert (
        services.projects.project_root("project-1") / indexed["relative_uri"]
    ).is_file()


def test_cancelled_task_quarantines_late_local_output(tmp_path: Path) -> None:
    services = _services(tmp_path)
    runtime = ProjectExecutionStore(services.root)

    async def cancel(_spec: LocalMediaExecutionSpec) -> None:
        task = runtime.list_tasks("project-1")[0]
        runtime.transition_task(
            "project-1",
            task.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.CANCELLED,
        )

    worker = FileLocalMediaExecutionService(
        services, runner=FakeLocalMediaRunner(cancel)
    )
    with pytest.raises(ConflictError, match="已取消"):
        asyncio.run(
            worker.execute(
                project_id="project-1",
                command="EXECUTE_EDIT",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="cancel-edit-1",
            )
        )
    task = runtime.list_tasks("project-1")[0]
    assert task.status is TaskStatus.CANCELLED
    assert (
        runtime.get_quarantine_record("project-1", task.task_id).reason
        == "TASK_CANCELLED_BEFORE_IMPORT"
    )
    assert (
        task.metadata["artifactVersionId"]
        not in services.projects.read(
            "project-1"
        ).project.assets.artifact_versions_by_id
    )


def test_restart_recovery_fails_running_task_without_durable_result(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    worker = FileLocalMediaExecutionService(services, runner=FakeLocalMediaRunner())
    base = services.projects.read("project-1")
    from services.media_files.local_execution import (
        _resolve_execution,
        _resolved_fingerprint,
    )

    resolved = _resolve_execution(
        snapshot=base,
        command=CreatorCommandType.EXECUTE_EDIT,
        target_ref="unit:unit-1",
        arguments={},
    )
    ids = worker._ids("project-1", "recover-edit-1")

    async def admit_then_recover():
        run, task = await worker._admit(
            base=base,
            resolved=resolved,
            request_fingerprint=_resolved_fingerprint(
                resolved, generation=base.generation, etag=base.etag
            ),
            command_request_hash="sha256:" + "a" * 64,
            idempotency_key="recover-edit-1",
            ids=ids,
        )
        await worker._start(run=run, task=task, resolved=resolved, ids=ids)
        return await worker.recover_project("project-1")

    recovered = asyncio.run(admit_then_recover())
    assert recovered == [ids["task_id"]]
    task = ProjectExecutionStore(services.root).get_task("project-1", ids["task_id"])
    assert task.status is TaskStatus.FAILED
    assert task.error["code"] == "LOCAL_MEDIA_PROCESS_RESTARTED"


def test_restart_recovery_converges_running_task_with_durable_result(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    runner = FakeLocalMediaRunner()
    worker = FileLocalMediaExecutionService(services, runner=runner)
    base = services.projects.read("project-1")
    from services.media_files.local_execution import (
        _resolve_execution,
        _resolved_fingerprint,
    )

    resolved = _resolve_execution(
        snapshot=base,
        command=CreatorCommandType.EXECUTE_EDIT,
        target_ref="unit:unit-1",
        arguments={},
    )
    ids = worker._ids("project-1", "recover-durable-edit-1")

    async def persist_durable_result_then_recover():
        run, task = await worker._admit(
            base=base,
            resolved=resolved,
            request_fingerprint=_resolved_fingerprint(
                resolved, generation=base.generation, etag=base.etag
            ),
            command_request_hash="sha256:" + "b" * 64,
            idempotency_key="recover-durable-edit-1",
            ids=ids,
        )
        task = await worker._start(
            run=run,
            task=task,
            resolved=resolved,
            ids=ids,
        )
        assert await worker._claim_runner(task) is True
        spec = worker._prepare_spec(base, resolved, task)
        runner_output = await runner.render(spec)
        result = worker._materialize_and_publish(
            base,
            resolved,
            task,
            ids,
            spec,
            runner_output,
        )
        worker.executions.transition_task(
            "project-1",
            task.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.RUNNING,
            updates={"result": result},
        )
        return await FileLocalMediaExecutionService(
            services,
            runner=FakeLocalMediaRunner(),
        ).recover_project("project-1")

    recovered = asyncio.run(persist_durable_result_then_recover())
    assert recovered == [ids["task_id"]]
    runtime = ProjectExecutionStore(services.root)
    assert runtime.get_task("project-1", ids["task_id"]).status is TaskStatus.SUCCEEDED
    project = services.projects.read("project-1").project
    assert (
        project.production.units_by_id["unit-1"].rendered_video_artifact_version_id
        == ids["artifact_version_id"]
    )


def test_shutdown_rejects_new_local_media_work(tmp_path: Path) -> None:
    services = _services(tmp_path)
    worker = FileLocalMediaExecutionService(services, runner=FakeLocalMediaRunner())

    async def scenario() -> None:
        await worker.shutdown()
        with pytest.raises(ConflictError, match="正在关闭"):
            await worker.execute(
                project_id="project-1",
                command="EXECUTE_EDIT",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="after-shutdown-1",
            )

    asyncio.run(scenario())


def test_runner_claim_is_created_under_project_lifecycle_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)
    state = {"depth": 0, "claim_checked": False, "read_checked": False}
    original_lifecycle_lock = services.projects.lifecycle_lock
    original_read = services.projects.read
    original_try_create = AtomicJsonRecordStore.try_create

    class TrackedLock:
        def __init__(self, delegate) -> None:
            self.delegate = delegate

        def acquire(self) -> None:
            self.delegate.acquire()
            state["depth"] += 1

        def release(self) -> None:
            state["depth"] -= 1
            self.delegate.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            self.release()

    def tracked_lifecycle_lock(project_id: str):
        return TrackedLock(original_lifecycle_lock(project_id))

    def tracked_read(project_id: str):
        if state["depth"]:
            state["read_checked"] = True
        return original_read(project_id)

    def tracked_try_create(store, value):
        if store.path.name == "runner-claim.json":
            assert state["depth"] > 0
            state["claim_checked"] = True
        return original_try_create(store, value)

    monkeypatch.setattr(services.projects, "lifecycle_lock", tracked_lifecycle_lock)
    monkeypatch.setattr(services.projects, "read", tracked_read)
    monkeypatch.setattr(AtomicJsonRecordStore, "try_create", tracked_try_create)
    asyncio.run(
        FileLocalMediaExecutionService(
            services,
            runner=FakeLocalMediaRunner(),
        ).execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="claim-lock-1",
        )
    )
    assert state["claim_checked"] is True
    assert state["read_checked"] is True


def test_task_work_parent_symlink_is_rejected_without_writing_outside_project(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    project_root = services.projects.project_root("project-1")
    task_work = project_root / "runtime" / "task-work"
    outside = tmp_path / "outside-task-work"
    outside.mkdir()
    assert not task_work.exists()
    task_work.symlink_to(outside, target_is_directory=True)
    runner = FakeLocalMediaRunner()

    with pytest.raises(StorageIntegrityError, match="task-work 路径不安全"):
        asyncio.run(
            FileLocalMediaExecutionService(services, runner=runner).execute(
                project_id="project-1",
                command="EXECUTE_EDIT",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="unsafe-task-work-1",
            )
        )
    assert runner.calls == []
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    ("transitions", "audio_plan", "original_sound", "overlay", "message"),
    [
        (({"kind": "fade", "duration_ms": 250},), {}, "preserve", None, "transition"),
        (({"kind": "cut", "duration_ms": 10},), {}, "preserve", None, "transition"),
        (
            ({"kind": "cut"},),
            {"music_prompt": "score"},
            "preserve",
            None,
            "audio_plan",
        ),
        (({"kind": "cut"},), "duck music", "preserve", None, "audio_plan"),
        (({"kind": "cut"},), {}, "mute", None, "original_sound"),
    ],
)
def test_default_ffmpeg_runner_rejects_unimplemented_directives(
    tmp_path: Path,
    transitions: tuple[dict, ...],
    audio_plan: dict | str,
    original_sound: str,
    overlay: dict | None,
    message: str,
) -> None:
    work_dir = tmp_path / "task-work"
    work_dir.mkdir()
    source = work_dir / "source.mp4"
    source.write_bytes(b"not-read-because-validation-runs-first")
    spec = LocalMediaExecutionSpec(
        command=CreatorCommandType.EXECUTE_EDIT,
        target_ref="unit:unit-1",
        task_id="task-1",
        work_dir=work_dir,
        output_path=work_dir / "output.mp4",
        inputs=(
            LocalMediaInput(
                version_id="source-version-1",
                file_id="file-source",
                checksum="a" * 64,
                media_type="video/mp4",
                path=source,
                source_ref="clip:clip-1",
                start_seconds=0,
                end_seconds=1,
                original_sound=original_sound,
                overlay=overlay,
            ),
        ),
        transitions=transitions,
        audio_plan=audio_plan,
        expected_duration_seconds=1,
    )
    with pytest.raises(ValidationError, match=message):
        asyncio.run(FfmpegLocalMediaRunner(executable="unused-ffmpeg").render(spec))


def test_default_ffmpeg_runner_applies_supported_text_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "task-work"
    work_dir.mkdir()
    source = work_dir / "source.mp4"
    source.write_bytes(b"source")
    observed: dict[str, object] = {}
    runner = FfmpegLocalMediaRunner(executable="fake-ffmpeg")

    def fake_run(arguments, *, cwd):
        observed.setdefault("commands", []).append(list(arguments))
        Path(arguments[-1]).write_bytes(b"rendered")

    def fake_overlay(**kwargs):
        observed["overlay"] = kwargs
        kwargs["output_path"].write_bytes(b"with-overlay")
        return OverlayRenderResult(True)

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(runner, "_probe_video_size", lambda _path: (640, 360))
    monkeypatch.setattr(
        "services.media_files.local_execution.render_pet_os_overlay",
        fake_overlay,
    )
    spec = LocalMediaExecutionSpec(
        command=CreatorCommandType.EXECUTE_EDIT,
        target_ref="unit:unit-1",
        task_id="task-1",
        work_dir=work_dir,
        output_path=work_dir / "output.mp4",
        inputs=(
            LocalMediaInput(
                version_id="source-version-1",
                file_id="file-source",
                checksum="a" * 64,
                media_type="video/mp4",
                path=source,
                source_ref="clip:clip-1",
                start_seconds=0,
                end_seconds=1,
                overlay={"kind": "pet_os", "text": "出发"},
            ),
        ),
        transitions=({"kind": "cut"},),
        audio_plan={},
        expected_duration_seconds=1,
    )

    result = asyncio.run(runner.render(spec))

    assert spec.output_path.read_bytes() == b"rendered"
    assert result["metadata"] == {"runner": "ffmpeg"}
    assert observed["overlay"]["text"] == "出发"
    assert observed["overlay"]["vibe"] == "chill"


def test_terminal_task_replay_preserves_original_runtime_error(tmp_path: Path) -> None:
    services = _services(tmp_path)

    class FailingRunner:
        async def render(self, _spec):
            raise ValidationError("真实 ffmpeg 错误")

    worker = FileLocalMediaExecutionService(services, runner=FailingRunner())
    arguments = {
        "project_id": "project-1",
        "command": "EXECUTE_EDIT",
        "target_ref": "unit:unit-1",
        "arguments": {},
        "idempotency_key": "failed-edit-1",
    }
    with pytest.raises(ValidationError, match="真实 ffmpeg 错误"):
        asyncio.run(worker.execute(**arguments))
    with pytest.raises(ConflictError, match="真实 ffmpeg 错误"):
        asyncio.run(worker.execute(**arguments))


def test_ffmpeg_timeout_terminates_kills_and_fails_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _services(tmp_path)

    class HangingProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.communicate_timeouts: list[float | None] = []
            self.terminated = False
            self.killed = False

        def communicate(self, timeout: float | None = None):
            self.communicate_timeouts.append(timeout)
            if len(self.communicate_timeouts) <= 2:
                raise subprocess.TimeoutExpired("ffmpeg", timeout)
            self.returncode = -9
            return "", ""

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    process = HangingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    with pytest.raises(ConflictError, match="ffmpeg 执行超时"):
        asyncio.run(
            FileLocalMediaExecutionService(
                services,
                runner=FfmpegLocalMediaRunner(
                    executable="fake-ffmpeg",
                    timeout_seconds=0.01,
                    termination_grace_seconds=0.01,
                ),
            ).execute(
                project_id="project-1",
                command="EXECUTE_EDIT",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="ffmpeg-timeout-1",
            )
        )

    runtime = ProjectExecutionStore(services.root)
    task = runtime.list_tasks("project-1")[0]
    assert task.status is TaskStatus.FAILED
    assert task.error is not None and "ffmpeg 执行超时" in task.error["message"]
    assert (
        runtime.get_run("project-1", task.run_id).status is SpecialistRunStatus.FAILED
    )
    assert process.terminated is True
    assert process.killed is True
    assert process.communicate_timeouts == [0.01, 0.01, 0.01]
    project = services.projects.read("project-1").project
    assert (
        task.metadata["artifactVersionId"] not in project.assets.artifact_versions_by_id
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_default_ffmpeg_runner_smoke(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=10:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    services = _services(tmp_path / "data", source_content=source.read_bytes())
    result = asyncio.run(
        FileLocalMediaExecutionService(
            services, runner=FfmpegLocalMediaRunner()
        ).execute(
            project_id="project-1",
            command="EXECUTE_EDIT",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="ffmpeg-smoke-1",
        )
    )
    project = services.projects.read("project-1").project
    artifact = project.assets.artifact_versions_by_id[result.artifact_version_id]
    indexed = project.assets.files_by_id[artifact.file_id]
    assert (
        AssetFileStore(services.projects.project_root("project-1"))
        .inspect(indexed)
        .available
    )
