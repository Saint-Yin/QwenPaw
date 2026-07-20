"""Full-tree diff for immutable revisions and working blob mappings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.errors import StorageIntegrityError

from .content_store import ContentStore
from .mutations import MutationKind, MutationRecord, is_media_ref
from .revision_store import RevisionEntry


class TreeSnapshot(Protocol):
    tree_hash: str
    entries: tuple[RevisionEntry, ...]


@dataclass(frozen=True, slots=True)
class DiffOperation:
    kind: MutationKind
    path: str
    source_path: str | None
    destination_path: str | None
    before_entry: RevisionEntry | None
    after_entry: RevisionEntry | None
    before_ref: str | None = None
    after_ref: str | None = None
    mutation_ids: tuple[str, ...] = ()

    @property
    def affected_paths(self) -> tuple[str, ...]:
        if self.source_path and self.destination_path:
            return (self.source_path, self.destination_path)
        return (self.path,)


@dataclass(frozen=True, slots=True)
class TreeDiff:
    base_tree_hash: str
    target_tree_hash: str
    operations: tuple[DiffOperation, ...]

    @property
    def is_empty(self) -> bool:
        return not self.operations

    def operations_of_kind(self, kind: MutationKind | str) -> tuple[DiffOperation, ...]:
        normalized = MutationKind(kind)
        return tuple(item for item in self.operations if item.kind is normalized)


class DiffService:
    def __init__(self, content_store: ContentStore) -> None:
        self.content_store = content_store

    def _read_ref(self, entry: RevisionEntry | None) -> str | None:
        if entry is None or not entry.path.endswith(".ref"):
            return None
        try:
            return self.content_store.read_text(entry.blob_hash, namespace="blob")
        except StorageIntegrityError:
            raise

    @staticmethod
    def _mutation_ids_for_paths(
        journal: tuple[MutationRecord, ...], paths: set[str]
    ) -> tuple[str, ...]:
        return tuple(
            record.id
            for record in journal
            if paths.intersection(record.affected_paths)
        )

    def compare(
        self,
        base: TreeSnapshot,
        target: TreeSnapshot,
        *,
        journal: tuple[MutationRecord, ...] = (),
    ) -> TreeDiff:
        base_entries = {entry.path: entry for entry in base.entries}
        target_entries = {entry.path: entry for entry in target.entries}
        consumed_base: set[str] = set()
        consumed_target: set[str] = set()
        operations: list[DiffOperation] = []

        # Identity-preserving move/rename comes from typed Journal records, not
        # from a best-effort comparison of two snapshots.
        for record in sorted(journal, key=lambda item: item.seq):
            if record.kind not in {MutationKind.MOVE, MutationKind.RENAME}:
                continue
            source = record.source_path or ""
            destination = record.destination_path or ""
            before = base_entries.get(source)
            after = target_entries.get(destination)
            if before is None or after is None:
                # The typed record may describe an intermediate move later
                # deleted or moved again.  Only the net tree diff is reviewable.
                continue
            operations.append(
                DiffOperation(
                    kind=record.kind,
                    path=destination,
                    source_path=source,
                    destination_path=destination,
                    before_entry=before,
                    after_entry=after,
                    before_ref=self._read_ref(before),
                    after_ref=self._read_ref(after),
                    mutation_ids=(record.id,),
                )
            )
            consumed_base.add(source)
            consumed_target.add(destination)

        common_paths = sorted(set(base_entries).intersection(target_entries))
        for path in common_paths:
            if path in consumed_base or path in consumed_target:
                continue
            before = base_entries[path]
            after = target_entries[path]
            if before.blob_hash == after.blob_hash and before.content_type == after.content_type:
                continue
            before_ref = self._read_ref(before)
            after_ref = self._read_ref(after)
            if path.endswith(".ref"):
                kind = (
                    MutationKind.REPLACE_MEDIA
                    if is_media_ref(before_ref) or is_media_ref(after_ref)
                    else MutationKind.CHANGE_REFERENCE
                )
            else:
                kind = MutationKind.UPDATE
            operations.append(
                DiffOperation(
                    kind=kind,
                    path=path,
                    source_path=path,
                    destination_path=path,
                    before_entry=before,
                    after_entry=after,
                    before_ref=before_ref,
                    after_ref=after_ref,
                    mutation_ids=self._mutation_ids_for_paths(journal, {path}),
                )
            )

        for path in sorted(set(base_entries).difference(target_entries) - consumed_base):
            before = base_entries[path]
            operations.append(
                DiffOperation(
                    kind=MutationKind.DELETE,
                    path=path,
                    source_path=path,
                    destination_path=None,
                    before_entry=before,
                    after_entry=None,
                    before_ref=self._read_ref(before),
                    mutation_ids=self._mutation_ids_for_paths(journal, {path}),
                )
            )

        for path in sorted(set(target_entries).difference(base_entries) - consumed_target):
            after = target_entries[path]
            operations.append(
                DiffOperation(
                    kind=MutationKind.CREATE,
                    path=path,
                    source_path=None,
                    destination_path=path,
                    before_entry=None,
                    after_entry=after,
                    after_ref=self._read_ref(after),
                    mutation_ids=self._mutation_ids_for_paths(journal, {path}),
                )
            )

        ordered = tuple(
            sorted(
                operations,
                key=lambda item: (
                    item.path,
                    item.kind.value,
                    item.source_path or "",
                    item.destination_path or "",
                ),
            )
        )
        return TreeDiff(
            base_tree_hash=base.tree_hash,
            target_tree_hash=target.tree_hash,
            operations=ordered,
        )

    @staticmethod
    def unjournaled_paths(diff: TreeDiff) -> tuple[str, ...]:
        """Return real tree changes not covered by any typed mutation record."""
        paths: set[str] = set()
        for operation in diff.operations:
            if not operation.mutation_ids:
                paths.update(operation.affected_paths)
        return tuple(sorted(paths))
