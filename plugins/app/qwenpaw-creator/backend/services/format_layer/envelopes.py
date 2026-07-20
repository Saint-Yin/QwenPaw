"""Unified View envelopes from Runtime and immutable revision authorities."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from .errors import ProjectionInputError
from .inputs import (
    ProjectionSnapshots,
    ReviewPresentationState,
    RuntimeViewState,
    TextWorkspaceSnapshot,
)

_WORKING_PHASES = frozenset(
    {"executing", "interrupting", "waiting_input", "waiting_authorization", "finalizing"}
)
_OPTIONAL_WORKING_PHASES = frozenset({"executing", "interrupting", "waiting_input"})


def derive_ui_phase(session_status: str, transaction_status: str | None) -> str:
    """Apply the single documented Session/Transaction-to-UI mapping."""

    if session_status == "IDLE":
        return "idle"
    if session_status == "RUNNING":
        if transaction_status is None:
            # A follow-up Goal opens its Change Transaction lazily on the
            # first typed mutation or Specialist delegate.  Keep every View
            # readable from Approved Revision during that short boundary.
            return "executing"
        if transaction_status in {"COMPLETION_CHECK", "SEALING"}:
            return "finalizing"
        if transaction_status in {"ACTIVE", "REVISING"}:
            return "executing"
        raise ProjectionInputError("RUNNING session requires ACTIVE, REVISING, COMPLETION_CHECK, or SEALING")
    if session_status == "WAITING_RUNTIME":
        if transaction_status not in {"ACTIVE", "REVISING"}:
            raise ProjectionInputError("WAITING_RUNTIME requires an active or revising transaction")
        return "executing"
    if session_status == "INTERRUPT_REQUESTED":
        return "interrupting"
    if session_status == "WAITING_USER_INPUT":
        return "waiting_input"
    if session_status == "WAITING_EXECUTION_AUTH":
        return "waiting_authorization"
    if session_status == "PENDING_REVIEW":
        if transaction_status != "PENDING_REVIEW":
            raise ProjectionInputError("PENDING_REVIEW session and transaction must agree")
        return "waiting_review"
    if session_status == "RESUMING":
        return "resuming"
    if session_status == "CANCELLED":
        return "cancelled"
    if session_status == "ERROR":
        return "error"
    raise ProjectionInputError(f"unknown Creator Session status: {session_status}")


def build_review_presentation_view(
    view: Mapping[str, Any],
    state: ReviewPresentationState,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "presentationVersion": state.presentation_version,
        "reviewRevisionId": state.review_revision_id,
        "approvedRevisionId": state.approved_revision_id,
        "view": deepcopy(dict(view)),
        "origins": dict(state.origins),
        "targetVersions": {
            target_ref: metadata.to_view()
            for target_ref, metadata in state.target_versions.items()
        },
    }
    if state.overlay_id is not None:
        result["overlayId"] = state.overlay_id
        result["overlayHead"] = state.overlay_head
    return result


def _assert_snapshot_project(snapshot: TextWorkspaceSnapshot, project_id: str, *, label: str) -> None:
    if snapshot.project_id != project_id:
        raise ProjectionInputError(f"{label} snapshot belongs to a different project")


def build_view_envelope(
    runtime: RuntimeViewState,
    snapshots: ProjectionSnapshots,
    builder: Callable[[TextWorkspaceSnapshot], Mapping[str, Any]],
    *,
    review_presentation: ReviewPresentationState | None = None,
) -> dict[str, Any]:
    """Select the correct authority and project one page without storing it."""

    _assert_snapshot_project(snapshots.approved, runtime.project_id, label="approved")
    if snapshots.approved.revision_id != runtime.approved_revision_id:
        raise ProjectionInputError("approved snapshot and Runtime pointer do not match")
    phase = derive_ui_phase(runtime.session_status, runtime.transaction_status)

    if phase == "waiting_review":
        if review_presentation is None or snapshots.review_presentation is None:
            raise ProjectionInputError("review phase requires presentation metadata and an effective snapshot")
        _assert_snapshot_project(snapshots.review_presentation, runtime.project_id, label="review presentation")
        if review_presentation.approved_revision_id != runtime.approved_revision_id:
            raise ProjectionInputError("review presentation has a stale approved revision")
        if review_presentation.review_revision_id != runtime.review_revision_id:
            raise ProjectionInputError("review presentation and Runtime review pointer do not match")
        raw_view = builder(snapshots.review_presentation)
        view: Mapping[str, Any] = build_review_presentation_view(raw_view, review_presentation)
    elif phase in _WORKING_PHASES:
        has_working_metadata = bool(
            runtime.working_branch_id
            and runtime.working_head
            and runtime.active_transaction_id
        )
        if snapshots.working is not None and has_working_metadata:
            _assert_snapshot_project(snapshots.working, runtime.project_id, label="working")
            view = builder(snapshots.working)
        elif (
            phase in _OPTIONAL_WORKING_PHASES
            and snapshots.working is None
            and not runtime.working_branch_id
            and not runtime.working_head
            and not runtime.active_transaction_id
        ):
            # A read-only question or a hard stop requested before the first
            # mutation has no Working Branch.  The UI must remain readable
            # from the current Approved Revision while writes stay gated.
            view = builder(snapshots.approved)
        else:
            raise ProjectionInputError(
                f"{phase} phase requires a complete working snapshot/metadata set"
            )
    else:
        view = builder(snapshots.approved)

    envelope: dict[str, Any] = {
        "projectId": runtime.project_id,
        "approvedRevisionId": runtime.approved_revision_id,
        "workingBranchId": runtime.working_branch_id,
        "workingHead": runtime.working_head,
        "reviewRevisionId": runtime.review_revision_id,
        "activeTransactionId": runtime.active_transaction_id,
        "uiPhase": phase,
        "manualEditOverlay": runtime.manual_edit_overlay.to_view() if runtime.manual_edit_overlay else None,
        "agentStatusBar": deepcopy(dict(runtime.agent_status_bar)),
        "view": deepcopy(dict(view)),
    }
    return envelope


def build_historical_view_envelope(
    snapshot: TextWorkspaceSnapshot,
    builder: Callable[[TextWorkspaceSnapshot], Mapping[str, Any]],
    *,
    agent_status_bar: Mapping[str, Any],
) -> dict[str, Any]:
    """Project an immutable revision with no mutable branch or review controls."""

    return {
        "projectId": snapshot.project_id,
        "approvedRevisionId": snapshot.revision_id,
        "workingBranchId": None,
        "workingHead": None,
        "reviewRevisionId": None,
        "activeTransactionId": None,
        "uiPhase": "idle",
        "manualEditOverlay": None,
        "agentStatusBar": deepcopy(dict(agent_status_bar)),
        "view": deepcopy(dict(builder(snapshot))),
    }
