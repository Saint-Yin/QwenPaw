"""Typed workspace mutation contracts for the new Text Workspace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
import re
from typing import Any

from domain.errors import ValidationError
from domain.ids import new_id, utc_now_iso

from .content_store import validate_sha256


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


class MutationKind(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"
    RENAME = "rename"
    REPLACE_MEDIA = "replace_media"
    CHANGE_REFERENCE = "change_reference"


class MutationActor(StrEnum):
    USER = "user"
    CREATOR_AGENT = "creator_agent"
    SUBAGENT = "subagent"
    SYSTEM = "system"


def safe_workspace_path(value: str) -> str:
    """Validate an Agent-facing POSIX relative path without normalizing escape attempts."""
    if not isinstance(value, str):
        raise ValidationError("workspace path 必须是字符串")
    raw = value
    if (
        not raw
        or raw != raw.strip()
        or raw.startswith(("/", "\\"))
        or "\\" in raw
        or "\x00" in raw
        or _WINDOWS_DRIVE_RE.match(raw)
    ):
        raise ValidationError(f"非法 workspace path: {value!r}")
    raw_parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValidationError(f"非法 workspace path: {value!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw:
        raise ValidationError(f"非法 workspace path: {value!r}")
    return raw


def safe_storage_segment(value: str, *, label: str = "storage id") -> str:
    """Validate an identifier before it becomes a private-store path segment."""
    raw = value if isinstance(value, str) else ""
    if not _SAFE_SEGMENT_RE.fullmatch(raw) or raw in {".", ".."}:
        raise ValidationError(f"非法 {label}: {value!r}")
    return raw


def is_media_ref(value: str | None) -> bool:
    ref = (value or "").strip()
    return ref.startswith(("asset://", "artifact://"))


def classify_content_change(path: str, before_text: str | None, after_text: str | None) -> MutationKind:
    normalized = safe_workspace_path(path)
    if before_text is None:
        return MutationKind.CREATE
    if after_text is None:
        return MutationKind.DELETE
    if normalized.endswith(".ref"):
        if is_media_ref(before_text) or is_media_ref(after_text):
            return MutationKind.REPLACE_MEDIA
        return MutationKind.CHANGE_REFERENCE
    return MutationKind.UPDATE


@dataclass(frozen=True, slots=True)
class MutationRecord:
    id: str
    seq: int
    project_id: str
    transaction_id: str
    actor: MutationActor
    kind: MutationKind
    target_ref: str
    path: str | None = None
    source_path: str | None = None
    destination_path: str | None = None
    before_blob_hash: str | None = None
    after_blob_hash: str | None = None
    actor_run_id: str | None = None
    trigger_message_seq: int | None = None
    parent_mutation_id: str | None = None
    dependency_reason: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        safe_storage_segment(self.id, label="mutation id")
        safe_storage_segment(self.project_id, label="project id")
        safe_storage_segment(self.transaction_id, label="transaction id")
        if self.seq < 0:
            raise ValidationError("mutation seq 不能小于 0")
        if not self.target_ref:
            raise ValidationError("mutation target_ref 不能为空")
        if self.trigger_message_seq is not None and self.trigger_message_seq < 0:
            raise ValidationError("trigger_message_seq 不能小于 0")
        if self.before_blob_hash is not None:
            validate_sha256(self.before_blob_hash)
        if self.after_blob_hash is not None:
            validate_sha256(self.after_blob_hash)

        if self.kind in {MutationKind.MOVE, MutationKind.RENAME}:
            if not self.source_path or not self.destination_path:
                raise ValidationError("move/rename mutation 必须包含 source_path 和 destination_path")
            safe_workspace_path(self.source_path)
            safe_workspace_path(self.destination_path)
            if self.source_path == self.destination_path:
                raise ValidationError("move/rename 的 source 和 destination 不能相同")
        else:
            if not self.path:
                raise ValidationError(f"{self.kind.value} mutation 必须包含 path")
            safe_workspace_path(self.path)

        if self.kind is MutationKind.CREATE:
            if self.before_blob_hash is not None or self.after_blob_hash is None:
                raise ValidationError("create mutation 必须只有 after_blob_hash")
        elif self.kind is MutationKind.DELETE:
            if self.before_blob_hash is None or self.after_blob_hash is not None:
                raise ValidationError("delete mutation 必须只有 before_blob_hash")
        elif self.kind in {
            MutationKind.UPDATE,
            MutationKind.REPLACE_MEDIA,
            MutationKind.CHANGE_REFERENCE,
        }:
            if self.before_blob_hash is None or self.after_blob_hash is None:
                raise ValidationError(f"{self.kind.value} mutation 必须包含 before/after blob hash")

    @property
    def affected_paths(self) -> tuple[str, ...]:
        if self.kind in {MutationKind.MOVE, MutationKind.RENAME}:
            return (self.source_path or "", self.destination_path or "")
        return (self.path or "",)


def new_mutation(
    *,
    project_id: str,
    transaction_id: str,
    actor: MutationActor | str,
    kind: MutationKind | str,
    target_ref: str,
    path: str | None = None,
    source_path: str | None = None,
    destination_path: str | None = None,
    before_blob_hash: str | None = None,
    after_blob_hash: str | None = None,
    actor_run_id: str | None = None,
    trigger_message_seq: int | None = None,
    parent_mutation_id: str | None = None,
    dependency_reason: str | None = None,
) -> MutationRecord:
    return MutationRecord(
        id=new_id("mutation"),
        seq=0,
        project_id=project_id,
        transaction_id=transaction_id,
        actor=MutationActor(actor),
        kind=MutationKind(kind),
        target_ref=target_ref,
        path=path,
        source_path=source_path,
        destination_path=destination_path,
        before_blob_hash=before_blob_hash,
        after_blob_hash=after_blob_hash,
        actor_run_id=actor_run_id,
        trigger_message_seq=trigger_message_seq,
        parent_mutation_id=parent_mutation_id,
        dependency_reason=dependency_reason,
        created_at=utc_now_iso(),
    )


def database_mutation_kind(record: MutationRecord) -> str:
    """Return the frozen Journal kind, preserving ref BIND/UNBIND semantics."""

    reference_change = any(path.endswith(".ref") for path in record.affected_paths)
    if reference_change:
        if record.kind is MutationKind.DELETE:
            return "UNBIND"
        if record.kind in {
            MutationKind.CREATE,
            MutationKind.UPDATE,
            MutationKind.REPLACE_MEDIA,
            MutationKind.CHANGE_REFERENCE,
        }:
            return "BIND"
    return {
        MutationKind.CREATE: "CREATE",
        MutationKind.UPDATE: "UPDATE",
        MutationKind.DELETE: "DELETE",
        MutationKind.MOVE: "MOVE",
        MutationKind.RENAME: "RENAME",
        MutationKind.REPLACE_MEDIA: "BIND",
        MutationKind.CHANGE_REFERENCE: "BIND",
    }[record.kind]


def mutation_to_dict(record: MutationRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "seq": record.seq,
        "projectId": record.project_id,
        "transactionId": record.transaction_id,
        "actor": record.actor.value,
        "actorRunId": record.actor_run_id,
        "kind": record.kind.value,
        "targetRef": record.target_ref,
        "path": record.path,
        "sourcePath": record.source_path,
        "destinationPath": record.destination_path,
        "beforeBlobHash": record.before_blob_hash,
        "afterBlobHash": record.after_blob_hash,
        "triggerMessageSeq": record.trigger_message_seq,
        "parentMutationId": record.parent_mutation_id,
        "dependencyReason": record.dependency_reason,
        "createdAt": record.created_at,
    }


def mutation_from_dict(payload: dict[str, Any]) -> MutationRecord:
    return MutationRecord(
        id=str(payload["id"]),
        seq=int(payload["seq"]),
        project_id=str(payload["projectId"]),
        transaction_id=str(payload["transactionId"]),
        actor=MutationActor(payload["actor"]),
        actor_run_id=payload.get("actorRunId"),
        kind=MutationKind(payload["kind"]),
        target_ref=str(payload["targetRef"]),
        path=payload.get("path"),
        source_path=payload.get("sourcePath"),
        destination_path=payload.get("destinationPath"),
        before_blob_hash=payload.get("beforeBlobHash"),
        after_blob_hash=payload.get("afterBlobHash"),
        trigger_message_seq=payload.get("triggerMessageSeq"),
        parent_mutation_id=payload.get("parentMutationId"),
        dependency_reason=payload.get("dependencyReason"),
        created_at=str(payload.get("createdAt") or ""),
    )
