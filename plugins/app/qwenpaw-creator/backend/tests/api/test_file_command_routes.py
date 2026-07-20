from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI

import api.file_command_routes as file_command_routes
from api.dependencies import creator_error_handler, project_file_services
from api.file_command_routes import router as command_router
from domain.errors import CreatorError
from services.media_files import (
    FileImageExecutionResult,
    FileLocalMediaExecutionResult,
    FileR2VDispatch,
)
from services.project_files.facade import CreatorFileServices
from services.project_files.models import Project
from services.runtime_files.session_store import ProjectRuntimeSessionStore


def _app(tmp_path, project: Project | None = None):
    services = CreatorFileServices.create(tmp_path.resolve())
    services.projects.create(
        project or Project.new(project_id="project-1", name="One")
    )
    services.sessions.create_project_runtime(
        "project-1",
        session_id="session-1",
        conversation_id="conversation-1",
    )
    app = FastAPI()
    app.add_exception_handler(CreatorError, creator_error_handler)
    app.include_router(command_router)
    app.dependency_overrides[project_file_services] = lambda: services
    return app, services


def _rich_project() -> Project:
    raw = Project.new(
        project_id="project-1",
        name="One",
        scenario="video_edit",
        now=datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc),
    ).model_dump(mode="json")
    raw["assets"] = {
        "files_by_id": {
            **{
                f"file-source-{index}": {
                    "file_id": f"file-source-{index}",
                    "kind": "source_original",
                    "relative_uri": f"assets/sources/source-{index}.mp4",
                    "sha256": character * 64,
                    "size_bytes": 100 + index,
                    "media_type": "video/mp4",
                    "created_at": "2026-07-15T08:00:00Z",
                }
                for index, character in enumerate(("a", "b", "c"), 1)
            },
            "file-artifact-1": {
                "file_id": "file-artifact-1",
                "kind": "artifact_payload",
                "relative_uri": "assets/artifacts/artifact-1.png",
                "sha256": "d" * 64,
                "size_bytes": 200,
                "media_type": "image/png",
                "created_at": "2026-07-15T08:00:00Z",
            },
        },
        "source_versions_by_id": {
            f"source-version-{index}": {
                "version_id": f"source-version-{index}",
                "logical_asset_id": f"logical-{index}",
                "name": f"source-{index}.mp4",
                "file_id": f"file-source-{index}",
                "checksum": character * 64,
                "media_kind": "video",
                "media_type": "video/mp4",
                "duration_seconds": 10,
                "created_at": "2026-07-15T08:00:00Z",
            }
            for index, character in enumerate(("a", "b", "c"), 1)
        },
        "artifact_slots_by_id": {
            "slot-1": {
                "slot_id": "slot-1",
                "kind": "visual_image",
                "owner_ref": "asset:visual-1",
                "version_ids": ["artifact-version-1"],
                "selected_version_id": "artifact-version-1",
            }
        },
        "artifact_versions_by_id": {
            "artifact-version-1": {
                "version_id": "artifact-version-1",
                "slot_id": "slot-1",
                "kind": "visual_image",
                "owner_ref": "asset:visual-1",
                "name": "visual.png",
                "file_id": "file-artifact-1",
                "checksum": "d" * 64,
                "based_on_generation": 0,
                "created_at": "2026-07-15T08:00:00Z",
            }
        },
    }
    raw["sources"] = {
        "sources": {
            "items": {
                "source-1": {
                    "source_id": "source-1",
                    "display_name": "Source One",
                    "logical_asset_id": "logical-1",
                    "selected_asset_version_id": "source-version-1",
                }
            },
            "order": ["source-1"],
        }
    }
    raw["visual"] = {
        "entities": {
            "items": {
                "visual-1": {
                    "entity_id": "visual-1",
                    "kind": "character",
                    "name": "Character",
                    "variants": {
                        "items": {
                            "variant-1": {
                                "variant_id": "variant-1",
                            }
                        },
                        "order": ["variant-1"],
                    },
                }
            },
            "order": ["visual-1"],
        }
    }
    raw["story"] = {
        "sections": {
            "items": {
                "section-1": {
                    "section_id": "section-1",
                    "title": "Section",
                    "units": {
                        "items": {
                            "unit-1": {
                                "unit_id": "unit-1",
                                "title": "Edit",
                                "route": "edit",
                                "duration_seconds": 8,
                                "source_refs": ["source-1"],
                                "character_refs": ["visual-1"],
                                "shots": {
                                    "items": {
                                            "shot-1": {
                                                "shot_id": "shot-1",
                                                "duration_seconds": 1,
                                                "character_refs": ["visual-1"],
                                            }
                                    },
                                    "order": ["shot-1"],
                                },
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
                                "source_out_seconds": 4,
                            },
                            "clip-2": {
                                "clip_id": "clip-2",
                                "source_asset_version_id": "source-version-1",
                                "source_in_seconds": 4,
                                "source_out_seconds": 8,
                            },
                        },
                        "order": ["clip-1", "clip-2"],
                    },
                    "storyboard": {
                        "items": {
                            "panel-1": {
                                "panel_id": "panel-1",
                                "clip_id": "clip-1",
                                "source_timestamp_seconds": 1,
                            },
                            "panel-2": {
                                "panel_id": "panel-2",
                                "clip_id": "clip-2",
                                "source_timestamp_seconds": 5,
                            },
                        },
                        "order": ["panel-1", "panel-2"],
                    },
                },
            }
        }
    }
    return Project.model_validate(raw)


