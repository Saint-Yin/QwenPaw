# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from domain.enums import ReviewDecisionCommand

from .common import StrictModel


class ReviewSelection(StrictModel):
    field: str
    text: str


class ReviewDecisionRequest(StrictModel):
    decision_token: str = Field(alias="decisionToken")
    decision: ReviewDecisionCommand
    instruction: str | None = None
    selection: ReviewSelection | None = None


class ReviewCommentRequest(StrictModel):
    client_comment_id: str = Field(alias="clientCommentId")
    text: str
    selection: dict[str, Any] | None = None


class JournalSeqRange(StrictModel):
    from_exclusive: int = Field(alias="fromExclusive", ge=0)
    to_inclusive: int = Field(alias="toInclusive", ge=0)


class ReviewOperationView(StrictModel):
    id: str
    decision_group_id: str = Field(alias="decisionGroupId")
    mutation_ids: list[str] = Field(alias="mutationIds")
    kind: Literal[
        "create",
        "update",
        "delete",
        "move",
        "rename",
        "replace_media",
        "change_reference",
    ]
    target_ref: str = Field(alias="targetRef")
    artifact_kind: str = Field(alias="artifactKind")
    path: str | None = None
    before_version_ref: str | None = Field(None, alias="beforeVersionRef")
    after_version_ref: str | None = Field(None, alias="afterVersionRef")
    causal_refs: list[str] = Field(alias="causalRefs")
    source: Literal[
        "user_direct",
        "dependency_cascade",
        "system_derived_content",
    ]
    actor_run_ids: list[str] = Field(alias="actorRunIds")
    trigger_message_seqs: list[int] = Field(alias="triggerMessageSeqs")
    dependency_reasons: list[str] = Field(alias="dependencyReasons")
    ui_locator: dict[str, str] | None = Field(None, alias="uiLocator")


ReviewDecisionState = Literal[
    "PENDING",
    "ACCEPTED_APPLIED",
    "REJECTED",
    "REVISION_REQUESTED",
    "SUPERSEDED_BY_USER_EDIT",
    "CARRIED_FORWARD_TO_NEXT_ROUND",
]


class ReviewDecisionGroupView(StrictModel):
    id: str
    title: str
    operation_ids: list[str] = Field(alias="operationIds")
    grouping_reasons: list[str] = Field(alias="groupingReasons")
    decision_token: str = Field(alias="decisionToken")
    decision: ReviewDecisionState


ReviewMediaType = Literal["image", "video", "audio", "other"]
ReviewMediaCandidateState = Literal[
    "SELECTED",
    "PREVIOUSLY_SELECTED",
    "UNSELECTED_CANDIDATE",
    "SUPERSEDED",
    "HISTORICAL",
]


class ReviewMediaVersionView(StrictModel):
    version_ref: str = Field(alias="versionRef")
    version_kind: Literal["asset", "artifact"] = Field(alias="versionKind")
    version_id: str = Field(alias="versionId")
    owner_id: str = Field(alias="ownerId")
    version: int = Field(ge=1)
    media_type: ReviewMediaType = Field(alias="mediaType")
    mime_type: str | None = Field(None, alias="mimeType")
    artifact_kind: str | None = Field(None, alias="artifactKind")
    target_ref: str | None = Field(None, alias="targetRef")
    checksum: str
    duration_seconds: float | None = Field(None, alias="durationSeconds", ge=0)
    created_by: str | None = Field(None, alias="createdBy")
    created_at: str = Field(alias="createdAt")
    provenance_refs: list[str] = Field(alias="provenanceRefs")
    input_fingerprint: str | None = Field(None, alias="inputFingerprint")
    model_run_id: str | None = Field(None, alias="modelRunId")
    selected_in_base_revision: bool = Field(alias="selectedInBaseRevision")
    selected_in_review_revision: bool = Field(alias="selectedInReviewRevision")
    candidate_state: ReviewMediaCandidateState = Field(alias="candidateState")


class MediaComparisonView(StrictModel):
    id: str
    operation_ids: list[str] = Field(alias="operationIds")
    target_ref: str = Field(alias="targetRef")
    path: str | None = None
    change_kind: Literal[
        "create",
        "delete",
        "replace_media",
        "change_reference",
        "move",
        "rename",
        "candidate",
    ] = Field(alias="changeKind")
    before: ReviewMediaVersionView | None = None
    after: ReviewMediaVersionView | None = None
    candidates: list[ReviewMediaVersionView]
    input_storyboard_refs: list[str] = Field(alias="inputStoryboardRefs")
    source_refs: list[str] = Field(alias="sourceRefs")


class IntegrationPreviewView(StrictModel):
    id: str
    scope: Literal["timeline", "project"]
    target_ref: str = Field(alias="targetRef")
    title: str
    operation_ids: list[str] = Field(alias="operationIds")
    before: ReviewMediaVersionView | None = None
    after: ReviewMediaVersionView | None = None
    affected_refs: list[str] = Field(alias="affectedRefs")
    ui_locator: dict[str, str] = Field(alias="uiLocator")


class ReviewManifestView(StrictModel):
    id: str
    transaction_id: str = Field(alias="transactionId")
    review_round: int = Field(alias="reviewRound", ge=1)
    base_revision_id: str = Field(alias="baseRevisionId")
    review_revision_id: str = Field(alias="reviewRevisionId")
    manifest_token: str = Field(alias="manifestToken")
    summary: str
    journal_seq_range: JournalSeqRange = Field(alias="journalSeqRange")
    decision_groups: list[ReviewDecisionGroupView] = Field(
        alias="decisionGroups",
    )
    operations: list[ReviewOperationView]
    created_artifact_version_refs: list[str] = Field(
        alias="createdArtifactVersionRefs",
    )
    media_comparisons: list[MediaComparisonView] = Field(
        alias="mediaComparisons",
    )
    integration_previews: list[IntegrationPreviewView] = Field(
        alias="integrationPreviews",
    )
    created_at: str = Field(alias="createdAt")


class ReviewDecisionResponse(StrictModel):
    group: ReviewDecisionGroupView
    approved_revision_id: str | None = Field(None, alias="approvedRevisionId")
    manifest: ReviewManifestView


class ReviewOperationContentView(StrictModel):
    operation_id: str = Field(alias="operationId")
    before_version_ref: str | None = Field(None, alias="beforeVersionRef")
    after_version_ref: str | None = Field(None, alias="afterVersionRef")
    before: str | None = None
    after: str | None = None
    content_type: str = Field(alias="contentType")
