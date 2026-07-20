from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from domain.enums import SpecialistRunStatus, TaskStatus
from domain.errors import ConflictError, ValidationError
from services.media_files.image_execution import FileImageExecutionService
from services.project_files.assets import AssetFileStore
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    EntityCollection,
    Production,
    Project,
    R2VProduction,
    Section,
    Shot,
    Story,
    Unit,
    VisualDevelopment,
    VisualEntity,
    VisualVariant,
)
from services.runtime_files.execution_store import ProjectExecutionStore
from services.runtime_files.models import ChangeOrigin, ReviewPolicy
from utils.paths import (
    media_path_from_url,
    media_task_scope,
    media_url_for,
    unique_task_work_path,
)


pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"file-native-image" * 16


class FakeImageProvider:
    def __init__(
        self,
        hook: Callable[[], Awaitable[None] | None] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.hook = hook

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.hook is not None:
            result = self.hook()
            if result is not None:
                await result
        return {
            "content": _PNG,
            "media_type": "image/png",
            "metadata": {"provider": "fake"},
        }


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
        shots=EntityCollection(items={shot.shot_id: shot}, order=[shot.shot_id]),
    )
    section = Section(
        section_id="section-1",
        title="第一幕",
        units=EntityCollection(items={unit.unit_id: unit}, order=[unit.unit_id]),
    )
    variant = VisualVariant(
        variant_id="variant-1",
        prompt="电影感角色正面设定图",
    )
    entity = VisualEntity(
        entity_id="character-1",
        kind="character",
        name="主角",
        description="穿黑色风衣",
        variants=EntityCollection(
            items={variant.variant_id: variant},
            order=[variant.variant_id],
        ),
    )
    project = Project.new(project_id="project-1", name="File media")
    project.story = Story(
        sections=EntityCollection(
            items={section.section_id: section},
            order=[section.section_id],
        )
    )
    project.production = Production(
        units_by_id={
            unit.unit_id: R2VProduction(
                storyboard_prompt="电影分镜，雨夜街道，主角入场",
            )
        }
    )
    project.visual = VisualDevelopment(
        style="电影写实",
        entities=EntityCollection(
            items={entity.entity_id: entity},
            order=[entity.entity_id],
        ),
    )
    services.projects.create(project)
    return services


