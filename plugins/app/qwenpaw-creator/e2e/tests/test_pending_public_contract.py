# -*- coding: utf-8 -*-
"""§13.4 scenarios 11/16 using only a naturally sealed public fixture."""
from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = [pytest.mark.pending, pytest.mark.contract]


def _browser_fetch(page, url: str, *, method: str = "GET", body=None, key=None):
    return page.evaluate(
        """async ({url, method, body, key}) => {
          const headers = {};
          if (body !== null) headers['Content-Type'] = 'application/json';
          if (key !== null) headers['Idempotency-Key'] = key;
          const response = await fetch(url, {
            method,
            headers,
            body: body === null ? undefined : JSON.stringify(body),
          });
          const text = await response.text();
          let parsed = null;
          try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
          return {status: response.status, body: parsed};
        }""",
        {"url": url, "method": method, "body": body, "key": key},
    )


def test_pending_action_commands_are_durable_deferred_with_zero_task_or_run_delta(
    api, pending_review_target, tmp_path
):
    project_id = pending_review_target["projectId"]
    transaction_id = pending_review_target["transactionId"]
    review_url = f"/projects/{project_id}/transactions/{transaction_id}/review"
    review_before = api.get(review_url).json()
    tasks_before = api.get(f"/projects/{project_id}/tasks").json()["items"]
    runs_before = api.get(f"/projects/{project_id}/specialist-runs").json()["items"]

    commands = (
        ("GENERATE_SCRIPT", "project:plan"),
        ("ANALYZE_SOURCE_MEDIA", "asset:pending-gate-probe"),
        ("EXECUTE_EDIT", "unit:pending-gate-probe"),
        ("COMPOSE_FINAL_VIDEO", "post:final"),
    )
    for command_type, target_ref in commands:
        command_id = f"e2e-pending-{command_type.lower()}-{uuid4()}"
        payload = {
            "clientCommandId": command_id,
            "type": command_type,
            "targetRef": target_ref,
            "arguments": {},
            "context": {"e2e": "pending-action-gate"},
            "expectedTargetVersions": [],
        }
        accepted = api.command(project_id, payload)
        replay = api.command(project_id, payload)
        assert accepted.status_code == replay.status_code == 202
        assert accepted.content == replay.content
        assert accepted.json()["status"] == "DEFERRED_UNTIL_REVIEW_RESOLVED"

    tasks_after_commands = api.get(f"/projects/{project_id}/tasks").json()["items"]
    runs_after_commands = api.get(
        f"/projects/{project_id}/specialist-runs"
    ).json()["items"]
    assert {item["id"] for item in tasks_after_commands} == {
        item["id"] for item in tasks_before
    }
    assert {item["id"] for item in runs_after_commands} == {
        item["id"] for item in runs_before
    }

    # The one permitted PENDING I/O lane is transaction-less asset ingest.
    # ATTACH_SOURCE must become a Manual Edit Overlay and must not wake Creator.
    upload_path = tmp_path / f"pending-overlay-{uuid4().hex[:8]}.txt"
    upload_path.write_text("pending overlay source", encoding="utf-8")
    upload_key = f"e2e-pending-attach-{uuid4()}"
    with upload_path.open("rb") as handle:
        accepted_upload = api.post_file(
            f"/projects/{project_id}/assets",
            files={"file": (upload_path.name, handle, "text/plain")},
            data={
                "clientRequestId": upload_key,
                "postIngestAction": "ATTACH_SOURCE",
            },
            headers={"Idempotency-Key": upload_key},
        )
    assert accepted_upload.status_code == 202, accepted_upload.text
    task = api.wait_task(project_id, accepted_upload.json()["taskId"])
    assert task["status"] == "SUCCEEDED", task
    assert task["kind"] == "asset_ingest"
    assert task["transactionId"] is None
    follow_up = task["result"]["followUp"]
    assert follow_up["type"] == "ATTACH_SOURCE_ASSETS"
    assert follow_up["targetRef"] == f"asset:{accepted_upload.json()['assetId']}"

    session_after = api.get(f"/projects/{project_id}/session").json()["session"]
    assert session_after["status"] == "PENDING_REVIEW"
    assert session_after["activeTransactionId"] == transaction_id
    assets_after = api.view(project_id, "assets")
    assert assets_after["uiPhase"] == "waiting_review"
    assert assets_after["manualEditOverlay"] is not None
    assert assets_after["reviewRevisionId"] == review_before["reviewRevisionId"]
    review_after = api.get(review_url).json()
    assert review_after["id"] == review_before["id"]
    assert review_after["reviewRevisionId"] == review_before["reviewRevisionId"]

    runs_after_upload = api.get(
        f"/projects/{project_id}/specialist-runs"
    ).json()["items"]
    assert {item["id"] for item in runs_after_upload} == {
        item["id"] for item in runs_before
    }
    new_tasks = [
        item
        for item in api.get(f"/projects/{project_id}/tasks").json()["items"]
        if item["id"] not in {old["id"] for old in tasks_before}
    ]
    assert [(item["id"], item["kind"], item["transactionId"]) for item in new_tasks] == [
        (task["id"], "asset_ingest", None)
    ]


@pytest.mark.destructive
def test_two_browser_contexts_only_one_decision_wins_and_stale_token_is_409(
    browser, base_url, pending_review_target
):
    project_id = pending_review_target["projectId"]
    transaction_id = pending_review_target["transactionId"]
    api_path = (
        f"/api/creator/projects/{project_id}/transactions/{transaction_id}/review"
    )
    context_a = browser.new_context(base_url=base_url)
    context_b = browser.new_context(base_url=base_url)
    try:
        tab_a = context_a.new_page()
        tab_b = context_b.new_page()
        tab_a.goto(f"/#/project/{project_id}/plan")
        tab_b.goto(f"/#/project/{project_id}/plan")

        manifest_a = _browser_fetch(tab_a, api_path)
        manifest_b = _browser_fetch(tab_b, api_path)
        assert manifest_a["status"] == manifest_b["status"] == 200
        pending_a = [
            item
            for item in manifest_a["body"]["decisionGroups"]
            if item["decision"] == "PENDING"
        ]
        pending_b = [
            item
            for item in manifest_b["body"]["decisionGroups"]
            if item["decision"] == "PENDING"
        ]
        assert len(pending_a) >= 2
        group = pending_a[0]
        copy_b = next(item for item in pending_b if item["id"] == group["id"])
        assert copy_b["decisionToken"] == group["decisionToken"]
        decision_path = f"{api_path}/groups/{group['id']}/decision"

        winner = _browser_fetch(
            tab_a,
            decision_path,
            method="PUT",
            body={"decisionToken": group["decisionToken"], "decision": "ACCEPT"},
            key=f"e2e-tab-a-{uuid4()}",
        )
        stale = _browser_fetch(
            tab_b,
            decision_path,
            method="PUT",
            body={"decisionToken": copy_b["decisionToken"], "decision": "REJECT"},
            key=f"e2e-tab-b-{uuid4()}",
        )
        assert winner["status"] == 200, winner
        assert stale["status"] == 409, stale
        assert stale["body"]["code"] == "CONFLICT"

        current = _browser_fetch(tab_b, api_path)
        assert current["status"] == 200
        decided = next(
            item
            for item in current["body"]["decisionGroups"]
            if item["id"] == group["id"]
        )
        assert decided["decision"] == "ACCEPTED_APPLIED"
        assert any(
            item["decision"] == "PENDING"
            for item in current["body"]["decisionGroups"]
        )
    finally:
        context_a.close()
        context_b.close()
