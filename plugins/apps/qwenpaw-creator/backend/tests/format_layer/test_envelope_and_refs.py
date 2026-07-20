# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

from dataclasses import replace

import pytest

from services.format_layer import (
    ManualEditOverlayRecord,
    ProjectionInputError,
    ProjectionSnapshots,
    ReviewPresentationState,
    ReviewTargetMetadata,
    RuntimeViewState,
    TextWorkspaceSnapshot,
    WorkspaceFile,
    build_historical_view_envelope,
    build_plan_view,
    build_ref_index,
    build_review_view,
    build_view_envelope,
    derive_ui_phase,
)

STATUS = {
    "progress": {
        "goalId": "goal-7",
        "phase": "unit_production",
        "label": "正在制作 R2V Unit 1/2",
        "sourceEventSeq": 41,
        "updatedAt": "2026-07-10T02:00:00Z",
    },
    "activity": {"label": "1 个任务等待媒体", "runningTaskCount": 1},
    "badges": [],
}


def _runtime(**changes):
    values = {
        "project_id": "p1",
        "approved_revision_id": "revision-17",
        "session_status": "RUNNING",
        "transaction_status": "ACTIVE",
        "agent_status_bar": STATUS,
        "working_branch_id": "branch-4",
        "working_head": "head-48",
        "active_transaction_id": "change-123",
    }
    values.update(changes)
    return RuntimeViewState(**values)


def test_waiting_runtime_maps_to_executing_and_uses_working_snapshot(
    projection_fixture,
):
    fixture = projection_fixture
    working = TextWorkspaceSnapshot(
        project_id="p1",
        revision_id="revision-17",
        files={
            **fixture.snapshot.files,
            "title.txt": replace(
                fixture.snapshot.files["title.txt"],
                content="Working title",
            ),
        },
        target_versions=fixture.snapshot.target_versions,
    )
    runtime = _runtime(session_status="WAITING_RUNTIME")
    envelope = build_view_envelope(
        runtime,
        ProjectionSnapshots(approved=fixture.snapshot, working=working),
        lambda snapshot: {"title": snapshot.text("title.txt", required=True)},
    )
    assert derive_ui_phase("WAITING_RUNTIME", "ACTIVE") == "executing"
    assert envelope["uiPhase"] == "executing"
    assert envelope["view"] == {"title": "Working title"}
    assert envelope["agentStatusBar"]["activity"]["label"] == "1 个任务等待媒体"


@pytest.mark.parametrize(
    ("session_status", "expected_phase"),
    [
        ("INTERRUPT_REQUESTED", "interrupting"),
        ("WAITING_USER_INPUT", "waiting_input"),
    ],
)
def test_non_mutating_boundary_phase_keeps_approved_view_readable(
    projection_fixture,
    session_status,
    expected_phase,
):
    fixture = projection_fixture
    runtime = _runtime(
        session_status=session_status,
        transaction_status=None,
        working_branch_id=None,
        working_head=None,
        active_transaction_id=None,
    )
    envelope = build_view_envelope(
        runtime,
        ProjectionSnapshots(approved=fixture.snapshot),
        lambda snapshot: {"title": snapshot.text("title.txt", required=True)},
    )

    assert envelope["uiPhase"] == expected_phase
    assert envelope["view"] == {
        "title": fixture.snapshot.text("title.txt", required=True),
    }


def test_running_followup_goal_without_lazy_transaction_keeps_approved_view_readable(
    projection_fixture,
):
    fixture = projection_fixture
    runtime = _runtime(
        session_status="RUNNING",
        transaction_status=None,
        working_branch_id=None,
        working_head=None,
        active_transaction_id=None,
    )
    envelope = build_view_envelope(
        runtime,
        ProjectionSnapshots(approved=fixture.snapshot),
        lambda snapshot: {"title": snapshot.text("title.txt", required=True)},
    )

    assert derive_ui_phase("RUNNING", None) == "executing"
    assert envelope["uiPhase"] == "executing"
    assert envelope["activeTransactionId"] is None
    assert envelope["view"] == {
        "title": fixture.snapshot.text("title.txt", required=True),
    }


