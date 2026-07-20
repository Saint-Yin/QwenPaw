# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-statements
"""§13.4 scenario 15: real Composer file ingest before the first Goal."""
from __future__ import annotations

import re
from urllib.parse import unquote
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.home_page import HomePage

pytestmark = [pytest.mark.contract, pytest.mark.assets]


def _presentation(envelope: dict) -> dict:
    value = envelope["view"]
    return value["view"] if "presentationVersion" in value else value


def test_composer_real_file_ingest_precedes_atomic_initial_goal(
    page,
    api,
    tmp_path,
):
    source = tmp_path / "composer-first-source.txt"
    source_bytes = "真实 Composer 首轮素材边界".encode("utf-8")
    source.write_bytes(source_bytes)
    project_name = f"Composer boundary {uuid4().hex[:8]}"
    goal = "只使用上传的文本素材建立一个最小方案，然后等待用户审阅。"
    boundary: dict = {}

    def observe_without_mocking(route):
        match = re.search(
            r"/projects/([^/]+)/assets(?:\?|$)",
            route.request.url,
        )
        if match and route.request.method == "POST":
            project_id = unquote(match.group(1))
            session_response = api.get(f"/projects/{project_id}/session")
            transaction_response = api.get(
                f"/projects/{project_id}/transactions/active",
            )
            tasks_response = api.get(f"/projects/{project_id}/tasks")
            plan_response = api.get(f"/projects/{project_id}/plan")
            conversations_response = api.get(
                f"/projects/{project_id}/conversations",
            )
            boundary.update(
                {
                    "projectId": project_id,
                    "sessionStatus": session_response.status_code,
                    "session": session_response.json(),
                    "transactionStatus": transaction_response.status_code,
                    "transaction": transaction_response.json(),
                    "tasks": tasks_response.json(),
                    "plan": plan_response.json(),
                    "conversations": conversations_response.json(),
                },
            )
            conversations = conversations_response.json()["items"]
            if conversations:
                messages = api.get(
                    f"/projects/{project_id}/conversations/"
                    f"{conversations[0]['conversationId']}/messages",
                )
                boundary["messages"] = messages.json()
        # This is a real multipart request.  The route is only paused long
        # enough to inspect the public pre-ingest state, then continued.
        route.continue_()

    page.route(
        "**/api/qwenpaw-creator/projects/*/assets",
        observe_without_mocking,
    )
    composer = HomePage(page).open().open_composer()
    composer.select_scenario("通用")
    composer.fill_name(project_name).fill_goal(goal).add_files(str(source))
    expect(composer.attachment_chip(source.name)).to_be_visible()

    project_id: str | None = None
    try:
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and re.search(
                r"/api/qwenpaw-creator/projects/[^/]+/messages$",
                response.url,
            )
            is not None,
            timeout=30_000,
        ) as message_info:
            with page.expect_response(
                lambda response: response.request.method == "POST"
                and re.search(
                    r"/api/qwenpaw-creator/projects/[^/]+/assets$",
                    response.url,
                )
                is not None,
                timeout=30_000,
            ) as asset_info:
                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url.endswith("/api/qwenpaw-creator/projects"),
                    timeout=30_000,
                ) as project_info:
                    composer.launch()

        project_response = project_info.value
        asset_response = asset_info.value
        message_response = message_info.value
        assert project_response.status == 201
        assert asset_response.status == 202
        assert message_response.status == 202
        project = project_response.json()
        project_id = project["projectId"]
        assert boundary["projectId"] == project_id

        pre_session = boundary["session"]["session"]
        assert boundary["sessionStatus"] == 200
        assert pre_session["status"] == "IDLE"
        assert pre_session.get("activeGoalId") is None
        assert pre_session.get("activeTransactionId") is None
        assert boundary["transactionStatus"] == 200
        assert boundary["transaction"] is None
        assert boundary["tasks"]["items"] == []
        assert boundary["messages"]["items"] == []
        assert boundary["plan"]["activeTransactionId"] is None
        assert _presentation(boundary["plan"])["sections"] == []

        asset_request_bytes = asset_response.request.post_data_buffer or b""
        assert b"postIngestAction" in asset_request_bytes
        assert b"NONE" in asset_request_bytes
        assert source.name.encode() in asset_request_bytes

        accepted_asset = asset_response.json()
        asset_task = api.wait_task(project_id, accepted_asset["taskId"])
        assert asset_task["status"] == "SUCCEEDED", asset_task
        expected_refs = list(asset_task["resultRefs"])
        if accepted_asset.get("assetVersionId"):
            expected_refs = [
                f"asset-version:{accepted_asset['assetVersionId']}",
            ]
        assert len(expected_refs) == 1

        message_payload = message_response.request.post_data_json
        assert message_payload["assetVersionRefs"] == expected_refs
        assert message_payload["content"] == [{"type": "text", "text": goal}]
        assert message_payload["context"] == {"panel": "composer"}
        assert (
            message_payload["creatorSessionId"] == project["creatorSessionId"]
        )
        assert message_payload["conversationId"] == project["conversationId"]

        session = api.get(f"/projects/{project_id}/session").json()["session"]
        assert session["activeGoalId"]
        assert session["activeTransactionId"]
        active = api.get(f"/projects/{project_id}/transactions/active")
        assert active.status_code == 200
        assert active.json()["id"] == session["activeTransactionId"]

        messages = api.get(
            f"/projects/{project_id}/conversations/{project['conversationId']}/messages",
        ).json()["items"]
        initial = next(
            item for item in messages if item["source"] == "initial_goal"
        )
        assert initial["metadata"]["assetVersionRefs"] == expected_refs
        assert initial["metadata"]["context"] == {"panel": "composer"}

        content = api.get(
            f"/projects/{project_id}/assets/{accepted_asset['assetId']}/content",
            params={"versionId": expected_refs[0].split(":", 1)[1]},
        )
        assert content.status_code == 200
        assert content.content == source_bytes
    finally:
        if project_id:
            stop_key = f"e2e-composer-stop-{uuid4()}"
            api.post(
                f"/projects/{project_id}/interrupt",
                json={},
                headers={"Idempotency-Key": stop_key},
            )
            api.delete_project(project_id)