def test_storyboard_image_persists_run_task_attempt_file_index_and_replays(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeImageProvider()
    worker = FileImageExecutionService(services, provider=provider)

    async def scenario():
        first = await worker.execute(
            project_id="project-1",
            command="GENERATE_STORYBOARD_IMAGE",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="storyboard-command-1",
        )
        replay = await worker.execute(
            project_id="project-1",
            command="GENERATE_STORYBOARD_IMAGE",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="storyboard-command-1",
        )
        return first, replay

    first, replay = asyncio.run(scenario())
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.task_id == first.task_id
    assert replay.artifact_version_id == first.artifact_version_id
    assert len(provider.calls) == 1

    runtime = ProjectExecutionStore(services.root)
    task = runtime.get_task("project-1", first.task_id)
    run = runtime.get_run("project-1", first.run_id)
    attempts = runtime.list_attempts("project-1", first.task_id)
    assert task.status is TaskStatus.SUCCEEDED
    assert run.status is SpecialistRunStatus.SUCCEEDED
    assert [item.status.value for item in attempts] == ["RUNNING", "SUCCEEDED"]

    snapshot = services.projects.read("project-1")
    assert snapshot.generation == 1
    production = snapshot.project.production.units_by_id["unit-1"]
    assert isinstance(production, R2VProduction)
    assert (
        production.selected_storyboard_artifact_version_id == first.artifact_version_id
    )
    version = snapshot.project.assets.artifact_versions_by_id[first.artifact_version_id]
    slot = snapshot.project.assets.artifact_slots_by_id[version.slot_id]
    indexed = snapshot.project.assets.files_by_id[version.file_id]
    assert slot.selected_version_id == version.version_id
    assert slot.version_ids == [version.version_id]
    assert (
        AssetFileStore(services.projects.project_root("project-1"))
        .inspect(indexed)
        .available
    )


def test_generate_asset_updates_variant_history_and_selected_pointer(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    provider = FakeImageProvider()
    result = asyncio.run(
        FileImageExecutionService(services, provider=provider).execute(
            project_id="project-1",
            command="GENERATE_ASSET",
            target_ref="asset:character-1",
            arguments={"promptIndex": 0},
            idempotency_key="asset-command-1",
        )
    )

    project = services.projects.read("project-1").project
    entity = project.visual.entities.items["character-1"]
    variant = entity.variants.items["variant-1"]
    assert entity.selected_artifact_version_id == result.artifact_version_id
    assert variant.generated_artifact_version_ids == [result.artifact_version_id]
    version = project.assets.artifact_versions_by_id[result.artifact_version_id]
    assert version.owner_ref == "asset:character-1"
    assert version.kind == "visual_asset_image"


def test_generate_asset_resolves_exact_artifact_refs_and_variant_refs(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    storyboard_provider = FakeImageProvider()
    storyboard = asyncio.run(
        FileImageExecutionService(services, provider=storyboard_provider).execute(
            project_id="project-1",
            command="GENERATE_STORYBOARD_IMAGE",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="reference-storyboard-1",
        )
    )
    base = services.projects.read("project-1")
    candidate = base.project.model_dump(mode="json")
    variant = candidate["visual"]["entities"]["items"]["character-1"]["variants"][
        "items"
    ]["variant-1"]
    variant["reference_artifact_version_ids"] = [storyboard.artifact_version_id]
    services.commits.commit(
        base=base,
        candidate=candidate,
        origin=ChangeOrigin.FRONTEND_EDIT,
        review_policy=ReviewPolicy.AUTO_FIX,
        caused_by_request_id="bind-artifact-reference",
        round_id="round-bind-artifact-reference",
        transaction_id="transaction-bind-artifact-reference",
    )
    slot_id = (
        services.projects.read("project-1")
        .project.assets.artifact_versions_by_id[storyboard.artifact_version_id]
        .slot_id
    )
    asset_provider = FakeImageProvider()
    generated = asyncio.run(
        FileImageExecutionService(services, provider=asset_provider).execute(
            project_id="project-1",
            command="GENERATE_ASSET",
            target_ref="asset:character-1",
            arguments={
                "promptIndex": 0,
                "referenceImageUrls": [
                    f"artifact://{slot_id}@{storyboard.artifact_version_id}"
                ],
            },
            idempotency_key="asset-with-artifact-ref-1",
        )
    )

    assert len(asset_provider.calls) == 1
    assert len(asset_provider.calls[0]["reference_image_urls"]) == 1
    assert asset_provider.calls[0]["reference_image_urls"][0].startswith("file://")
    version = services.projects.read(
        "project-1"
    ).project.assets.artifact_versions_by_id[generated.artifact_version_id]
    assert version.provenance_refs == [
        f"artifact-version:{storyboard.artifact_version_id}"
    ]


def test_running_task_has_one_durable_provider_claim(tmp_path: Path) -> None:
    services = _services(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def wait_for_release() -> None:
        entered.set()
        await release.wait()

    provider = FakeImageProvider(wait_for_release)
    worker = FileImageExecutionService(services, provider=provider)
    arguments = {
        "project_id": "project-1",
        "command": "GENERATE_STORYBOARD_IMAGE",
        "target_ref": "unit:unit-1",
        "arguments": {},
        "idempotency_key": "concurrent-command-1",
    }

    async def scenario():
        first = asyncio.create_task(worker.execute(**arguments))
        await entered.wait()
        with pytest.raises(ConflictError, match="领取"):
            await worker.execute(**arguments)
        release.set()
        return await first

    result = asyncio.run(scenario())
    assert result.project_generation == 1
    assert len(provider.calls) == 1
    claim = (
        services.projects.project_root("project-1")
        / "runtime"
        / "tasks"
        / result.task_id
        / "provider-claim.json"
    )
    assert claim.is_file()


def test_project_change_during_provider_quarantines_unindexed_output(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)

    async def mutate_project() -> None:
        base = services.projects.read("project-1")
        candidate = base.project.model_dump(mode="json")
        candidate["strategy"]["creative_brief"] = "concurrent frontend edit"
        services.commits.commit(
            base=base,
            candidate=candidate,
            origin=ChangeOrigin.FRONTEND_EDIT,
            review_policy=ReviewPolicy.AUTO_FIX,
            caused_by_request_id="frontend-change",
            round_id="round-frontend-change",
            transaction_id="transaction-frontend-change",
        )

    provider = FakeImageProvider(mutate_project)
    worker = FileImageExecutionService(services, provider=provider)
    with pytest.raises(ConflictError, match="结果已隔离"):
        asyncio.run(
            worker.execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="stale-command-1",
            )
        )

    runtime = ProjectExecutionStore(services.root)
    task = runtime.list_tasks("project-1")[0]
    assert task.status is TaskStatus.QUARANTINED
    assert runtime.get_run("project-1", task.run_id).status is SpecialistRunStatus.STALE
    quarantine = runtime.get_quarantine_record("project-1", task.task_id)
    assert quarantine.reason == "PROJECT_INPUT_SNAPSHOT_STALE"
    project = services.projects.read("project-1").project
    assert project.assets.artifact_versions_by_id == {}
    assert (
        project.production.units_by_id["unit-1"].selected_storyboard_artifact_version_id
        is None
    )
    assert any(
        path.is_file()
        for path in (
            services.projects.project_root("project-1") / "assets" / "artifacts"
        ).iterdir()
    )


def test_cancelled_task_quarantines_late_provider_output(tmp_path: Path) -> None:
    services = _services(tmp_path)
    runtime = ProjectExecutionStore(services.root)

    async def cancel_task() -> None:
        task = runtime.list_tasks("project-1")[0]
        runtime.transition_task(
            "project-1",
            task.task_id,
            expected_status=TaskStatus.RUNNING,
            status=TaskStatus.CANCELLED,
            updates={"error": {"code": "TEST_CANCELLED"}},
        )

    provider = FakeImageProvider(cancel_task)
    with pytest.raises(ConflictError, match="迟到结果已隔离"):
        asyncio.run(
            FileImageExecutionService(services, provider=provider).execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="cancelled-command-1",
            )
        )

    task = runtime.list_tasks("project-1")[0]
    assert task.status is TaskStatus.CANCELLED
    assert (
        runtime.get_run("project-1", task.run_id).status
        is SpecialistRunStatus.CANCELLED
    )
    quarantine = runtime.get_quarantine_record("project-1", task.task_id)
    assert quarantine.reason == "TASK_CANCELLED_BEFORE_IMPORT"
    assert (
        services.projects.read("project-1").project.assets.artifact_versions_by_id == {}
    )


def test_provider_generated_file_must_belong_to_current_task_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path.resolve()))
    services = _services(tmp_path)
    runtime = ProjectExecutionStore(services.root)

    class TaskWorkProvider:
        async def generate(self, **_kwargs):
            task = runtime.list_tasks("project-1")[0]
            output = (
                services.projects.project_root("project-1")
                / "runtime"
                / "task-work"
                / task.task_id
                / "images"
                / "provider-output.png"
            )
            output.parent.mkdir(parents=True)
            output.write_bytes(_PNG)
            return {"url": media_url_for(output), "media_type": "image/png"}

    result = asyncio.run(
        FileImageExecutionService(services, provider=TaskWorkProvider()).execute(
            project_id="project-1",
            command="GENERATE_STORYBOARD_IMAGE",
            target_ref="unit:unit-1",
            arguments={},
            idempotency_key="controlled-provider-file-1",
        )
    )
    project = services.projects.read("project-1").project
    artifact = project.assets.artifact_versions_by_id[result.artifact_version_id]
    assert project.assets.files_by_id[artifact.file_id].media_type == "image/png"
    assert project.assets.files_by_id[artifact.file_id].relative_uri.endswith(".png")