async def _submit(
    client: httpx.AsyncClient,
    command_id: str,
    command_type: str,
    target_ref: str,
    arguments: dict,
) -> httpx.Response:
    return await client.post(
        "/projects/project-1/commands",
        headers={"Idempotency-Key": command_id},
        json={
            "clientCommandId": command_id,
            "editSessionId": "edit-session-1",
            "type": command_type,
            "targetRef": target_ref,
            "arguments": arguments,
        },
    )


def test_direct_file_command_commits_once_and_replays(tmp_path) -> None:
    app, services = _app(tmp_path)
    payload = {
        "clientCommandId": "create-section-1",
        "editSessionId": "edit-1",
        "type": "CREATE_SECTION",
        "targetRef": "project:story",
        "arguments": {"title": "开场"},
    }

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "create-section-1"},
                json=payload,
            )
            replay = await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "create-section-1"},
                json=payload,
            )
            return first, replay

    first, replay = asyncio.run(scenario())
    assert first.status_code == 202
    assert first.json()["status"] == "APPLIED"
    assert first.json()["eventSeq"] == 0
    assert replay.status_code == 202
    assert replay.content == first.content

    snapshot = services.projects.read("project-1")
    assert snapshot.generation == 1
    section_id = snapshot.project.story.sections.order[0]
    assert snapshot.project.story.sections.items[section_id].title == "开场"


def test_model_command_is_queued_as_one_runtime_message_and_replays(tmp_path) -> None:
    app, services = _app(tmp_path)
    payload = {
        "clientCommandId": "plan-units-1",
        "type": "PLAN_UNITS",
        "targetRef": "project:story",
        "arguments": {"instruction": "拆成三个制作单元"},
    }

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "plan-units-1"},
                json=payload,
            )
            replay = await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "plan-units-1"},
                json=payload,
            )
            return first, replay

    first, replay = asyncio.run(scenario())
    assert first.status_code == 202
    assert first.json()["status"] == "QUEUED"
    assert replay.content == first.content

    runtime = ProjectRuntimeSessionStore(services.root)
    session = runtime.get_project_session("project-1")
    messages = runtime.list_messages("project-1", session.session_id)
    assert len(messages) == 1
    assert messages[0].classification.value == "workspace_command"
    assert "PLAN_UNITS" in (messages[0].content_parts[0].text or "")


