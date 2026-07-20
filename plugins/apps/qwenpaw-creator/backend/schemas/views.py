# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import Field

from domain.enums import CreatorProgressPhase, UiPhase

from .common import StrictModel

T = TypeVar("T")


class CreatorTaskProgress(StrictModel):
    goal_id: str | None = Field(None, alias="goalId")
    phase: CreatorProgressPhase
    label: str
    latest_milestone: str | None = Field(None, alias="latestMilestone")
    completed: int | None = None
    total: int | None = None
    section_id: str | None = Field(None, alias="sectionId")
    unit_id: str | None = Field(None, alias="unitId")
    source_event_seq: int = Field(0, alias="sourceEventSeq")
    updated_at: str = Field(alias="updatedAt")


class AgentStatusBadge(StrictModel):
    kind: str
    label: str
    count: int | None = None
    action_target: str | None = Field(None, alias="actionTarget")


class AgentStatusBarView(StrictModel):
    progress: CreatorTaskProgress
    activity: dict[str, Any] | None = None
    badges: list[AgentStatusBadge] = Field(default_factory=list)


class ViewEnvelope(StrictModel, Generic[T]):
    project_id: str = Field(alias="projectId")
    approved_revision_id: str = Field(alias="approvedRevisionId")
    working_branch_id: str | None = Field(None, alias="workingBranchId")
    working_head: str | None = Field(None, alias="workingHead")
    review_revision_id: str | None = Field(None, alias="reviewRevisionId")
    active_transaction_id: str | None = Field(
        None,
        alias="activeTransactionId",
    )
    ui_phase: UiPhase = Field(alias="uiPhase")
    manual_edit_overlay: dict[str, Any] | None = Field(
        None,
        alias="manualEditOverlay",
    )
    agent_status_bar: AgentStatusBarView = Field(alias="agentStatusBar")
    view: T
