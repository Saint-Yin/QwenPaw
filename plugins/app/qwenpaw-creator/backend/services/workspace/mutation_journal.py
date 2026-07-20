"""Persistent, append-only typed Mutation Journal."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Protocol

from domain.errors import ConflictError, StorageIntegrityError, ValidationError
from domain.ids import utc_now_iso

from .content_store import atomic_replace_bytes
from .mutations import (
    MutationRecord,
    mutation_from_dict,
    mutation_to_dict,
    safe_storage_segment,
)


class MutationJournalRepository(Protocol):
    def load(self, project_id: str, transaction_id: str) -> tuple[MutationRecord, ...]: ...

    def compare_and_append(
        self,
        project_id: str,
        transaction_id: str,
        records: tuple[MutationRecord, ...],
        *,
        expected_last_seq: int,
    ) -> None: ...


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _records_hash(records: Iterable[MutationRecord]) -> str:
    return hashlib.sha256(
        _canonical_json([mutation_to_dict(record) for record in records])
    ).hexdigest()


class FileMutationJournalRepository:
    """Private file repository for the append-only workspace mutation journal."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve() / "mutation-journal"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, project_id: str, transaction_id: str) -> Path:
        return (
            self.root
            / "projects"
            / safe_storage_segment(project_id, label="project id")
            / "transactions"
            / f"{safe_storage_segment(transaction_id, label='transaction id')}.json"
        )

    def load(self, project_id: str, transaction_id: str) -> tuple[MutationRecord, ...]:
        target = self._path(project_id, transaction_id)
        if not target.exists():
            return ()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            records = tuple(mutation_from_dict(item) for item in payload.get("records", []))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise StorageIntegrityError(f"Mutation Journal 无法读取: {target}") from exc
        if payload.get("projectId") != project_id or payload.get("transactionId") != transaction_id:
            raise StorageIntegrityError("Mutation Journal identity 不匹配")
        if [record.seq for record in records] != list(range(1, len(records) + 1)):
            raise StorageIntegrityError("Mutation Journal seq 不连续")
        if any(
            record.project_id != project_id or record.transaction_id != transaction_id
            for record in records
        ):
            raise StorageIntegrityError("Mutation Journal record 归属不匹配")
        actual_hash = _records_hash(records)
        if payload.get("journalHash") != actual_hash:
            raise StorageIntegrityError(
                "Mutation Journal hash 不匹配",
                details={"expected": payload.get("journalHash"), "actual": actual_hash},
            )
        return records

    def compare_and_append(
        self,
        project_id: str,
        transaction_id: str,
        records: tuple[MutationRecord, ...],
        *,
        expected_last_seq: int,
    ) -> None:
        if not records:
            return
        target = self._path(project_id, transaction_id)
        with self._lock:
            current = self.load(project_id, transaction_id)
            current_last_seq = current[-1].seq if current else 0
            if current_last_seq != expected_last_seq:
                raise ConflictError(
                    "Mutation Journal seq CAS 冲突",
                    details={"expected": expected_last_seq, "actual": current_last_seq},
                )
            expected_seqs = list(
                range(expected_last_seq + 1, expected_last_seq + len(records) + 1)
            )
            if [record.seq for record in records] != expected_seqs:
                raise ValidationError("append records seq 必须连续")
            combined = current + records
            payload = {
                "version": 1,
                "projectId": project_id,
                "transactionId": transaction_id,
                "records": [mutation_to_dict(record) for record in combined],
                "journalHash": _records_hash(combined),
            }
            atomic_replace_bytes(target, _canonical_json(payload))


class MutationJournal:
    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        repository: MutationJournalRepository | None = None,
    ) -> None:
        self.repository = repository or FileMutationJournalRepository(root)

    def records(
        self,
        project_id: str,
        transaction_id: str,
        *,
        after_seq: int = 0,
    ) -> tuple[MutationRecord, ...]:
        if after_seq < 0:
            raise ValidationError("after_seq 不能小于 0")
        return tuple(
            record
            for record in self.repository.load(project_id, transaction_id)
            if record.seq > after_seq
        )

    def append(
        self,
        record: MutationRecord,
        *,
        expected_last_seq: int | None = None,
    ) -> MutationRecord:
        return self.append_many(
            [record], expected_last_seq=expected_last_seq
        )[0]

    def append_many(
        self,
        records: Iterable[MutationRecord],
        *,
        expected_last_seq: int | None = None,
    ) -> tuple[MutationRecord, ...]:
        pending = tuple(records)
        if not pending:
            return ()
        project_id = pending[0].project_id
        transaction_id = pending[0].transaction_id
        safe_storage_segment(project_id, label="project id")
        safe_storage_segment(transaction_id, label="transaction id")
        if any(
            item.project_id != project_id or item.transaction_id != transaction_id
            for item in pending
        ):
            raise ValidationError("append_many 只能包含同一 Project/Transaction 的 records")

        current = self.repository.load(project_id, transaction_id)
        by_id = {item.id: item for item in current}
        new_records: list[MutationRecord] = []
        resolved: list[MutationRecord] = []
        next_seq = current[-1].seq + 1 if current else 1
        for item in pending:
            existing = by_id.get(item.id)
            if existing is not None:
                candidate = replace(item, seq=existing.seq, created_at=existing.created_at)
                if candidate != existing:
                    raise ConflictError(
                        "mutation id 已存在且 payload 不同",
                        details={"mutationId": item.id},
                    )
                resolved.append(existing)
                continue
            if item.seq not in {0, next_seq}:
                raise ValidationError("新 mutation seq 必须为 0 或下一连续值")
            assigned = replace(
                item,
                seq=next_seq,
                created_at=item.created_at or utc_now_iso(),
            )
            new_records.append(assigned)
            resolved.append(assigned)
            by_id[assigned.id] = assigned
            next_seq += 1

        if not new_records:
            return tuple(resolved)
        current_last_seq = current[-1].seq if current else 0
        if expected_last_seq is not None and current_last_seq != expected_last_seq:
            raise ConflictError(
                "Mutation Journal expected_last_seq 已过期",
                details={"expected": expected_last_seq, "actual": current_last_seq},
            )
        self.repository.compare_and_append(
            project_id,
            transaction_id,
            tuple(new_records),
            expected_last_seq=current_last_seq,
        )
        return tuple(resolved)

    def seq_range(self, project_id: str, transaction_id: str) -> tuple[int, int] | None:
        records = self.repository.load(project_id, transaction_id)
        if not records:
            return None
        return records[0].seq, records[-1].seq