def test_image_command_dispatches_file_worker_without_agent_message(
    tmp_path, monkeypatch
) -> None:
    app, services = _app(tmp_path)
    calls: list[dict] = []

    async def fake_execute(_services, **kwargs):
        calls.append(kwargs)
        return FileImageExecutionResult(
            task_id="task-image-1",
            run_id="run-image-1",
            transaction_id="transaction-image-1",
            artifact_version_id="artifact-version-image-1",
            project_etag="sha256:image-head",
            project_generation=1,
            replayed=False,
        )

    monkeypatch.setattr(file_command_routes, "execute_file_image_command", fake_execute)
    payload = {
        "clientCommandId": "image-command-1",
        "type": "GENERATE_ASSET",
        "targetRef": "asset:character-1",
        "arguments": {"prompt": "character concept"},
    }

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "image-command-1"},
                json=payload,
            )

    response = asyncio.run(scenario())
    assert response.status_code == 202
    assert response.json() == {
        "commandId": "image-command-1",
        "status": "APPLIED",
        "eventSeq": 0,
        "transactionId": "transaction-image-1",
        "workingHead": "sha256:image-head",
    }
    assert calls[0]["command"].value == "GENERATE_ASSET"
    session = services.sessions.get_project_session("project-1")
    assert services.sessions.list_messages("project-1", session.session_id) == []


def test_local_media_commands_dispatch_file_worker_without_agent_messages(
    tmp_path, monkeypatch
) -> None:
    app, services = _app(tmp_path)
    calls: list[dict] = []

    async def fake_execute(_services, **kwargs):
        calls.append(kwargs)
        suffix = kwargs["command"].value.casefold()
        return FileLocalMediaExecutionResult(
            task_id=f"task-{suffix}",
            run_id=f"run-{suffix}",
            transaction_id=f"transaction-{suffix}",
            artifact_version_id=f"artifact-version-{suffix}",
            project_etag=f"sha256:{suffix}",
            project_generation=1,
            replayed=False,
        )

    monkeypatch.setattr(
        file_command_routes,
        "execute_file_local_media_command",
        fake_execute,
    )
    commands = (
        ("EXECUTE_EDIT", "unit:unit-1"),
        ("STITCH_SECTION", "post:section-1"),
        ("COMPOSE_FINAL_VIDEO", "post:final"),
    )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return [
                await client.post(
                    "/projects/project-1/commands",
                    headers={"Idempotency-Key": f"local-media-{index}"},
                    json={
                        "clientCommandId": f"local-media-{index}",
                        "type": command,
                        "targetRef": target_ref,
                        "arguments": {},
                    },
                )
                for index, (command, target_ref) in enumerate(commands, 1)
            ]

    responses = asyncio.run(scenario())
    assert [response.status_code for response in responses] == [202, 202, 202]
    assert [response.json()["status"] for response in responses] == [
        "APPLIED",
        "APPLIED",
        "APPLIED",
    ]
    assert [call["command"].value for call in calls] == [
        command for command, _target_ref in commands
    ]
    session = services.sessions.get_project_session("project-1")
    assert services.sessions.list_messages("project-1", session.session_id) == []


def test_r2v_command_queues_file_supervisor_without_agent_message(
    tmp_path, monkeypatch
) -> None:
    app, services = _app(tmp_path)
    calls: list[dict] = []

    async def fake_execute(_services, **kwargs):
        calls.append(kwargs)
        return FileR2VDispatch(
            task_id="task-r2v-1",
            run_id="run-r2v-1",
            transaction_id="transaction-r2v-1",
            input_etag="sha256:r2v-input-head",
            replayed=False,
        )

    monkeypatch.setattr(
        file_command_routes,
        "execute_file_r2v_command",
        fake_execute,
    )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/projects/project-1/commands",
                headers={"Idempotency-Key": "r2v-route-1"},
                json={
                    "clientCommandId": "r2v-route-1",
                    "type": "GENERATE_R2V_VIDEO",
                    "targetRef": "unit:unit-1",
                    "arguments": {},
                },
            )

    response = asyncio.run(scenario())
    assert response.status_code == 202
    assert response.json() == {
        "commandId": "r2v-route-1",
        "status": "QUEUED",
        "eventSeq": 0,
        "transactionId": "transaction-r2v-1",
        "workingHead": "sha256:r2v-input-head",
    }
    assert calls[0]["target_ref"] == "unit:unit-1"
    session = services.sessions.get_project_session("project-1")
    assert services.sessions.list_messages("project-1", session.session_id) == []


