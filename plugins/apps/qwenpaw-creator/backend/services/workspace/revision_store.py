# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Immutable revision manifests backed by content-addressed blobs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Protocol

from domain.errors import (
    ConflictError,
    NotFoundError,
    StorageIntegrityError,
    ValidationError,
)
from domain.ids import new_id, utc_now_iso

from .content_store import ContentStore, atomic_replace_bytes, validate_sha256
from .mutations import safe_storage_segment, safe_workspace_path


class RevisionKind(StrEnum):
    APPROVED = "APPROVED"
    REVIEW = "REVIEW"


class RevisionPointer(StrEnum):
    APPROVED = "approved"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class RevisionEntry:
    path: str
    blob_hash: str
    size: int
    content_type: str = "text/plain; charset=utf-8"

    def __post_init__(self) -> None:
        safe_workspace_path(self.path)
        validate_sha256(self.blob_hash)
        if self.size < 0:
            raise ValidationError("revision entry size 不能小于 0")
        if not self.content_type:
            raise ValidationError("revision entry content_type 不能为空")

    @property
    def object_version(self) -> str:
        return self.blob_hash


@dataclass(frozen=True, slots=True)
class RevisionManifest:
    id: str
    project_id: str
    kind: RevisionKind
    parent_revision_id: str | None
    tree_hash: str
    entries: tuple[RevisionEntry, ...]
    created_at: str
    manifest_hash: str

    def __post_init__(self) -> None:
        safe_storage_segment(self.id, label="revision id")
        safe_storage_segment(self.project_id, label="project id")
        if self.parent_revision_id is not None:
            safe_storage_segment(
                self.parent_revision_id,
                label="parent revision id",
            )
        validate_sha256(self.tree_hash)
        validate_sha256(self.manifest_hash)
        paths = [entry.path for entry in self.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValidationError("revision entries 必须按 path 排序且不能重复")

    def entry_map(self) -> dict[str, RevisionEntry]:
        return {entry.path: entry for entry in self.entries}


class RevisionRepository(Protocol):
    def save(self, manifest: RevisionManifest) -> None:
        ...

    def get(self, project_id: str, revision_id: str) -> RevisionManifest:
        ...

    def get_pointer(
        self,
        project_id: str,
        pointer: RevisionPointer,
    ) -> str | None:
        ...

    def compare_and_set_pointer(
        self,
        project_id: str,
        pointer: RevisionPointer,
        revision_id: str | None,
        *,
        expected_revision_id: str | None,
    ) -> None:
        ...


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


def tree_hash_for_entries(entries: Iterable[RevisionEntry]) -> str:
    ordered = sorted(entries, key=lambda item: item.path)
    return hashlib.sha256(
        _canonical_json([_entry_payload(item) for item in ordered]),
    ).hexdigest()


def _manifest_core_payload(
    *,
    revision_id: str,
    project_id: str,
    kind: RevisionKind,
    parent_revision_id: str | None,
    tree_hash: str,
    entries: Iterable[RevisionEntry],
    created_at: str,
) -> dict[str, Any]:
    return {
        "id": revision_id,
        "projectId": project_id,
        "kind": kind.value,
        "parentRevisionId": parent_revision_id,
        "treeHash": tree_hash,
        "entries": [
            _entry_payload(item)
            for item in sorted(entries, key=lambda item: item.path)
        ],
        "createdAt": created_at,
    }


def _manifest_payload(manifest: RevisionManifest) -> dict[str, Any]:
    payload = _manifest_core_payload(
        revision_id=manifest.id,
        project_id=manifest.project_id,
        kind=manifest.kind,
        parent_revision_id=manifest.parent_revision_id,
        tree_hash=manifest.tree_hash,
        entries=manifest.entries,
        created_at=manifest.created_at,
    )
    payload["manifestHash"] = manifest.manifest_hash
    return payload


def _manifest_from_payload(payload: Mapping[str, Any]) -> RevisionManifest:
    entries = tuple(
        RevisionEntry(
            path=str(item["path"]),
            blob_hash=str(item["blobHash"]),
            size=int(item["size"]),
            content_type=str(item["contentType"]),
        )
        for item in payload.get("entries", [])
    )
    manifest = RevisionManifest(
        id=str(payload["id"]),
        project_id=str(payload["projectId"]),
        kind=RevisionKind(payload["kind"]),
        parent_revision_id=payload.get("parentRevisionId"),
        tree_hash=str(payload["treeHash"]),
        entries=entries,
        created_at=str(payload["createdAt"]),
        manifest_hash=str(payload["manifestHash"]),
    )
    actual_tree_hash = tree_hash_for_entries(manifest.entries)
    if actual_tree_hash != manifest.tree_hash:
        raise StorageIntegrityError(
            "revision tree hash 不匹配",
            details={
                "expected": manifest.tree_hash,
                "actual": actual_tree_hash,
            },
        )
    core = _manifest_core_payload(
        revision_id=manifest.id,
        project_id=manifest.project_id,
        kind=manifest.kind,
        parent_revision_id=manifest.parent_revision_id,
        tree_hash=manifest.tree_hash,
        entries=manifest.entries,
        created_at=manifest.created_at,
    )
    actual_manifest_hash = hashlib.sha256(_canonical_json(core)).hexdigest()
    if actual_manifest_hash != manifest.manifest_hash:
        raise StorageIntegrityError(
            "revision manifest hash 不匹配",
            details={
                "expected": manifest.manifest_hash,
                "actual": actual_manifest_hash,
            },
        )
    return manifest


class FileRevisionRepository:
    """Private file repository for immutable revision metadata and pointers."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve() / "revision-store"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _project_root(self, project_id: str) -> Path:
        return (
            self.root
            / "projects"
            / safe_storage_segment(project_id, label="project id")
        )

    def _manifest_path(self, project_id: str, revision_id: str) -> Path:
        return (
            self._project_root(project_id)
            / "revisions"
            / f"{safe_storage_segment(revision_id, label='revision id')}.json"
        )

    def _pointer_path(self, project_id: str, pointer: RevisionPointer) -> Path:
        return (
            self._project_root(project_id)
            / "pointers"
            / f"{pointer.value}.json"
        )

    def save(self, manifest: RevisionManifest) -> None:
        target = self._manifest_path(manifest.project_id, manifest.id)
        payload = _canonical_json(_manifest_payload(manifest))
        with self._lock:
            if target.exists():
                existing = target.read_bytes()
                if existing == payload:
                    return
                raise ConflictError(
                    "immutable revision 已存在且内容不同",
                    details={"revisionId": manifest.id},
                )
            atomic_replace_bytes(target, payload)

    def get(self, project_id: str, revision_id: str) -> RevisionManifest:
        target = self._manifest_path(project_id, revision_id)
        if not target.is_file():
            raise NotFoundError(
                "revision 不存在",
                details={"projectId": project_id, "revisionId": revision_id},
            )
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageIntegrityError(
                f"revision manifest 无法读取: {target}",
            ) from exc
        manifest = _manifest_from_payload(payload)
        if manifest.project_id != project_id or manifest.id != revision_id:
            raise StorageIntegrityError("revision manifest identity 不匹配")
        return manifest

    def get_pointer(
        self,
        project_id: str,
        pointer: RevisionPointer,
    ) -> str | None:
        target = self._pointer_path(project_id, pointer)
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            revision_id = payload.get("revisionId")
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            raise StorageIntegrityError(
                f"revision pointer 无法读取: {target}",
            ) from exc
        if revision_id is None:
            return None
        return safe_storage_segment(str(revision_id), label="revision id")

    def compare_and_set_pointer(
        self,
        project_id: str,
        pointer: RevisionPointer,
        revision_id: str | None,
        *,
        expected_revision_id: str | None,
    ) -> None:
        if revision_id is not None:
            self.get(project_id, revision_id)
        target = self._pointer_path(project_id, pointer)
        with self._lock:
            current = self.get_pointer(project_id, pointer)
            if current != expected_revision_id:
                raise ConflictError(
                    "revision pointer CAS 冲突",
                    details={
                        "pointer": pointer.value,
                        "expected": expected_revision_id,
                        "actual": current,
                    },
                )
            atomic_replace_bytes(
                target,
                _canonical_json({"revisionId": revision_id}),
            )


def infer_content_type(path: str) -> str:
    normalized = safe_workspace_path(path)
    suffix = _pure_suffix(normalized)
    return {
        ".md": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".ref": "text/x-creator-ref; charset=utf-8",
        ".vtt": "text/vtt; charset=utf-8",
        ".ctm": "text/x-ctm; charset=utf-8",
    }.get(suffix, "application/octet-stream")


def _pure_suffix(path: str) -> str:
    # Kept local to avoid exposing host-OS path rules for POSIX workspace paths.
    name = path.rsplit("/", 1)[-1]
    return f".{name.rsplit('.', 1)[-1]}" if "." in name else ""


class RevisionStore:
    def __init__(
        self,
        content_store: ContentStore,
        *,
        repository: RevisionRepository | None = None,
    ) -> None:
        self.content_store = content_store
        self.repository = repository or FileRevisionRepository(
            content_store.root,
        )

    def _normalize_entries(
        self,
        entries: Mapping[str, RevisionEntry] | Iterable[RevisionEntry],
    ) -> tuple[RevisionEntry, ...]:
        values = (
            list(entries.values())
            if isinstance(entries, Mapping)
            else list(entries)
        )
        ordered = tuple(sorted(values, key=lambda item: item.path))
        if len({entry.path for entry in ordered}) != len(ordered):
            raise ValidationError("revision entries path 重复")
        for entry in ordered:
            if not self.content_store.verify(
                entry.blob_hash,
                namespace="blob",
            ):
                raise StorageIntegrityError(
                    "revision entry 引用不存在的 blob",
                    details={"path": entry.path, "blobHash": entry.blob_hash},
                )
        return ordered

    def entries_from_files(
        self,
        files: Mapping[str, str | bytes | bytearray | memoryview],
    ) -> tuple[RevisionEntry, ...]:
        entries: list[RevisionEntry] = []
        for path, value in files.items():
            normalized = safe_workspace_path(path)
            payload = (
                value.encode("utf-8")
                if isinstance(value, str)
                else bytes(value)
            )
            stored = self.content_store.put_bytes(payload, namespace="blob")
            entries.append(
                RevisionEntry(
                    path=normalized,
                    blob_hash=stored.sha256,
                    size=stored.size,
                    content_type=infer_content_type(normalized),
                ),
            )
        return tuple(sorted(entries, key=lambda item: item.path))

    def create_revision(
        self,
        *,
        project_id: str,
        kind: RevisionKind | str,
        entries: Mapping[str, RevisionEntry] | Iterable[RevisionEntry],
        parent_revision_id: str | None = None,
        revision_id: str | None = None,
        created_at: str | None = None,
    ) -> RevisionManifest:
        safe_storage_segment(project_id, label="project id")
        normalized_kind = RevisionKind(kind)
        normalized_entries = self._normalize_entries(entries)
        if parent_revision_id is not None:
            parent = self.get(project_id, parent_revision_id)
            if (
                parent.project_id != project_id
            ):  # defensive for custom repositories
                raise ValidationError("parent revision 不属于当前 Project")
        identifier = revision_id or new_id("revision")
        safe_storage_segment(identifier, label="revision id")
        timestamp = created_at or utc_now_iso()
        tree_hash = tree_hash_for_entries(normalized_entries)
        core = _manifest_core_payload(
            revision_id=identifier,
            project_id=project_id,
            kind=normalized_kind,
            parent_revision_id=parent_revision_id,
            tree_hash=tree_hash,
            entries=normalized_entries,
            created_at=timestamp,
        )
        manifest = RevisionManifest(
            id=identifier,
            project_id=project_id,
            kind=normalized_kind,
            parent_revision_id=parent_revision_id,
            tree_hash=tree_hash,
            entries=normalized_entries,
            created_at=timestamp,
            manifest_hash=hashlib.sha256(_canonical_json(core)).hexdigest(),
        )
        self.repository.save(manifest)
        return manifest

    def create_initial_approved_revision(
        self,
        *,
        project_id: str,
        files: Mapping[str, str | bytes | bytearray | memoryview]
        | None = None,
    ) -> RevisionManifest:
        entries = self.entries_from_files(files or {})
        requested_tree_hash = tree_hash_for_entries(entries)
        current_id = self.repository.get_pointer(
            project_id,
            RevisionPointer.APPROVED,
        )
        if current_id is not None:
            current = self.get(project_id, current_id)
            if current.tree_hash != requested_tree_hash:
                raise ConflictError(
                    "Project 已有不同的 initial Approved Revision",
                    details={
                        "approvedRevisionId": current.id,
                        "approvedTreeHash": current.tree_hash,
                        "requestedTreeHash": requested_tree_hash,
                    },
                )
            return current

        manifest = self.create_revision(
            project_id=project_id,
            kind=RevisionKind.APPROVED,
            entries=entries,
        )
        try:
            self.repository.compare_and_set_pointer(
                project_id,
                RevisionPointer.APPROVED,
                manifest.id,
                expected_revision_id=None,
            )
        except ConflictError:
            # A concurrent creator may have won after our immutable manifest was
            # written.  Its pointer is authoritative; the orphan is safe for GC.
            current_id = self.repository.get_pointer(
                project_id,
                RevisionPointer.APPROVED,
            )
            if current_id is None:
                raise
            current = self.get(project_id, current_id)
            if current.tree_hash != manifest.tree_hash:
                raise
            return current
        return manifest

    def get(self, project_id: str, revision_id: str) -> RevisionManifest:
        manifest = self.repository.get(project_id, revision_id)
        # Validate every content reference on read, not merely at creation.
        self._normalize_entries(manifest.entries)
        return manifest

    def get_approved(self, project_id: str) -> RevisionManifest:
        revision_id = self.repository.get_pointer(
            project_id,
            RevisionPointer.APPROVED,
        )
        if revision_id is None:
            raise NotFoundError(
                "Project 尚无 Approved Revision",
                details={"projectId": project_id},
            )
        return self.get(project_id, revision_id)

    def set_approved(
        self,
        project_id: str,
        revision_id: str,
        *,
        expected_revision_id: str | None,
    ) -> RevisionManifest:
        manifest = self.get(project_id, revision_id)
        if manifest.kind is not RevisionKind.APPROVED:
            raise ValidationError("Approved pointer 只能指向 APPROVED revision")
        self.repository.compare_and_set_pointer(
            project_id,
            RevisionPointer.APPROVED,
            revision_id,
            expected_revision_id=expected_revision_id,
        )
        return manifest