def test_provider_external_file_url_is_rejected_without_project_commit(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    outside = tmp_path / "provider-secret.png"
    outside.write_bytes(_PNG)

    class ExternalFileProvider:
        async def generate(self, **_kwargs):
            return {"url": outside.as_uri(), "media_type": "image/png"}

    with pytest.raises(ValidationError, match="当前 Task work"):
        asyncio.run(
            FileImageExecutionService(
                services, provider=ExternalFileProvider()
            ).execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="external-provider-file-1",
            )
        )
    task = ProjectExecutionStore(services.root).list_tasks("project-1")[0]
    assert task.status is TaskStatus.FAILED
    assert (
        services.projects.read("project-1").project.assets.artifact_versions_by_id == {}
    )


def test_provider_task_work_symlink_is_rejected_without_project_commit(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    runtime = ProjectExecutionStore(services.root)
    outside = tmp_path / "outside-provider.png"
    outside.write_bytes(_PNG)

    class SymlinkProvider:
        async def generate(self, **_kwargs):
            task = runtime.list_tasks("project-1")[0]
            link = (
                services.projects.project_root("project-1")
                / "runtime"
                / "task-work"
                / task.task_id
                / "images"
                / "provider-output.png"
            )
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)
            return {"path": str(link), "media_type": "image/png"}

    with pytest.raises(ValidationError, match="symlink"):
        asyncio.run(
            FileImageExecutionService(services, provider=SymlinkProvider()).execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="symlink-provider-file-1",
            )
        )
    task = runtime.list_tasks("project-1")[0]
    assert task.status is TaskStatus.FAILED
    assert (
        services.projects.read("project-1").project.assets.artifact_versions_by_id == {}
    )


