# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from domain.enums import SpecialistRole


@dataclass(frozen=True, slots=True)
class TargetExpectation:
    ref: str
    object_version: str | None = None
    slot_generation: int | None = None


@dataclass(frozen=True, slots=True)
class SpecialistRunInput:
    run_id: str
    project_id: str
    creator_session_id: str
    transaction_id: str
    role: SpecialistRole
    target_refs: tuple[str, ...]
    context_refs: tuple[str, ...]
    exact_user_intent: str
    source_message_seqs: tuple[int, ...]
    base_revision_id: str
    observed_working_head: str
    target_expectations: tuple[TargetExpectation, ...] = ()
    input_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeMutationRequestDraft:
    kind: Literal[
        "create_path",
        "write_multi_files",
        "move_path",
        "delete_path",
        "set_reference",
        "set_multi_references",
        "select_artifact_version",
    ]
    target_ref: str
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeExecutionRequestDraft:
    kind: Literal["image_generation", "r2v_generation", "ai_edit", "compose"]
    target_ref: str
    input_refs: tuple[str, ...]
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SpecialistDelegateRequest:
    """Creator-authored fields for one durable, isolated SpecialistRun.

    Governance fields are supplied by Runtime and persisted with the Run.  In
    particular, the Creator model never supplies a read-set, branch head,
    target expectation, or media Task id.
    """

    project_id: str
    creator_session_id: str
    goal_id: str
    transaction_id: str
    role: SpecialistRole
    target_refs: tuple[str, ...]
    context_refs: tuple[str, ...]
    exact_user_intent: str
    task: str
    success_criteria: str
    source_message_seqs: tuple[int, ...]
    base_revision_id: str
    observed_working_head: str
    input_fingerprint: str
    idempotency_key: str
    target_expectations: tuple[TargetExpectation, ...] = ()
    native_media_parts: tuple[Mapping[str, Any], ...] = ()
    service_invocation: Mapping[str, Any] | None = None
    related_run_id: str | None = None
    supersedes_run_id: str | None = None
    run_id: str | None = None

    def run_input(self, run_id: str) -> SpecialistRunInput:
        return SpecialistRunInput(
            run_id=run_id,
            project_id=self.project_id,
            creator_session_id=self.creator_session_id,
            transaction_id=self.transaction_id,
            role=self.role,
            target_refs=self.target_refs,
            context_refs=self.context_refs,
            exact_user_intent=self.exact_user_intent,
            source_message_seqs=self.source_message_seqs,
            base_revision_id=self.base_revision_id,
            observed_working_head=self.observed_working_head,
            target_expectations=self.target_expectations,
            input_fingerprint=self.input_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class SpecialistAccepted:
    accepted: Literal[True]
    run_id: str
    role: SpecialistRole
    status: str


@dataclass(frozen=True, slots=True)
class ResolvedNativeContext:
    """Current target text, native media, and version observations for one turn."""

    content_parts: tuple[Any, ...] = ()
    read_set: tuple[Mapping[str, Any], ...] = ()
    media_manifest: tuple[Mapping[str, Any], ...] = ()
    text_context: str = ""
