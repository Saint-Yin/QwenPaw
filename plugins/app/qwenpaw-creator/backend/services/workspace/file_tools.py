"""The seven Agent-facing file tools over the versioned Text Workspace.

Reads resolve either a current Working Branch or an immutable Revision and add
every observed file version to a run-local read set.  Writes require a live
Runtime transaction/lease snapshot and go through one mutation gateway whose
contract is to commit the blob/tree change, typed journal row and event in one
atomic operation.

No method in this module opens a host path.  Directory operations, moves,
deletes and reference selection are intentionally absent from the tool map.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import PurePosixPath
import re
from typing import Literal, Protocol

from domain.enums import ShotCamera, ShotFraming, SpecialistRole, TransactionStatus
from domain.errors import (
    ConflictError,
    NotFoundError,
    PhaseConflictError,
    StorageIntegrityError,
    ValidationError,
)
from domain.refs import parse_target_ref

from .content_store import validate_sha256
from .mutations import safe_storage_segment
from .paths import (
    SEARCHABLE_SUFFIXES,
    compile_workspace_glob,
    join_workspace_glob,
    scope_contains_path,
    workspace_directory,
    workspace_glob,
    workspace_text_path,
)
from .permissions import FILE_TOOL_NAMES, PermissionRegistry
from .revision_store import RevisionEntry
from .text_store import TextStore, WorkspaceMutationResult


ViewKind = Literal["working", "revision"]

_DURATION_VALUE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?\s*s?$", re.IGNORECASE)
_CAMERA_VALUE_RE = re.compile(
    r"^(?P<camera>[^\n]+?)\s*\n+\s*画幅[：:]\s*(?P<framing>[^\n]+?)\s*$"
)


def bind_write_file_runtime_expectations(
    arguments: Mapping[str, object],
    current_entry: RevisionEntry | None,
) -> dict[str, object]:
    """Bind the CAS hidden behind the model-facing ``write_file`` contract.

    QwenPaw exposes only ``file_path`` and ``content`` to the model. Creator
    keeps its stronger atomic commit internally by resolving the target's
    current version after the writer lease has been acquired. Explicit legacy
    expectations remain untouched, except for the known provider encoding of
    two empty strings when the target is absent.
    """

    normalized = dict(arguments)
    has_blob = "expected_blob_hash" in normalized
    has_object = "expected_object_version" in normalized
    if (
        current_entry is None
        and has_blob
        and has_object
        and normalized["expected_blob_hash"] == ""
        and normalized["expected_object_version"] == ""
    ):
        normalized["expected_blob_hash"] = None
        normalized["expected_object_version"] = None
        return normalized
    if not has_blob:
        normalized["expected_blob_hash"] = (
            current_entry.blob_hash if current_entry is not None else None
        )
    if not has_object:
        normalized["expected_object_version"] = (
            current_entry.object_version if current_entry is not None else None
        )
    return normalized


def _shot_unit_route_path(path: str) -> str | None:
    marker = "/shots/"
    if PurePosixPath(path).name != "camera.md" or marker not in f"/{path}":
        return None
    return f"{path.split(marker, 1)[0]}/route.txt"


def _validate_projected_text(
    path: str,
    text: str,
    *,
    unit_route: str | None = None,
) -> None:
    """Keep every committed Agent value round-trippable by Format Layer."""

    leaf = PurePosixPath(path).name
    stripped = text.strip()
    if leaf == "title.txt" and (not stripped or "\n" in stripped or "\r" in stripped):
        raise ValidationError("title.txt 必须是非空单行文本", details={"path": path})
    if leaf in {
        "duration.txt",
        "duration-budget.txt",
    } and not _DURATION_VALUE_RE.fullmatch(stripped):
        raise ValidationError(
            f"{leaf} 必须只包含非负秒数（例如 8、20 或 8.5s）",
            details={"path": path},
        )
    if (
        leaf == "route.txt"
        and "/units/" in f"/{path}"
        and stripped
        not in {
            "r2v",
            "edit",
        }
    ):
        raise ValidationError(
            "Unit route.txt 只能逐字为 r2v 或 edit", details={"path": path}
        )
    if leaf == "camera.md" and "/shots/" in f"/{path}" and unit_route != "edit":
        match = _CAMERA_VALUE_RE.fullmatch(stripped)
        if match is None:
            raise ValidationError(
                "Shot camera.md 必须是运镜首行加独立的 画幅: 行",
                details={"path": path},
            )
        try:
            ShotCamera(match.group("camera").strip())
            ShotFraming(match.group("framing").strip())
        except ValueError as exc:
            raise ValidationError(
                "Shot camera/framing 不在冻结枚举中", details={"path": path}
            ) from exc


@dataclass(frozen=True, slots=True)
class ReadSetEntry:
    path: str
    blob_hash: str
    object_version: str
    view_kind: ViewKind
    view_id: str

    def __post_init__(self) -> None:
        workspace_text_path(self.path)
        validate_sha256(self.blob_hash)
        if not self.object_version:
            raise ValidationError("read-set object version 不能为空")
        safe_storage_segment(self.view_id, label="workspace view id")


class ReadSetAccumulator:
    """Monotonic, conflict-detecting run-local file observations."""

    def __init__(self) -> None:
        self._entries: dict[tuple[ViewKind, str, str], ReadSetEntry] = {}

    def record(self, entry: ReadSetEntry) -> None:
        key = (entry.view_kind, entry.view_id, entry.path)
        existing = self._entries.get(key)
        if existing is not None and (
            existing.blob_hash != entry.blob_hash
            or existing.object_version != entry.object_version
        ):
            raise ConflictError(
                "同一 Run 读取的 Workspace 文件版本已变化",
                details={
                    "reason": "READ_SET_CHANGED",
                    "path": entry.path,
                    "before": existing.object_version,
                    "after": entry.object_version,
                },
            )
        self._entries[key] = entry

    def replace(self, entry: ReadSetEntry) -> None:
        """Advance an entry after this same writer atomically changed it."""

        self._entries[(entry.view_kind, entry.view_id, entry.path)] = entry

    def snapshot(self) -> tuple[ReadSetEntry, ...]:
        return tuple(
            sorted(
                self._entries.values(),
                key=lambda item: (item.view_kind, item.view_id, item.path),
            )
        )

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True, slots=True)
class WorkspaceToolContext:
    project_id: str
    creator_session_id: str
    role: SpecialistRole | str
    working_branch_id: str | None = None
    revision_id: str | None = None
    transaction_id: str | None = None
    specialist_run_id: str | None = None
    writer_lease_id: str | None = None
    observed_working_head: str | None = None
    target_ref: str | None = None
    # The newest user message that was part of the writer's immutable input.
    # Persisting this on every mutation lets Review reconstruct an intervention
    # (generated text before the message versus revised text after it) without
    # guessing from prose or wall-clock ordering.
    trigger_message_seq: int | None = None
    read_set: ReadSetAccumulator = field(default_factory=ReadSetAccumulator)

    def __post_init__(self) -> None:
        safe_storage_segment(self.project_id, label="project id")
        safe_storage_segment(self.creator_session_id, label="creator session id")
        if (self.working_branch_id is None) == (self.revision_id is None):
            raise ValidationError("必须且只能选择 Working Branch 或 immutable Revision")
        if self.working_branch_id is not None:
            safe_storage_segment(self.working_branch_id, label="working branch id")
        if self.revision_id is not None:
            safe_storage_segment(self.revision_id, label="revision id")
        for value, label in (
            (self.transaction_id, "transaction id"),
            (self.specialist_run_id, "specialist run id"),
            (self.writer_lease_id, "writer lease id"),
        ):
            if value is not None:
                safe_storage_segment(value, label=label)
        if self.target_ref is not None:
            parse_target_ref(self.target_ref)
        if self.trigger_message_seq is not None and self.trigger_message_seq <= 0:
            raise ValidationError("trigger_message_seq 必须大于 0")

    @property
    def role_value(self) -> str:
        return self.role.value if isinstance(self.role, SpecialistRole) else self.role

    @property
    def view_kind(self) -> ViewKind:
        return "working" if self.working_branch_id is not None else "revision"

    @property
    def view_id(self) -> str:
        return self.working_branch_id or self.revision_id or ""


@dataclass(frozen=True, slots=True)
class RuntimeWriteState:
    """Current file-native Runtime facts for one transaction-bound writer lease."""

    project_id: str
    creator_session_id: str
    transaction_id: str
    working_branch_id: str
    transaction_status: TransactionStatus | str
    lease_id: str
    lease_status: str
    lease_target_scope: str
    lease_specialist_run_id: str | None
    lease_observed_working_head: str
    lease_expires_at: datetime


class RuntimeWriteStateProvider(Protocol):
    def get_write_state(
        self,
        *,
        project_id: str,
        transaction_id: str,
        lease_id: str,
    ) -> RuntimeWriteState | None: ...


@dataclass(frozen=True, slots=True)
class TextWriteRequest:
    context: WorkspaceToolContext
    tool_name: Literal["write_file", "edit_file", "append_file"]
    path: str
    text: str
    expected_blob_hash: str | None
    expected_object_version: str | None
    read_set: tuple[ReadSetEntry, ...]


@dataclass(frozen=True, slots=True)
class CommittedWorkspaceMutation:
    result: WorkspaceMutationResult
    mutation_id: str | None
    event_seq: int | None


class WorkspaceMutationGateway(Protocol):
    """Atomic Runtime boundary for a text write plus Journal/Event append."""

    def commit_text_write(
        self, request: TextWriteRequest
    ) -> CommittedWorkspaceMutation: ...


class _ExpectationRequired:
    pass


EXPECTATION_REQUIRED = _ExpectationRequired()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceFileTools:
    """Role-filtered implementation registered under exactly seven names."""

    def __init__(
        self,
        text_store: TextStore,
        context: WorkspaceToolContext,
        *,
        write_state_provider: RuntimeWriteStateProvider | None = None,
        mutation_gateway: WorkspaceMutationGateway | None = None,
        permissions: PermissionRegistry | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.text_store = text_store
        self.context = context
        self.write_state_provider = write_state_provider
        self.mutation_gateway = mutation_gateway
        self.permissions = permissions or PermissionRegistry()
        self.now = now

    def public_tools(self) -> dict[str, Callable[..., dict]]:
        """Return the only functions that may enter a model tool manifest."""

        allowed = set(self.permissions.resolve(self.context.role).tools)
        return {
            name: getattr(self, name) for name in FILE_TOOL_NAMES if name in allowed
        }

    def _view_kwargs(self) -> dict[str, str | None]:
        return {
            "branch_id": self.context.working_branch_id,
            "revision_id": self.context.revision_id,
        }

    def _entries(self, prefix: str | None = None) -> tuple[RevisionEntry, ...]:
        return self.text_store.list_entries(
            self.context.project_id,
            prefix=prefix,
            **self._view_kwargs(),
        )

    def _entry_map(self) -> dict[str, RevisionEntry]:
        return {entry.path: entry for entry in self._entries()}

    def _read_set_entry(self, entry: RevisionEntry) -> ReadSetEntry:
        return ReadSetEntry(
            path=entry.path,
            blob_hash=entry.blob_hash,
            object_version=entry.object_version,
            view_kind=self.context.view_kind,
            view_id=self.context.view_id,
        )

    def _record(self, entry: RevisionEntry) -> None:
        self.context.read_set.record(self._read_set_entry(entry))

    def _read_entry(self, path: str) -> tuple[RevisionEntry, str]:
        normalized = workspace_text_path(path)
        self.permissions.ensure_read_path(self.context.role, normalized)
        entry = self._entry_map().get(normalized)
        if entry is None:
            raise NotFoundError("Workspace 文件不存在", details={"path": normalized})
        content = self.text_store.read_text(
            self.context.project_id,
            normalized,
            **self._view_kwargs(),
        )
        self._record(entry)
        return entry, content

    def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict:
        self.permissions.ensure_tool(self.context.role, "read_file")
        entry, content = self._read_entry(file_path)
        result_content = content
        result: dict = {
            "ok": True,
            "path": entry.path,
            "blobHash": entry.blob_hash,
            "objectVersion": entry.object_version,
        }
        if start_line is not None or end_line is not None:
            start = int(start_line or 1)
            end = int(end_line) if end_line is not None else None
            if start < 1 or (end is not None and end < start):
                raise ValidationError("非法 read_file 行范围")
            lines = content.splitlines()
            bounded_end = min(end if end is not None else len(lines), len(lines))
            selected = lines[start - 1 : bounded_end]
            result_content = "\n".join(
                f"{start + index:6d}\u2192{line}" for index, line in enumerate(selected)
            )
            result.update({"startLine": start, "endLine": bounded_end})
        result["content"] = result_content
        return result

    def _candidate_entries(
        self,
        *,
        path: str | None,
        include_pattern: str | None = None,
    ) -> tuple[RevisionEntry, ...]:
        prefix = workspace_directory(path)
        matcher = compile_workspace_glob(include_pattern) if include_pattern else None
        entries = self._entries(prefix=prefix)
        return tuple(
            entry
            for entry in entries
            if PurePosixPath(entry.path).suffix.lower() in SEARCHABLE_SUFFIXES
            and self.permissions.can_read_path(self.context.role, entry.path)
            and (matcher is None or matcher.fullmatch(PurePosixPath(entry.path).name))
        )

    def grep_search(
        self,
        pattern: str,
        path: str | None = None,
        is_regex: bool = False,
        case_sensitive: bool = True,
        context_lines: int = 0,
        include_pattern: str | None = None,
        max_results: int = 200,
    ) -> dict:
        self.permissions.ensure_tool(self.context.role, "grep_search")
        if not isinstance(pattern, str) or not pattern or len(pattern) > 4096:
            raise ValidationError("grep pattern 不能为空且不能超过 4096 字符")
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            matcher = re.compile(pattern if is_regex else re.escape(pattern), flags)
        except re.error as exc:
            raise ValidationError(
                "非法 grep 正则", details={"error": str(exc)}
            ) from exc
        context_count = max(0, min(int(context_lines), 5))
        limit = max(1, min(int(max_results), 500))
        matches: list[dict] = []
        for entry in self._candidate_entries(
            path=path, include_pattern=include_pattern
        ):
            content = self.text_store.read_text(
                self.context.project_id,
                entry.path,
                **self._view_kwargs(),
            )
            self._record(entry)
            lines = content.splitlines()
            for index, line in enumerate(lines):
                if matcher.search(line):
                    item: dict = {
                        "path": entry.path,
                        "line": index + 1,
                        "content": line,
                        "blobHash": entry.blob_hash,
                        "objectVersion": entry.object_version,
                    }
                    if context_count:
                        item["context"] = lines[
                            max(0, index - context_count) : index + context_count + 1
                        ]
                    matches.append(item)
                    if len(matches) >= limit:
                        return {
                            "ok": True,
                            "pattern": pattern,
                            "count": len(matches),
                            "truncated": True,
                            "matches": matches,
                        }
        return {
            "ok": True,
            "pattern": pattern,
            "count": len(matches),
            "truncated": False,
            "matches": matches,
        }

    def glob_search(
        self,
        pattern: str,
        path: str | None = None,
        max_results: int = 500,
    ) -> dict:
        self.permissions.ensure_tool(self.context.role, "glob_search")
        full_pattern = join_workspace_glob(path, pattern)
        matcher = compile_workspace_glob(full_pattern)
        limit = max(1, min(int(max_results), 1000))
        matches = [
            entry
            for entry in self._entries()
            if self.permissions.can_read_path(self.context.role, entry.path)
            and matcher.fullmatch(entry.path)
        ]
        selected = matches[:limit]
        for entry in matches:
            self._record(entry)
        return {
            "ok": True,
            "pattern": workspace_glob(pattern),
            "count": len(matches),
            "truncated": len(matches) > limit,
            "files": [
                {
                    "path": entry.path,
                    "blobHash": entry.blob_hash,
                    "objectVersion": entry.object_version,
                }
                for entry in selected
            ],
        }

    def ast_search(
        self,
        pattern: str,
        path: str | None = None,
        max_results: int = 200,
    ) -> dict:
        """Search structural nodes in Markdown, VTT, CTM, TXT and REF files."""

        self.permissions.ensure_tool(self.context.role, "ast_search")
        if not isinstance(pattern, str) or not pattern or len(pattern) > 1024:
            raise ValidationError("ast pattern 不能为空且不能超过 1024 字符")
        needle = pattern.casefold()
        limit = max(1, min(int(max_results), 500))
        matches: list[dict] = []
        for entry in self._candidate_entries(path=path):
            content = self.text_store.read_text(
                self.context.project_id,
                entry.path,
                **self._view_kwargs(),
            )
            self._record(entry)
            suffix = PurePosixPath(entry.path).suffix.lower()
            for node in _text_nodes(content, suffix):
                if needle in node["text"].casefold():
                    matches.append(
                        {
                            "path": entry.path,
                            "blobHash": entry.blob_hash,
                            "objectVersion": entry.object_version,
                            **node,
                        }
                    )
                    if len(matches) >= limit:
                        return {
                            "ok": True,
                            "pattern": pattern,
                            "count": len(matches),
                            "truncated": True,
                            "matches": matches,
                        }
        return {
            "ok": True,
            "pattern": pattern,
            "count": len(matches),
            "truncated": False,
            "matches": matches,
        }

    def _runtime_write_state(self, path: str, tool_name: str) -> RuntimeWriteState:
        self.permissions.ensure_tool(self.context.role, tool_name)
        if PurePosixPath(path).suffix.lower() == ".ref":
            raise ValidationError(
                "引用选择必须使用 typed Runtime mutation，不能使用文件写工具",
                details={"path": path},
            )
        if (
            self.context.revision_id is not None
            or self.context.working_branch_id is None
        ):
            raise PhaseConflictError("immutable Revision 只读")
        required = {
            "transactionId": self.context.transaction_id,
            "writerLeaseId": self.context.writer_lease_id,
            "observedWorkingHead": self.context.observed_working_head,
            "targetRef": self.context.target_ref,
        }
        if self.context.role_value != "creator_agent":
            required["specialistRunId"] = self.context.specialist_run_id
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValidationError(
                "写工具缺少 Runtime 隐式上下文", details={"missing": missing}
            )
        self.permissions.ensure_run_write_path(
            self.context.role,
            path,
            specialist_run_id=str(self.context.specialist_run_id),
            target_ref=str(self.context.target_ref),
        )
        if self.write_state_provider is None or self.mutation_gateway is None:
            raise StorageIntegrityError(
                "写工具未连接 Runtime state provider/mutation gateway"
            )
        state = self.write_state_provider.get_write_state(
            project_id=self.context.project_id,
            transaction_id=self.context.transaction_id or "",
            lease_id=self.context.writer_lease_id or "",
        )
        if state is None:
            raise PhaseConflictError("Writer lease 不存在或已失效")
        identity_pairs = {
            "projectId": (self.context.project_id, state.project_id),
            "creatorSessionId": (
                self.context.creator_session_id,
                state.creator_session_id,
            ),
            "transactionId": (self.context.transaction_id, state.transaction_id),
            "workingBranchId": (
                self.context.working_branch_id,
                state.working_branch_id,
            ),
            "writerLeaseId": (self.context.writer_lease_id, state.lease_id),
            "specialistRunId": (
                self.context.specialist_run_id,
                state.lease_specialist_run_id,
            ),
        }
        mismatched = {
            name: {"context": pair[0], "runtime": pair[1]}
            for name, pair in identity_pairs.items()
            if pair[0] != pair[1]
        }
        if mismatched:
            raise PhaseConflictError(
                "Writer context 与 Runtime lease 归属不匹配", details=mismatched
            )
        try:
            transaction_status = TransactionStatus(state.transaction_status)
        except ValueError as exc:
            raise StorageIntegrityError("Runtime 返回未知 Transaction 状态") from exc
        if transaction_status not in {
            TransactionStatus.ACTIVE,
            TransactionStatus.REVISING,
        }:
            raise PhaseConflictError(
                "Transaction 当前阶段禁止 Agent 写入",
                details={"status": transaction_status.value},
            )
        if state.lease_status != "ACTIVE":
            raise PhaseConflictError(
                "Writer lease 不是 ACTIVE",
                details={"status": state.lease_status},
            )
        expiry = state.lease_expires_at
        if not isinstance(expiry, datetime):
            raise StorageIntegrityError("Runtime 返回非法 Writer lease expiry")
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        current_time = self.now()
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        if expiry <= current_time:
            raise PhaseConflictError("Writer lease 已过期")
        if self.context.observed_working_head != state.lease_observed_working_head:
            raise ConflictError(
                "Writer context 的 observed Working Head 与 lease 不匹配",
                details={
                    "reason": "LEASE_HEAD_MISMATCH",
                    "expected": state.lease_observed_working_head,
                    "actual": self.context.observed_working_head,
                },
            )
        if not scope_contains_path(state.lease_target_scope, path):
            raise PhaseConflictError(
                "Writer lease scope 不覆盖目标文件",
                details={"scope": state.lease_target_scope, "path": path},
            )
        return state

    def _assert_read_set_current(self) -> None:
        if self.context.working_branch_id is None:
            return
        current = self._entry_map()
        stale: list[dict] = []
        for observed in self.context.read_set.snapshot():
            if (
                observed.view_kind != "working"
                or observed.view_id != self.context.working_branch_id
            ):
                continue
            entry = current.get(observed.path)
            actual_blob = entry.blob_hash if entry else None
            actual_version = entry.object_version if entry else None
            if (
                actual_blob != observed.blob_hash
                or actual_version != observed.object_version
            ):
                stale.append(
                    {
                        "path": observed.path,
                        "expectedBlobHash": observed.blob_hash,
                        "actualBlobHash": actual_blob,
                        "expectedObjectVersion": observed.object_version,
                        "actualObjectVersion": actual_version,
                    }
                )
        if stale:
            raise ConflictError(
                "Workspace read-set 已过期",
                details={"reason": "READ_SET_STALE", "entries": stale},
            )

    @staticmethod
    def _expected_value(
        value: str | None | _ExpectationRequired,
        *,
        label: str,
        is_blob: bool,
    ) -> str | None:
        if isinstance(value, _ExpectationRequired):
            raise ValidationError(f"写文件必须显式提供 {label}（创建文件时传 null）")
        if value is None:
            return None
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValidationError(f"非法 {label}")
        return validate_sha256(value) if is_blob else value

    def _commit_text(
        self,
        *,
        tool_name: Literal["write_file", "edit_file", "append_file"],
        path: str,
        text: str,
        expected_blob_hash: str | None | _ExpectationRequired,
        expected_object_version: str | None | _ExpectationRequired,
    ) -> dict:
        if not isinstance(text, str):
            raise ValidationError("文件内容必须是 UTF-8 文本字符串")
        normalized = workspace_text_path(path)
        self._runtime_write_state(normalized, tool_name)
        expected_blob = self._expected_value(
            expected_blob_hash,
            label="expectedBlobHash",
            is_blob=True,
        )
        expected_object = self._expected_value(
            expected_object_version,
            label="expectedObjectVersion",
            is_blob=False,
        )
        self._assert_read_set_current()
        entries = self._entry_map()
        unit_route = None
        route_path = _shot_unit_route_path(normalized)
        if route_path is not None and route_path in entries:
            unit_route = self.text_store.read_text(
                self.context.project_id,
                route_path,
                **self._view_kwargs(),
            ).strip()
        _validate_projected_text(normalized, text, unit_route=unit_route)
        before = entries.get(normalized)
        actual_blob = before.blob_hash if before else None
        actual_object = before.object_version if before else None
        if actual_blob != expected_blob or actual_object != expected_object:
            raise ConflictError(
                "目标文件 CAS 冲突",
                details={
                    "reason": "TARGET_VERSION_STALE",
                    "path": normalized,
                    "expectedBlobHash": expected_blob,
                    "actualBlobHash": actual_blob,
                    "expectedObjectVersion": expected_object,
                    "actualObjectVersion": actual_object,
                },
            )
        if before is None:
            parent = PurePosixPath(normalized).parent.as_posix()
            if parent != "." and not any(
                entry.path.startswith(parent + "/") for entry in entries.values()
            ):
                raise ValidationError(
                    "目标目录不存在；目录创建必须使用 typed Runtime mutation",
                    details={"path": normalized, "parent": parent},
                )
        assert self.mutation_gateway is not None
        committed = self.mutation_gateway.commit_text_write(
            TextWriteRequest(
                context=self.context,
                tool_name=tool_name,
                path=normalized,
                text=text,
                expected_blob_hash=expected_blob,
                expected_object_version=expected_object,
                read_set=self.context.read_set.snapshot(),
            )
        )
        result = committed.result
        after = result.after_entry
        if after is None or after.path != normalized:
            raise StorageIntegrityError(
                "Mutation gateway 返回了错误的 Workspace target"
            )
        if result.working_tree.project_id != self.context.project_id:
            raise StorageIntegrityError("Mutation gateway 返回了错误的 Project")
        if result.working_tree.id != self.context.working_branch_id:
            raise StorageIntegrityError("Mutation gateway 返回了错误的 Working Branch")
        expected_after_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if after.blob_hash != expected_after_hash:
            raise StorageIntegrityError("Mutation gateway 返回的 blob 与提交文本不匹配")
        if result.changed and (
            not committed.mutation_id or committed.event_seq is None
        ):
            raise StorageIntegrityError(
                "Workspace 内容已变化但缺少原子 Journal/Event 证据"
            )
        if committed.mutation_id is not None:
            safe_storage_segment(committed.mutation_id, label="mutation id")
        if committed.event_seq is not None and committed.event_seq <= 0:
            raise StorageIntegrityError("Mutation gateway 返回非法 Event seq")
        self.context.read_set.replace(self._read_set_entry(after))
        return {
            "ok": True,
            "path": normalized,
            "bytes": len(text.encode("utf-8")),
            "changed": result.changed,
            "blobHash": after.blob_hash,
            "objectVersion": after.object_version,
            "workingHead": result.working_tree.head,
            "mutationId": committed.mutation_id,
            "eventSeq": committed.event_seq,
        }

    def write_file(
        self,
        file_path: str,
        content: str,
        expected_blob_hash: str | None | _ExpectationRequired = EXPECTATION_REQUIRED,
        expected_object_version: str
        | None
        | _ExpectationRequired = EXPECTATION_REQUIRED,
    ) -> dict:
        return self._commit_text(
            tool_name="write_file",
            path=file_path,
            text=content,
            expected_blob_hash=expected_blob_hash,
            expected_object_version=expected_object_version,
        )

    def edit_file(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = True,
        expected_blob_hash: str | None | _ExpectationRequired = EXPECTATION_REQUIRED,
        expected_object_version: str
        | None
        | _ExpectationRequired = EXPECTATION_REQUIRED,
    ) -> dict:
        self.permissions.ensure_tool(self.context.role, "edit_file")
        _, current = self._read_entry(file_path)
        if not isinstance(old_text, str) or not old_text:
            raise ValidationError("old_text 不能为空")
        if not isinstance(new_text, str):
            raise ValidationError("new_text 必须是字符串")
        count = current.count(old_text)
        if count == 0:
            raise ConflictError("目标文本不存在", details={"path": file_path})
        if count > 1 and not replace_all:
            raise ConflictError(
                "old_text 出现多次，请扩展上下文或启用 replace_all",
                details={"path": file_path, "occurrences": count},
            )
        updated = (
            current.replace(old_text, new_text)
            if replace_all
            else current.replace(old_text, new_text, 1)
        )
        result = self._commit_text(
            tool_name="edit_file",
            path=file_path,
            text=updated,
            expected_blob_hash=expected_blob_hash,
            expected_object_version=expected_object_version,
        )
        result["replaced"] = count if replace_all else 1
        return result

    def append_file(
        self,
        file_path: str,
        content: str,
        expected_blob_hash: str | None | _ExpectationRequired = EXPECTATION_REQUIRED,
        expected_object_version: str
        | None
        | _ExpectationRequired = EXPECTATION_REQUIRED,
    ) -> dict:
        self.permissions.ensure_tool(self.context.role, "append_file")
        if not isinstance(content, str):
            raise ValidationError("content 必须是字符串")
        normalized = workspace_text_path(file_path)
        entry = self._entry_map().get(normalized)
        current = ""
        if entry is not None:
            _, current = self._read_entry(normalized)
        return self._commit_text(
            tool_name="append_file",
            path=normalized,
            text=current + content,
            expected_blob_hash=expected_blob_hash,
            expected_object_version=expected_object_version,
        )


def _text_nodes(content: str, suffix: str) -> tuple[dict, ...]:
    nodes: list[dict] = []
    lines = content.splitlines()
    if suffix == ".md":
        for line_number, line in enumerate(lines, 1):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                nodes.append(
                    {
                        "kind": "markdown_heading",
                        "level": len(match.group(1)),
                        "line": line_number,
                        "text": match.group(2),
                    }
                )
    elif suffix == ".vtt":
        for line_number, line in enumerate(lines, 1):
            if "-->" in line:
                cue_text = lines[line_number] if line_number < len(lines) else ""
                nodes.append(
                    {
                        "kind": "vtt_cue",
                        "line": line_number,
                        "timeRange": line.strip(),
                        "text": cue_text,
                    }
                )
    elif suffix == ".ctm":
        for line_number, line in enumerate(lines, 1):
            fields = line.split()
            if len(fields) >= 5:
                nodes.append(
                    {
                        "kind": "ctm_token",
                        "line": line_number,
                        "start": fields[2],
                        "duration": fields[3],
                        "text": " ".join(fields[4:]),
                    }
                )
    elif suffix == ".ref":
        if content:
            nodes.append({"kind": "reference", "line": 1, "text": content})
    else:
        nodes.extend(
            {"kind": "text_line", "line": line_number, "text": line}
            for line_number, line in enumerate(lines, 1)
            if line.strip()
        )
    return tuple(nodes)


__all__ = [
    "bind_write_file_runtime_expectations",
    "CommittedWorkspaceMutation",
    "EXPECTATION_REQUIRED",
    "ReadSetAccumulator",
    "ReadSetEntry",
    "RuntimeWriteState",
    "RuntimeWriteStateProvider",
    "TextWriteRequest",
    "WorkspaceFileTools",
    "WorkspaceMutationGateway",
    "WorkspaceToolContext",
]