def test_ai_edit_commands_mutate_embedded_plan_directly(tmp_path) -> None:
    app, services = _app(tmp_path, _rich_project())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            commands = [
                (
                    "range-1",
                    "SET_EDIT_CLIP_RANGE",
                    {"clipId": "clip-1", "start": 1, "end": 5},
                ),
                (
                    "os-1",
                    "SET_EDIT_CLIP_OS",
                    {
                        "clipId": "clip-1",
                        "text": "出发",
                        "vibe": "action",
                        "appear_at": 0.5,
                        "duration": 2,
                    },
                ),
                (
                    "transition-1",
                    "SET_EDIT_CLIP_TRANSITION",
                    {"clipId": "clip-1", "transition": "fade"},
                ),
                (
                    "audio-1",
                    "SET_EDIT_AUDIO_PLAN",
                    {
                        "audio_plan": {
                            "preserve_original": False,
                            "music_prompt": "轻快",
                            "voiceover": "旁白",
                            "notes": "压低环境声",
                        }
                    },
                ),
            ]
            return [
                await _submit(client, command_id, command_type, "unit:unit-1", args)
                for command_id, command_type, args in commands
            ]

    responses = asyncio.run(scenario())
    assert [response.status_code for response in responses] == [202] * 4
    assert all(response.json()["status"] == "APPLIED" for response in responses)

    project = services.projects.read("project-1").project
    production = project.production.units_by_id["unit-1"]
    assert production.plan is not None
    clip = production.plan.timeline.items["clip-1"]
    assert (clip.source_in_seconds, clip.source_out_seconds) == (1, 5)
    assert clip.overlay == {
        "kind": "pet_os",
        "text": "出发",
        "vibe": "action",
        "appear_at": 0.5,
        "duration": 2.0,
    }
    assert clip.transition == "fade"
    assert production.plan.audio_plan.music_prompt == "轻快"
    assert production.plan.audio_plan.preserve_original is False
    assert production.plan.target_duration_seconds == 8
    assert production.plan.plan_hash == production.plan.content_hash()
    assert "clip-1: 1–5 秒" in production.timeline_summary


def test_move_and_delete_edit_clip_keep_timeline_and_storyboard_closed(tmp_path) -> None:
    app, services = _app(tmp_path, _rich_project())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            moved = await _submit(
                client,
                "move-clip-1",
                "MOVE_EDIT_CLIP",
                "unit:unit-1",
                {"clipId": "clip-2", "beforeClipId": "clip-1"},
            )
            deleted = await _submit(
                client,
                "delete-clip-1",
                "DELETE_EDIT_CLIP",
                "unit:unit-1",
                {"clipId": "clip-1"},
            )
            return moved, deleted

    moved, deleted = asyncio.run(scenario())
    assert moved.status_code == deleted.status_code == 202
    assert moved.json()["status"] == deleted.json()["status"] == "APPLIED"

    production = services.projects.read("project-1").project.production.units_by_id[
        "unit-1"
    ]
    assert production.plan is not None
    assert production.plan.timeline.order == ["clip-2"]
    assert set(production.plan.timeline.items) == {"clip-2"}
    assert production.plan.storyboard.order == ["panel-2"]
    assert set(production.plan.storyboard.items) == {"panel-2"}
    assert production.plan.target_duration_seconds == 4
    assert "clip-1" not in production.timeline_summary


def test_edit_command_semantic_errors_do_not_publish_project(tmp_path) -> None:
    app, services = _app(tmp_path, _rich_project())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            bad_range = await _submit(
                client,
                "bad-range",
                "SET_EDIT_CLIP_RANGE",
                "unit:unit-1",
                {"clipId": "clip-1", "start": 4, "end": 4},
            )
            bad_audio = await _submit(
                client,
                "bad-audio",
                "SET_EDIT_AUDIO_PLAN",
                "unit:unit-1",
                {"audio_plan": {"bgm": "legacy field"}},
            )
            bad_move = await _submit(
                client,
                "bad-move",
                "MOVE_EDIT_CLIP",
                "unit:unit-1",
                {
                    "clipId": "clip-1",
                    "beforeClipId": "clip-2",
                    "afterClipId": "clip-2",
                },
            )
            return bad_range, bad_audio, bad_move

    responses = asyncio.run(scenario())
    assert [response.status_code for response in responses] == [422, 422, 422]
    assert services.projects.read("project-1").generation == 0


