# -*- coding: utf-8 -*-
"""§13.4 scenarios 13/14 through the only public Creator HTTP surface."""
from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.security]


def _presentation(envelope: dict) -> dict:
    value = envelope["view"]
    return value["view"] if "presentationVersion" in value else value


def _command(
    command_id: str,
    command_type: str,
    target_ref: str,
    arguments: dict,
    *,
    target_version: str | None = None,
    **extra,
) -> dict:
    payload = {
        "clientCommandId": command_id,
        "type": command_type,
        "targetRef": target_ref,
        "arguments": arguments,
        "context": {},
        "expectedTargetVersions": [],
    }
    if target_version is not None:
        payload["expectedTargetVersions"] = [
            {"ref": target_ref, "objectVersion": target_version}
        ]
    payload.update(extra)
    return payload


def _interrupt_quietly(api, project_id: str) -> None:
    key = f"e2e-stop-{uuid4()}"
    api.post(
        f"/projects/{project_id}/interrupt",
        json={},
        headers={"Idempotency-Key": key},
    )


def test_old_http_routes_and_old_payloads_have_no_fallback(api, cutover_ids):
    project = api.create_project(f"E2E no fallback {uuid4().hex[:8]}")
    project_id = project["projectId"]
    try:
        old_requests = (
            ("get", "/agent/sessions", None, 404),
            ("post", "/run", {}, 404),
            ("post", "/ai/generate-image", {}, 404),
            ("post", f"/projects/{project_id}/runs", {}, 404),
            (
                "post",
                f"/projects/{project_id}/proposals/proposal-old/apply",
                {},
                404,
            ),
        )
        for method, path, body, expected in old_requests:
            response = getattr(api, method)(path, json=body) if body is not None else getattr(api, method)(path)
            assert response.status_code == expected, (method, path, response.text)

        whole_project = api.session.put(
            f"{api.base}/projects/{project_id}",
            json={"name": "legacy whole-project update"},
            timeout=30,
        )
        assert whole_project.status_code == 404, whole_project.text

        legacy_project_id = f"legacy-project-{uuid4()}"
        legacy_project = api.post(
            "/projects",
            json={
                "clientRequestId": legacy_project_id,
                "name": "legacy payload",
                "scenario": "general",
                "task_type": "t2v",
            },
            headers={"Idempotency-Key": legacy_project_id},
        )
        assert legacy_project.status_code == 422, legacy_project.text

        unknown = _command(
            f"unknown-{uuid4()}",
            "SET_SECTION_TEXT_LEGACY",
            "project:plan",
            {},
        )
        unknown_response = api.command(project_id, unknown)
        assert unknown_response.status_code == 400, unknown_response.text

        # Use an existing, IDLE cutover Section so the invalid command can be
        # rejected before any valid mutation wakes the asynchronous Creator
        # runtime.  The fixture remains byte-for-byte unchanged at the public
        # View/Session/Transaction boundary.
        cutover_project = cutover_ids["r2v_project"]
        section_id = cutover_ids["r2v_section"]
        cutover_plan_before = _presentation(api.view(cutover_project, "plan"))
        section = next(
            item for item in cutover_plan_before["sections"] if item["id"] == section_id
        )
        session_before = api.get(f"/projects/{cutover_project}/session").json()
        transaction_before = api.get(
            f"/projects/{cutover_project}/transactions/active"
        ).json()
        legacy_key = _command(
            f"legacy-task-type-{uuid4()}",
            "CREATE_UNIT",
            f"section:{section_id}",
            {
                "title": "must not be created",
                "unitId": f"legacy-unit-{uuid4().hex}",
                "task_type": "r2v",
                "duration": 8,
            },
            target_version=section["targetVersion"],
        )
        legacy_key_response = api.command(cutover_project, legacy_key)
        assert legacy_key_response.status_code == 422, legacy_key_response.text
        assert legacy_key_response.json()["code"] == "VALIDATION_ERROR"

        legacy_value = _command(
            f"legacy-t2v-{uuid4()}",
            "CREATE_UNIT",
            f"section:{section_id}",
            {
                "title": "must not be created either",
                "unitId": f"legacy-t2v-unit-{uuid4().hex}",
                "taskType": "t2v",
                "duration": 8,
            },
            target_version=section["targetVersion"],
        )
        legacy_value_response = api.command(cutover_project, legacy_value)
        assert legacy_value_response.status_code == 422, legacy_value_response.text
        assert legacy_value_response.json()["code"] == "VALIDATION_ERROR"
        cutover_plan_after = _presentation(api.view(cutover_project, "plan"))
        assert cutover_plan_after == cutover_plan_before
        assert api.get(f"/projects/{cutover_project}/session").json() == session_before
        assert api.get(
            f"/projects/{cutover_project}/transactions/active"
        ).json() == transaction_before
    finally:
        _interrupt_quietly(api, project_id)
        api.delete_project(project_id)


