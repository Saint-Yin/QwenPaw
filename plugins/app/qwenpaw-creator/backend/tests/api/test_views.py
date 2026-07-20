from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient


def test_header_plan_assets_and_refs_are_page_specific_envelopes(app):
    async def scenario():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project = (
                await client.post(
                    "/projects",
                    json={
                        "clientRequestId": "view-project",
                        "name": "View Project",
                        "description": "View description",
                        "scenario": "general",
                        "aspectRatio": "16:9",
                        "resolution": "720P",
                    },
                )
            ).json()
            header_idle = await client.get(f"/projects/{project['projectId']}/header")
            plan_idle = await client.get(f"/projects/{project['projectId']}/plan")
            ingested = await client.post(
                f"/projects/{project['projectId']}/assets",
                json={
                    "clientRequestId": "view-asset",
                    "kind": "text",
                    "name": "reference.txt",
                    "value": "reference",
                        "postIngestAction": "ATTACH_SOURCE",
                },
            )
            await client.post(
                f"/projects/{project['projectId']}/messages",
                json={
                    "clientMessageId": "view-root-message",
                    "conversationId": project["conversationId"],
                    "message": "开始制作",
                    "assetVersionRefs": [
                        f"asset-version:{ingested.json()['assetVersionId']}"
                    ],
                },
            )
            header_working = await client.get(f"/projects/{project['projectId']}/header")
            assets = await client.get(f"/projects/{project['projectId']}/assets")
            refs = await client.get(
                f"/projects/{project['projectId']}/refs", params={"types": "asset"}
            )
            return header_idle, plan_idle, header_working, assets, refs

    header_idle, plan_idle, header_working, assets, refs = asyncio.run(scenario())
    assert header_idle.status_code == 200
    assert header_idle.json()["uiPhase"] == "idle"
    assert header_idle.json()["view"]["name"] == "View Project"
    assert "sections" not in header_idle.json()["view"]
    assert plan_idle.json()["view"]["sections"] == []
    # File-native message admission persists the turn; execution is not
    # inferred from an append alone and remains idle until a worker claims it.
    assert header_working.json()["uiPhase"] == "idle"
    assert header_working.json()["workingHead"] is None
    assert assets.status_code == 200
    assert len(assets.json()["view"]["attachedSources"]) == 1
    assert len(assets.json()["view"]["availableAssets"]) == 1
    assert refs.status_code == 200
    assert len(refs.json()["items"]) == 1
    assert refs.json()["items"][0]["type"] == "asset"


def test_view_routes_do_not_expose_whole_project_or_old_canvas(app):
    paths = app.openapi()["paths"]
    assert "get" in paths["/projects/{project_id}/header"]
    assert "get" in paths["/projects/{project_id}/plan"]
    assert "get" in paths["/projects/{project_id}/units/{unit_id}/workbench"]
    assert not any("canvas" in path.lower() for path in paths)
    assert "put" not in paths.get("/projects/{project_id}", {})


def test_missing_specialized_view_resources_return_contract_404(app):
    async def scenario():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project = (
                await client.post(
                    "/projects",
                    json={
                        "clientRequestId": "missing-specialized-view-project",
                        "name": "Missing Specialized View Project",
                        "scenario": "general",
                        "aspectRatio": "16:9",
                        "resolution": "720P",
                    },
                )
            ).json()
            project_id = project["projectId"]
            await client.get(f"/projects/{project_id}/plan")
            workbench = await client.get(
                f"/projects/{project_id}/units/deleted-unit/workbench"
            )
            section_compose = await client.get(
                f"/projects/{project_id}/post/sections/deleted-section"
            )
            return workbench, section_compose

    responses = asyncio.run(scenario())
    for response in responses:
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
