# -*- coding: utf-8 -*-
# pylint: disable=protected-access
from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI

from api import file_asset_routes
from api.dependencies import creator_error_handler, project_file_services
from api.file_view_routes import router
from domain.errors import CreatorError
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    EntityCollection,
    Production,
    Project,
    ProjectSettings,
    R2VProduction,
    Section,
    Shot,
    Story,
    Unit,
)


def _app(tmp_path):
    services = CreatorFileServices.create(tmp_path.resolve())
    shot = Shot(
        shot_id="shot-1",
        description="Opening",
        camera="⊙ 静止",
        framing="全景",
        duration_seconds=6,
    )
    unit = Unit(
        unit_id="unit-1",
        title="First unit",
        route="r2v",
        duration_seconds=6,
        narrative="Opening action",
        shots=EntityCollection(
            items={shot.shot_id: shot},
            order=[shot.shot_id],
        ),
    )
    section = Section(
        section_id="section-1",
        title="First section",
        narrative="The opening",
        script="A first scene",
        units=EntityCollection(
            items={unit.unit_id: unit},
            order=[unit.unit_id],
        ),
    )
    project = Project.new(
        project_id="project-1",
        name="File Project",
        description="Original goal",
        scenario="short_drama",
        settings=ProjectSettings(
            aspect_ratio="9:16",
            resolution="1080P",
            platform="mobile",
            language="zh-CN",
            target_duration_seconds=6,
            content_type="video",
        ),
    )
    project.story = Story(
        title="Story title",
        outline="Outline",
        sections=EntityCollection(
            items={section.section_id: section},
            order=[section.section_id],
        ),
    )
    project.production = Production(
        units_by_id={
            unit.unit_id: R2VProduction(
                storyboard_prompt="Storyboard prompt",
                video_prompt="Video prompt",
            ),
        },
    )
    snapshot = services.projects.create(project)
    bootstrap = services.sessions.create_project_runtime(
        project.project_id,
        session_id="session-1",
        conversation_id="conversation-1",
    )
    services.sessions.set_session_status(
        project.project_id,
        bootstrap.session.session_id,
        "RUNNING",
    )

    app = FastAPI()
    app.add_exception_handler(CreatorError, creator_error_handler)
    app.include_router(router)
    app.dependency_overrides[project_file_services] = lambda: services
    return app, snapshot


def test_file_views_keep_existing_browser_shapes(tmp_path) -> None:
    app, snapshot = _app(tmp_path)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            paths = [
                "/projects/project-1/header",
                "/projects/project-1/plan",
                "/projects/project-1/sections/section-1",
                "/projects/project-1/units/unit-1/workbench",
                "/projects/project-1/assets",
                "/projects/project-1/post/sections/section-1",
                "/projects/project-1/post/final",
            ]
            responses = [await client.get(path) for path in paths]
            refs = await client.get(
                "/projects/project-1/refs",
                params={"query": "first", "types": "section,unit"},
            )
        return responses, refs

    responses, refs = asyncio.run(scenario())
    assert all(response.status_code == 200 for response in responses)

    header = responses[0]
    assert header.headers["etag"] == f'"{snapshot.etag}"'
    assert header.headers["x-project-generation"] == "0"
    assert header.json()["approvedRevisionId"] == snapshot.etag
    assert header.json()["uiPhase"] == "executing"
    assert header.json()["view"]["name"] == "File Project"

    plan = responses[1].json()["view"]
    assert plan["sections"][0]["id"] == "section-1"
    assert plan["sections"][0]["units"][0]["id"] == "unit-1"

    workbench = responses[3].json()["view"]
    assert workbench["kind"] == "r2v"
    assert workbench["storyboardPrompt"] == "Storyboard prompt"
    assert workbench["providerConstraints"]["version"] == "project-schema-1"

    assets = responses[4].json()["view"]
    assert assets["attachedSources"] == []
    assert assets["presentationAssets"] == []

    section_compose = responses[5].json()["view"]
    assert section_compose["kind"] == "section"
    assert section_compose["sectionId"] == "section-1"
    assert section_compose["readiness"]["ready"] is False

    final_compose = responses[6].json()["view"]
    assert final_compose["kind"] == "final"
    assert final_compose["sections"][0]["id"] == "section-1"

    assert refs.status_code == 200
    assert {item["type"] for item in refs.json()["items"]} == {
        "section",
        "unit",
    }


def test_asset_view_exposes_pending_ingest_and_normalizes_uploaded_video(
    tmp_path,
) -> None:
    app, _snapshot = _app(tmp_path)
    services = app.dependency_overrides[project_file_services]()
    indexed = file_asset_routes._register_remote_asset_sync(
        services,
        project_id="project-1",
        key="pending-video",
        url="https://cdn.example.com/clip.mp4",
        requested_name="clip.mp4",
        attach_source=True,
        scope="POST-assets",
    )
    task = file_asset_routes._ensure_remote_task(
        services,
        project_id="project-1",
        key="pending-video",
        url="https://cdn.example.com/clip.mp4",
        requested_name="clip.mp4",
        attach_source=True,
        scope="POST-assets",
    )

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/projects/project-1/assets")

    response = asyncio.run(scenario())
    assert response.status_code == 200
    view = response.json()["view"]
    source = next(
        item
        for item in view["presentationAssets"]
        if item["assetVersionId"] == indexed["assetVersionId"]
    )
    assert source["id"] == indexed["assetId"]
    assert source["mediaType"] == "video"
    assert view["ingestItems"] == [
        {
            "taskId": task.task_id,
            "assetId": indexed["assetId"],
            "assetVersionId": indexed["assetVersionId"],
            "name": "clip.mp4",
            "status": "QUEUED",
            "progress": 0.0,
            "error": None,
        },
    ]


def test_file_views_return_structured_not_found(tmp_path) -> None:
    app, _snapshot = _app(tmp_path)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            missing_project = await client.get("/projects/missing/header")
            missing_section = await client.get(
                "/projects/project-1/sections/missing",
            )
            missing_unit = await client.get(
                "/projects/project-1/units/missing/workbench",
            )
        return missing_project, missing_section, missing_unit

    missing_project, missing_section, missing_unit = asyncio.run(scenario())
    assert missing_project.status_code == 404
    assert missing_section.status_code == 404
    assert missing_unit.status_code == 404
    assert missing_project.json()["code"] == "NOT_FOUND"


def test_ref_search_rejects_unknown_contract_type(tmp_path) -> None:
    app, _snapshot = _app(tmp_path)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(
                "/projects/project-1/refs",
                params={"types": "analysis"},
            )

    response = asyncio.run(scenario())
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