def test_project_and_asset_idempotency_replay_exactly_and_reject_drift(api):
    key = f"e2e-idempotency-{uuid4()}"
    payload = {
        "clientRequestId": key,
        "name": "Idempotent project",
        "description": "same key, same payload",
        "scenario": "general",
        "aspectRatio": "16:9",
        "resolution": "720P",
        "contentType": None,
    }
    first = api.post("/projects", json=payload, headers={"Idempotency-Key": key})
    replay = api.post("/projects", json=payload, headers={"Idempotency-Key": key})
    drift = api.post(
        "/projects",
        json={**payload, "name": "different payload"},
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert drift.status_code == 409, drift.text
    project_id = first.json()["projectId"]

    delete_key = f"e2e-idempotent-delete-{uuid4()}"
    deleted = api.delete(
        f"/projects/{project_id}", headers={"Idempotency-Key": delete_key}
    )
    delete_replay = api.delete(
        f"/projects/{project_id}", headers={"Idempotency-Key": delete_key}
    )
    assert deleted.status_code == delete_replay.status_code == 204
    assert api.get(f"/projects/{project_id}/header").status_code == 404


def test_path_cross_project_ref_forged_artifact_and_role_write_are_rejected(api):
    source = api.create_project(f"E2E source authority {uuid4().hex[:8]}")
    target = api.create_project(f"E2E target authority {uuid4().hex[:8]}")
    source_id, target_id = source["projectId"], target["projectId"]
    ingest_key = f"e2e-cross-ref-{uuid4()}"
    upload = {
        "file": ("cross-project.txt", b"source authority", "text/plain")
    }
    data = {"clientRequestId": ingest_key, "postIngestAction": "NONE"}
    try:
        ingested = api.post_file(
            f"/projects/{source_id}/assets",
            files=upload,
            data=data,
            headers={"Idempotency-Key": ingest_key},
        )
        replay = api.post_file(
            f"/projects/{source_id}/assets",
            files=upload,
            data=data,
            headers={"Idempotency-Key": ingest_key},
        )
        drift = api.post_file(
            f"/projects/{source_id}/assets",
            files={"file": ("cross-project.txt", b"changed bytes", "text/plain")},
            data=data,
            headers={"Idempotency-Key": ingest_key},
        )
        assert ingested.status_code == replay.status_code == 202
        assert ingested.json()["taskId"] == replay.json()["taskId"]
        assert drift.status_code == 409, drift.text

        accepted = ingested.json()
        task = api.wait_task(source_id, accepted["taskId"])
        assert task["status"] == "SUCCEEDED", task
        version_id = accepted.get("assetVersionId") or task["resultRefs"][0].split(":", 1)[1]
        asset_id = accepted["assetId"]

        own_content = api.get(
            f"/projects/{source_id}/assets/{asset_id}/content",
            params={"versionId": version_id},
        )
        foreign_content = api.get(
            f"/projects/{target_id}/assets/{asset_id}/content",
            params={"versionId": version_id},
        )
        assert own_content.status_code == 200
        assert own_content.content == b"source authority"
        assert foreign_content.status_code == 404, foreign_content.text

        traversal = _command(
            f"path-escape-{uuid4()}",
            "CREATE_SECTION",
            "project:../plan",
            {"title": "escape", "sectionId": "../../escape"},
        )
        traversal_response = api.command(target_id, traversal)
        assert traversal_response.status_code == 422, traversal_response.text
        assert traversal_response.json()["code"] == "VALIDATION_ERROR"

        generated_escape = api.get(
            "/generated/task-work/%2e%2e/%2e%2e/.env"
        )
        assert generated_escape.status_code == 404, generated_escape.text

        cross_ref = f"asset://{asset_id}@{version_id}"
        cross_attach = _command(
            f"cross-project-attach-{uuid4()}",
            "ATTACH_SOURCE_ASSETS",
            "project:assets",
            {"assetVersionRefs": [cross_ref]},
            target_version=_presentation(api.view(target_id, "assets"))["targetVersion"],
        )
        cross_response = api.command(target_id, cross_attach)
        assert cross_response.status_code == 404, cross_response.text

        forged_artifact = _command(
            f"forged-artifact-{uuid4()}",
            "SELECT_ARTIFACT_VERSION",
            "project:plan",
            {
                "slotId": "forged-slot",
                "artifactVersionId": "forged-version",
                "artifactRef": "artifact://forged-slot@forged-version",
            },
            target_version=_presentation(api.view(target_id, "plan"))["targetVersion"],
        )
        forged_response = api.command(target_id, forged_artifact)
        assert forged_response.status_code == 404, forged_response.text

        role_write = api.post(
            f"/projects/{target_id}/specialist-runs",
            json={"role": "review_consistency_agent", "targetRefs": ["project:plan"]},
        )
        assert role_write.status_code == 405, role_write.text
    finally:
        _interrupt_quietly(api, target_id)
        api.delete_project(source_id)
        api.delete_project(target_id)
