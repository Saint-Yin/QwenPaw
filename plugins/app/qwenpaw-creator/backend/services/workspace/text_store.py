"""Virtual Agent-facing Text Workspace backed only by blob mappings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
from typing import Any, Final, Protocol

from domain.errors import ConflictError, NotFoundError, StorageIntegrityError, ValidationError
from domain.ids import new_id, utc_now_iso
from domain.refs import validate_workspace_ref

from .content_store import ContentStore, atomic_replace_bytes
from .mutations import (
    MutationKind,
    classify_content_change,
    safe_storage_segment,
    safe_workspace_path,
)
from .revision_store import (
    RevisionEntry,
    RevisionKind,
    RevisionManifest,
    RevisionStore,
    infer_content_type,
    tree_hash_for_entries,
)


_ALLOWED_SUFFIXES = frozenset({".md", ".txt", ".ref", ".vtt", ".ctm"})
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", re.DOTALL)


class _UnsetExpectation:
    pass


UNSET_EXPECTATION: Final = _UnsetExpectation()


@dataclass(frozen=True, slots=True)
class WorkingTree:
    id: str
    project_id: str
    base_revision_id: str
    version: int
    head: str
    tree_hash: str
    entries: tuple[RevisionEntry, ...]
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        safe_storage_segment(self.id, label="working branch id")
        safe_storage_segment(self.project_id, label="project id")
        safe_storage_segment(self.base_revision_id, label="base revision id")
        if self.version < 0:
            raise ValidationError("working tree version 不能小于 0")
        from .content_store import validate_sha256

        validate_sha256(self.head)
        validate_sha256(self.tree_hash)
        paths = [entry.path for entry in self.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValidationError("working entries 必须按 path 排序且不能重复")

    def entry_map(self) -> dict[str, RevisionEntry]:
        return {entry.path: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class WorkspaceMutationResult:
    kind: MutationKind
    before_entry: RevisionEntry | None
    after_entry: RevisionEntry | None
    source_path: str | None
    destination_path: str | None
    working_tree: WorkingTree
    changed: bool = True


class WorkingTreeRepository(Protocol):
    def create(self, tree: WorkingTree) -> None: ...

    def get(self, project_id: str, branch_id: str) -> WorkingTree: ...

    def compare_and_set(self, tree: WorkingTree, *, expected_head: str) -> None: ...


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _entry_payload(entry: RevisionEntry) -> dict[str, Any]:
    return {
        "path": entry.path,
        "blobHash": entry.blob_hash,
        "size": entry.size,
        "contentType": entry.content_type,
    }


def _working_head(
    *,
    project_id: str,
    branch_id: str,
    base_revision_id: str,
    version: int,
    tree_hash: str,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "projectId": project_id,
                "branchId": branch_id,
                "baseRevisionId": base_revision_id,
                "version": version,
                "treeHash": tree_hash,
            }
        )
    ).hexdigest()


def _tree_payload(tree: WorkingTree) -> dict[str, Any]:
    return {
        "id": tree.id,
        "projectId": tree.project_id,
        "baseRevisionId": tree.base_revision_id,
        "version": tree.version,
        "head": tree.head,
        "treeHash": tree.tree_hash,
        "entries": [_entry_payload(entry) for entry in tree.entries],
        "createdAt": tree.created_at,
        "updatedAt": tree.updated_at,
    }


def _tree_from_payload(payload: Mapping[str, Any]) -> WorkingTree:
    entries = tuple(
        RevisionEntry(
            path=str(item["path"]),
            blob_hash=str(item["blobHash"]),
            size=int(item["size"]),
            content_type=str(item["contentType"]),
        )
        for item in payload.get("entries", [])
    )
    tree = WorkingTree(
        id=str(payload["id"]),
        project_id=str(payload["projectId"]),
        base_revision_id=str(payload["baseRevisionId"]),
        version=int(payload["version"]),
        head=str(payload["head"]),
        tree_hash=str(payload["treeHash"]),
        entries=entries,
        created_at=str(payload["createdAt"]),
        updated_at=str(payload["updatedAt"]),
    )
    actual_tree_hash = tree_hash_for_entries(tree.entries)
    actual_head = _working_head(
        project_id=tree.project_id,
        branch_id=tree.id,
        base_revision_id=tree.base_revision_id,
        version=tree.version,
        tree_hash=actual_tree_hash,
    )
    if actual_tree_hash != tree.tree_hash or actual_head != tree.head:
        raise StorageIntegrityError(
            "working tree hash/head 不匹配",
            details={
                "expectedTreeHash": tree.tree_hash,
                "actualTreeHash": actual_tree_hash,
                "expectedHead": tree.head,
                "actualHead": actual_head,
            },
        )
    return tree


class FileWorkingTreeRepository:
    """Private mutable branch metadata; content remains immutable blobs."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve() / "working-tree-store"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, project_id: str, branch_id: str) -> Path:
        return (
            self.root
            / "projects"
            / safe_storage_segment(project_id, label="project id")
            / "branches"
            / f"{safe_storage_segment(branch_id, label='working branch id')}.json"
        )

    def create(self, tree: WorkingTree) -> None:
        target = self._path(tree.project_id, tree.id)
        payload = _canonical_json(_tree_payload(tree))
        with self._lock:
            if target.exists():
                existing = target.read_bytes()
                if existing == payload:
                    return
                raise ConflictError("working branch id 已存在", details={"branchId": tree.id})
            atomic_replace_bytes(target, payload)

    def get(self, project_id: str, branch_id: str) -> WorkingTree:
        target = self._path(project_id, branch_id)
        if not target.is_file():
            raise NotFoundError(
                "working branch 不存在",
                details={"projectId": project_id, "branchId": branch_id},
            )
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageIntegrityError(f"working tree metadata 无法读取: {target}") from exc
        tree = _tree_from_payload(payload)
        if tree.project_id != project_id or tree.id != branch_id:
            raise StorageIntegrityError("working tree identity 不匹配")
        return tree

    def compare_and_set(self, tree: WorkingTree, *, expected_head: str) -> None:
        target = self._path(tree.project_id, tree.id)
        with self._lock:
            current = self.get(tree.project_id, tree.id)
            if current.head != expected_head:
                raise ConflictError(
                    "working head CAS 冲突",
                    details={"expected": expected_head, "actual": current.head},
                )
            if tree.version != current.version + 1:
                raise ConflictError(
                    "working tree version 必须单调递增",
                    details={"current": current.version, "next": tree.version},
                )
            atomic_replace_bytes(target, _canonical_json(_tree_payload(tree)))


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def validate_text_workspace_content(path: str, payload: bytes) -> str:
    """Validate allowed text/ref formats and return the decoded text."""
    normalized = safe_workspace_path(path)
    suffix = _suffix(normalized)
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValidationError(
            "Agent-facing Workspace 只允许 .md/.txt/.ref/.vtt/.ctm",
            details={"path": normalized, "suffix": suffix},
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Workspace 文本必须是 UTF-8: {normalized}") from exc
    if suffix == ".md" and _FRONTMATTER_RE.match(text):
        raise ValidationError("Workspace Markdown 不允许 YAML frontmatter")
    if suffix == ".ref":
        if not text or text != text.strip() or "\n" in text or "\r" in text:
            raise ValidationError(".ref 必须是单行且无首尾空白")
        validate_workspace_ref(text)
    return text


class TextStore:
    """Read and mutate a virtual working tree through content hashes only."""

    def __init__(
        self,
        content_store: ContentStore,
        revision_store: RevisionStore,
        *,
        repository: WorkingTreeRepository | None = None,
    ) -> None:
        self.content_store = content_store
        self.revision_store = revision_store
        self.repository = repository or FileWorkingTreeRepository(content_store.root)

    def open_working_tree(
        self,
        *,
        project_id: str,
        base_revision_id: str,
        branch_id: str | None = None,
    ) -> WorkingTree:
        revision = self.revision_store.get(project_id, base_revision_id)
        identifier = branch_id or new_id("branch")
        safe_storage_segment(identifier, label="working branch id")
        timestamp = utc_now_iso()
        tree_hash = revision.tree_hash
        tree = WorkingTree(
            id=identifier,
            project_id=project_id,
            base_revision_id=base_revision_id,
            version=0,
            head=_working_head(
                project_id=project_id,
                branch_id=identifier,
                base_revision_id=base_revision_id,
                version=0,
                tree_hash=tree_hash,
            ),
            tree_hash=tree_hash,
            entries=revision.entries,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.repository.create(tree)
        return tree

    def get_working_tree(self, project_id: str, branch_id: str) -> WorkingTree:
        tree = self.repository.get(project_id, branch_id)
        for entry in tree.entries:
            if not self.content_store.verify(entry.blob_hash, namespace="blob"):
                raise StorageIntegrityError(
                    "working tree 引用不存在的 blob",
                    details={"path": entry.path, "blobHash": entry.blob_hash},
                )
        return tree

    def _snapshot_entries(
        self,
        project_id: str,
        *,
        branch_id: str | None,
        revision_id: str | None,
    ) -> tuple[RevisionEntry, ...]:
        if (branch_id is None) == (revision_id is None):
            raise ValidationError("必须且只能指定 branch_id 或 revision_id")
        if branch_id is not None:
            return self.get_working_tree(project_id, branch_id).entries
        return self.revision_store.get(project_id, revision_id or "").entries

    def list_entries(
        self,
        project_id: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
        prefix: str | None = None,
    ) -> tuple[RevisionEntry, ...]:
        entries = self._snapshot_entries(
            project_id, branch_id=branch_id, revision_id=revision_id
        )
        if prefix is None:
            return entries
        normalized = safe_workspace_path(prefix)
        prefix_with_slash = f"{normalized.rstrip('/')}/"
        return tuple(
            entry
            for entry in entries
            if entry.path == normalized or entry.path.startswith(prefix_with_slash)
        )

    def read_bytes(
        self,
        project_id: str,
        path: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> bytes:
        normalized = safe_workspace_path(path)
        entries = self._snapshot_entries(
            project_id, branch_id=branch_id, revision_id=revision_id
        )
        entry = next((item for item in entries if item.path == normalized), None)
        if entry is None:
            raise NotFoundError("Workspace 文件不存在", details={"path": normalized})
        return self.content_store.read_bytes(entry.blob_hash, namespace="blob")

    def read_text(
        self,
        project_id: str,
        path: str,
        *,
        branch_id: str | None = None,
        revision_id: str | None = None,
    ) -> str:
        payload = self.read_bytes(
            project_id,
            path,
            branch_id=branch_id,
            revision_id=revision_id,
        )
        return validate_text_workspace_content(path, payload)

    @staticmethod
    def _check_target_expectation(
        current: RevisionEntry | None,
        expected_blob_hash: str | None | _UnsetExpectation,
    ) -> None:
        if isinstance(expected_blob_hash, _UnsetExpectation):
            return
        actual = current.blob_hash if current is not None else None
        if actual != expected_blob_hash:
            raise ConflictError(
                "target blob CAS 冲突",
                details={"expected": expected_blob_hash, "actual": actual},
            )

    def _updated_tree(
        self,
        current: WorkingTree,
        entries: Iterable[RevisionEntry],
        *,
        expected_head: str | None,
    ) -> WorkingTree:
        if expected_head is not None and current.head != expected_head:
            raise ConflictError(
                "working head 已变化",
                details={"expected": expected_head, "actual": current.head},
            )
        ordered = tuple(sorted(entries, key=lambda item: item.path))
        tree_hash = tree_hash_for_entries(ordered)
        next_version = current.version + 1
        updated = WorkingTree(
            id=current.id,
            project_id=current.project_id,
            base_revision_id=current.base_revision_id,
            version=next_version,
            head=_working_head(
                project_id=current.project_id,
                branch_id=current.id,
                base_revision_id=current.base_revision_id,
                version=next_version,
                tree_hash=tree_hash,
            ),
            tree_hash=tree_hash,
            entries=ordered,
            created_at=current.created_at,
            updated_at=utc_now_iso(),
        )
        self.repository.compare_and_set(updated, expected_head=current.head)
        return updated

    def write_bytes(
        self,
        *,
        project_id: str,
        branch_id: str,
        path: str,
        payload: bytes | bytearray | memoryview,
        expected_head: str | None = None,
        expected_blob_hash: str | None | _UnsetExpectation = UNSET_EXPECTATION,
    ) -> WorkspaceMutationResult:
        normalized = safe_workspace_path(path)
        raw = bytes(payload)
        after_text = validate_text_workspace_content(normalized, raw)
        current = self.get_working_tree(project_id, branch_id)
        entries = current.entry_map()
        before = entries.get(normalized)
        self._check_target_expectation(before, expected_blob_hash)

        stored = self.content_store.put_bytes(raw, namespace="blob")
        after = RevisionEntry(
            path=normalized,
            blob_hash=stored.sha256,
            size=stored.size,
            content_type=infer_content_type(normalized),
        )
        if before == after:
            return WorkspaceMutationResult(
                kind=MutationKind.UPDATE,
                before_entry=before,
                after_entry=after,
                source_path=normalized,
                destination_path=normalized,
                working_tree=current,
                changed=False,
            )

        before_text = (
            self.content_store.read_text(before.blob_hash, namespace="blob")
            if before is not None
            else None
        )
        entries[normalized] = after
        updated = self._updated_tree(current, entries.values(), expected_head=expected_head)
        return WorkspaceMutationResult(
            kind=classify_content_change(normalized, before_text, after_text),
            before_entry=before,
            after_entry=after,
            source_path=normalized,
            destination_path=normalized,
            working_tree=updated,
        )

    def write_text(
        self,
        *,
        project_id: str,
        branch_id: str,
        path: str,
        text: str,
        expected_head: str | None = None,
        expected_blob_hash: str | None | _UnsetExpectation = UNSET_EXPECTATION,
    ) -> WorkspaceMutationResult:
        return self.write_bytes(
            project_id=project_id,
            branch_id=branch_id,
            path=path,
            payload=text.encode("utf-8"),
            expected_head=expected_head,
            expected_blob_hash=expected_blob_hash,
        )

    def delete(
        self,
        *,
        project_id: str,
        branch_id: str,
        path: str,
        expected_head: str | None = None,
        expected_blob_hash: str | None | _UnsetExpectation = UNSET_EXPECTATION,
    ) -> WorkspaceMutationResult:
        normalized = safe_workspace_path(path)
        current = self.get_working_tree(project_id, branch_id)
        entries = current.entry_map()
        before = entries.get(normalized)
        if before is None:
            raise NotFoundError("Workspace 文件不存在", details={"path": normalized})
        self._check_target_expectation(before, expected_blob_hash)
        del entries[normalized]
        updated = self._updated_tree(current, entries.values(), expected_head=expected_head)
        return WorkspaceMutationResult(
            kind=MutationKind.DELETE,
            before_entry=before,
            after_entry=None,
            source_path=normalized,
            destination_path=None,
            working_tree=updated,
        )

    def move(
        self,
        *,
        project_id: str,
        branch_id: str,
        source_path: str,
        destination_path: str,
        expected_head: str | None = None,
        expected_source_blob_hash: str | None | _UnsetExpectation = UNSET_EXPECTATION,
    ) -> WorkspaceMutationResult:
        source = safe_workspace_path(source_path)
        destination = safe_workspace_path(destination_path)
        if source == destination:
            raise ValidationError("move source 和 destination 不能相同")
        current = self.get_working_tree(project_id, branch_id)
        entries = current.entry_map()
        before = entries.get(source)
        if before is None:
            raise NotFoundError("move source 不存在", details={"path": source})
        if destination in entries:
            raise ConflictError("move destination 已存在", details={"path": destination})
        self._check_target_expectation(before, expected_source_blob_hash)
        raw = self.content_store.read_bytes(before.blob_hash, namespace="blob")
        validate_text_workspace_content(destination, raw)
        after = RevisionEntry(
            path=destination,
            blob_hash=before.blob_hash,
            size=before.size,
            content_type=infer_content_type(destination),
        )
        del entries[source]
        entries[destination] = after
        updated = self._updated_tree(current, entries.values(), expected_head=expected_head)
        kind = (
            MutationKind.RENAME
            if PurePosixPath(source).parent == PurePosixPath(destination).parent
            else MutationKind.MOVE
        )
        return WorkspaceMutationResult(
            kind=kind,
            before_entry=before,
            after_entry=after,
            source_path=source,
            destination_path=destination,
            working_tree=updated,
        )

    def seal_revision(
        self,
        *,
        project_id: str,
        branch_id: str,
        kind: RevisionKind | str,
        parent_revision_id: str | None = None,
    ) -> RevisionManifest:
        tree = self.get_working_tree(project_id, branch_id)
        return self.revision_store.create_revision(
            project_id=project_id,
            kind=kind,
            entries=tree.entries,
            parent_revision_id=parent_revision_id or tree.base_revision_id,
        )