@pytest.mark.parametrize(
    ("content", "declared_media_type", "message"),
    [
        (b"not-an-image", "image/png", "magic"),
        (_PNG, "image/jpeg", "media_type"),
    ],
)
def test_provider_bytes_are_validated_by_magic_and_actual_media_type(
    tmp_path: Path,
    content: bytes,
    declared_media_type: str,
    message: str,
) -> None:
    services = _services(tmp_path)

    class InvalidBytesProvider:
        async def generate(self, **_kwargs):
            return {"content": content, "media_type": declared_media_type}

    with pytest.raises(ValidationError, match=message):
        asyncio.run(
            FileImageExecutionService(
                services, provider=InvalidBytesProvider()
            ).execute(
                project_id="project-1",
                command="GENERATE_STORYBOARD_IMAGE",
                target_ref="unit:unit-1",
                arguments={},
                idempotency_key="invalid-provider-bytes-1",
            )
        )
    task = ProjectExecutionStore(services.root).list_tasks("project-1")[0]
    assert task.status is TaskStatus.FAILED
    assert (
        services.projects.read("project-1").project.assets.artifact_versions_by_id == {}
    )


def test_provider_scratch_is_project_scoped_and_url_round_trips(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path.resolve()
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(root))
    project_root = root / "project-1"
    (project_root / "runtime").mkdir(parents=True)
    (project_root / "project.json").write_text("{}\n", encoding="utf-8")
    with media_task_scope("task-1", project_id="project-1"):
        path = unique_task_work_path("images", ".png", prefix="provider-")
    assert path.parent == (
        root / "project-1" / "runtime" / "task-work" / "task-1" / "images"
    )
    path.write_bytes(_PNG)
    url = media_url_for(path)
    assert url.startswith("/generated/projects/project-1/task-work/task-1/images/")
    assert media_path_from_url(url) == path.resolve()
