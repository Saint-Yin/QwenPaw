from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from domain.enums import CreatorCommandType

from .common import ExpectedTargetVersion, StrictModel


class CreatorCommandRequest(StrictModel):
    client_command_id: str = Field(alias="clientCommandId")
    edit_session_id: str | None = Field(None, alias="editSessionId")
    type: CreatorCommandType
    target_ref: str = Field(alias="targetRef")
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    expected_target_versions: list[ExpectedTargetVersion] = Field(default_factory=list, alias="expectedTargetVersions")
    expected_presentation_version: str | None = Field(None, alias="expectedPresentationVersion")
    expected_decision_token: str | None = Field(None, alias="expectedDecisionToken")
    expected_overlay_head: str | None = Field(None, alias="expectedOverlayHead")


class CreatorCommandAccepted(StrictModel):
    command_id: str = Field(alias="commandId")
    status: Literal[
        "RECEIVED",
        "APPLIED",
        "QUEUED",
        "DEFERRED_UNTIL_REVIEW_RESOLVED",
        "CONSUMED",
        "REJECTED",
    ]
    event_seq: int = Field(alias="eventSeq", ge=0)
    transaction_id: str | None = Field(None, alias="transactionId")
    message_seq: int | None = Field(None, alias="messageSeq", ge=1)
    working_head: str | None = Field(None, alias="workingHead")