def test_waiting_review_returns_presentation_with_origin_and_cas_metadata(
    projection_fixture,
):
    fixture = projection_fixture
    presentation_snapshot = TextWorkspaceSnapshot(
        project_id="p1",
        revision_id="review-revision-18",
        files=fixture.snapshot.files,
        target_versions={
            **fixture.snapshot.target_versions,
            "unit:u-r2v": "ov-review-u-r2v",
        },
    )
    runtime = _runtime(
        session_status="PENDING_REVIEW",
        transaction_status="PENDING_REVIEW",
        review_revision_id="review-revision-18",
        manual_edit_overlay=ManualEditOverlayRecord(
            "overlay-2",
            "overlay-head-3",
            1,
        ),
    )
    review_state = ReviewPresentationState(
        presentation_version="presentation-hash-8",
        review_revision_id="review-revision-18",
        approved_revision_id="revision-17",
        overlay_id="overlay-2",
        overlay_head="overlay-head-3",
        origins={
            "unit:u-r2v": "review_candidate",
            "unit:u-edit": "user_overlay",
            "section:s1": "approved",
        },
        target_versions={
            "unit:u-r2v": ReviewTargetMetadata(
                "ov-review-u-r2v",
                "group-1",
                "token-1",
            ),
            "unit:u-edit": ReviewTargetMetadata("ov-overlay-u-edit"),
            "section:s1": ReviewTargetMetadata("ov-section-s1-9"),
        },
    )
    envelope = build_view_envelope(
        runtime,
        ProjectionSnapshots(
            approved=fixture.snapshot,
            review_presentation=presentation_snapshot,
        ),
        lambda snapshot: build_plan_view(snapshot, fixture.catalogs),
        review_presentation=review_state,
    )
    assert envelope["uiPhase"] == "waiting_review"
    assert envelope["manualEditOverlay"] == {
        "id": "overlay-2",
        "head": "overlay-head-3",
        "mutationCount": 1,
    }
    presentation = envelope["view"]
    assert presentation["presentationVersion"] == "presentation-hash-8"
    assert presentation["origins"]["unit:u-r2v"] == "review_candidate"
    assert presentation["targetVersions"]["unit:u-r2v"] == {
        "targetVersion": "ov-review-u-r2v",
        "decisionGroupId": "group-1",
        "decisionToken": "token-1",
    }
    assert presentation["targetVersions"]["unit:u-edit"] == {
        "targetVersion": "ov-overlay-u-edit",
    }


def test_review_candidate_requires_decision_cas_metadata():
    with pytest.raises(ProjectionInputError, match="decision CAS metadata"):
        ReviewPresentationState(
            presentation_version="pv",
            review_revision_id="rv",
            approved_revision_id="av",
            origins={"unit:u1": "review_candidate"},
            target_versions={"unit:u1": ReviewTargetMetadata("ov")},
        )


def test_historical_revision_envelope_is_read_only(projection_fixture):
    fixture = projection_fixture
    envelope = build_historical_view_envelope(
        fixture.snapshot,
        lambda snapshot: {"title": snapshot.text("title.txt", required=True)},
        agent_status_bar=STATUS,
    )
    assert envelope["approvedRevisionId"] == "revision-17"
    assert envelope["workingBranchId"] is None
    assert envelope["activeTransactionId"] is None
    assert envelope["uiPhase"] == "idle"


def test_ref_index_search_is_server_projected_and_bounded(projection_fixture):
    fixture = projection_fixture
    index = build_ref_index(fixture.snapshot, fixture.catalogs)
    result = index.search("scene-a", types=["asset"], limit=10)
    assert len(result) == 1
    assert result[0]["assetVersionId"] == "av-scene-2"
    assert result[0]["uiLocator"] == {
        "page": "assets",
        "assetId": "scene-a",
        "versionId": "av-scene-2",
    }
    assert (
        index.resolve(fixture.artifacts["storyboard"].source_ref)[
            "artifactVersionId"
        ]
        == "sb-v4"
    )
    with pytest.raises(ProjectionInputError, match="between 1 and 100"):
        index.search(limit=101)


def test_ref_index_resolves_current_source_analysis(projection_fixture):
    fixture = projection_fixture
    analysis_ref = "analysis://av-video-7@run-source-1"
    snapshot = replace(
        fixture.snapshot,
        files={
            **fixture.snapshot.files,
            "sources/upload-video-01--product-demo/understanding/current.ref": (
                WorkspaceFile(analysis_ref, "ov-analysis-current")
            ),
        },
    )
    resolved = build_ref_index(snapshot, fixture.catalogs).resolve(
        analysis_ref,
    )
    assert resolved is not None
    assert resolved["type"] == "analysis"
    assert resolved["name"] == "product-demo.mp4 · 素材理解"
    assert resolved["assetVersionId"] == "av-video-7"


def test_review_view_keeps_manifest_locators_and_does_not_duplicate_operations():
    manifest = {
        "id": "manifest-1",
        "transactionId": "change-1",
        "reviewRevisionId": "review-1",
        "manifestToken": "manifest-token",
        "decisionGroups": [
            {
                "id": "group-1",
                "operationIds": ["op-1"],
                "decisionToken": "token-1",
                "decision": "PENDING",
            },
        ],
        "operations": [
            {
                "id": "op-1",
                "mutationIds": ["mutation-1", "mutation-2"],
                "targetRef": "unit:u-r2v",
                "uiLocator": {
                    "page": "workbench",
                    "unitId": "u-r2v",
                    "focus": "storyboard",
                },
            },
        ],
    }
    view = build_review_view(manifest)
    assert len(view["manifest"]["operations"]) == 1
    assert view["manifest"]["operations"][0]["mutationIds"] == [
        "mutation-1",
        "mutation-2",
    ]
    assert view["readiness"]["ready"] is True
    assert view["targetVersion"] == "manifest-token"