def test_supplement_asset_crud_updates_variants_and_reference_closure(tmp_path) -> None:
    app, services = _app(tmp_path, _rich_project())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            commands = [
                (
                    "create-visual",
                    "project:assets",
                    {
                        "operation": "create",
                        "id": "visual-new",
                        "assetKind": "scene",
                        "name": "新场景",
                    },
                ),
                (
                    "rename-visual",
                    "asset:visual-new",
                    {"field": "name", "value": "夜晚街道"},
                ),
                (
                    "prompt-generated-reference",
                    "asset:visual-new",
                    {
                        "field": "promptConfig",
                        "promptIndex": 0,
                        "prompt": "延续已生成的视觉风格",
                        "referenceImageUrls": [
                            "artifact://slot-1@artifact-version-1"
                        ],
                    },
                ),
                (
                    "prompt-visual",
                    "asset:visual-1",
                    {
                        "field": "promptConfig",
                        "promptIndex": 0,
                        "prompt": "正面角色图",
                        "referenceImageUrls": [
                            "asset://logical-2@source-version-2"
                        ],
                    },
                ),
                (
                    "image-visual",
                    "asset:visual-1",
                    {
                        "field": "image",
                        "promptIndex": 0,
                        "imageRef": "artifact://slot-1@artifact-version-1",
                    },
                ),
                (
                    "appearance-prompt",
                    "asset:visual-1",
                    {
                        "field": "appearancePrompt",
                        "refDescription": "雨衣造型",
                    },
                ),
                (
                    "appearance-image",
                    "asset:visual-1",
                    {
                        "field": "appearance",
                        "refDescription": "运动装",
                        "prompt": "运动装正面",
                        "imageUrl": "/media/assets/source-version-2",
                    },
                ),
                (
                    "remove-appearance",
                    "asset:visual-1",
                    {
                        "field": "appearance",
                        "action": "removeFacet",
                        "promptIndex": 1,
                    },
                ),
                (
                    "delete-visual",
                    "asset:visual-1",
                    {"operation": "delete"},
                ),
                (
                    "delete-source",
                    "asset:logical-3",
                    {
                        "operation": "delete",
                        "assetVersionRef": "asset://logical-3@source-version-3",
                    },
                ),
            ]
            return [
                await _submit(
                    client,
                    command_id,
                    "SUPPLEMENT_ASSET",
                    target_ref,
                    arguments,
                )
                for command_id, target_ref, arguments in commands
            ]

    responses = asyncio.run(scenario())
    assert [response.status_code for response in responses] == [202] * len(responses)
    assert all(response.json()["status"] == "APPLIED" for response in responses)

    project = services.projects.read("project-1").project
    assert project.visual.entities.items["visual-new"].name == "夜晚街道"
    new_variant = project.visual.entities.items["visual-new"].variants.items.values()
    assert next(iter(new_variant)).reference_artifact_version_ids == [
        "artifact-version-1"
    ]
    assert "visual-1" not in project.visual.entities.items
    unit = project.story.sections.items["section-1"].units.items["unit-1"]
    assert unit.character_refs == []
    assert unit.shots.items["shot-1"].character_refs == []
    assert "source-version-3" not in project.assets.source_versions_by_id
    # Project-level delete removes the index record, not immutable payload bytes.
    assert "file-source-3" in project.assets.files_by_id
    assert "artifact-version-1" in project.assets.artifact_versions_by_id


def test_supplement_asset_refuses_to_delete_referenced_source_version(tmp_path) -> None:
    app, services = _app(tmp_path, _rich_project())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await _submit(
                client,
                "delete-used-source",
                "SUPPLEMENT_ASSET",
                "asset:logical-1",
                {
                    "operation": "delete",
                    "assetVersionRef": "asset://logical-1@source-version-1",
                },
            )

    response = asyncio.run(scenario())
    assert response.status_code == 409
    assert response.json()["details"]["references"]
    assert "source-version-1" in services.projects.read(
        "project-1"
    ).project.assets.source_versions_by_id
