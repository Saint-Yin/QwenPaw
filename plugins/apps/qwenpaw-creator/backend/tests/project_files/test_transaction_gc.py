# -*- coding: utf-8 -*-
"""The startup transaction sweep.

Deletion needs the strictest reading of its own rules: a transaction survives
unless its journal positively says it settled, and history the Project arrived
with is never this build's to reclaim.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from services.media_files.task_scratch import remember_scratch_baseline
from services.project_files.transaction_gc import (
    collect_project_transactions,
    collect_terminal_transactions,
    transaction_gc_enabled,
)
from services.project_files.transaction_index import (
    TransactionJournalIndex,
    plan_transaction_scan,
    record_transaction_scan,
)
from services.runtime_files.atomic_store import AtomicJsonRecordStore

pytestmark = pytest.mark.unit

BASELINE = datetime(2026, 1, 10, tzinfo=timezone.utc)


def _runtime(tmp_path) -> Path:
    root = tmp_path / "project-1"
    (root / "runtime" / "transactions").mkdir(parents=True)
    return root


def _transaction(
    project_root: Path,
    name: str,
    state: str | None,
    *,
    age_days: int,
    body_bytes: int = 128,
) -> Path:
    directory = project_root / "runtime" / "transactions" / name
    directory.mkdir(parents=True)
    if state is not None:
        (directory / "journal.json").write_text(
            json.dumps({"state": state}),
            encoding="utf-8",
        )
    elif name == "corrupt":
        (directory / "journal.json").write_text("{broken", encoding="utf-8")
    if body_bytes:
        (directory / "final.json").write_bytes(b"x" * body_bytes)
    moment = (BASELINE + timedelta(days=age_days)).timestamp()
    os.utime(directory, (moment, moment))
    return directory


def _managed(tmp_path) -> Path:
    project_root = _runtime(tmp_path)
    remember_scratch_baseline(project_root, now=BASELINE)
    return project_root


def test_only_the_newest_terminal_transactions_survive(tmp_path):
    project_root = _managed(tmp_path)
    newest = _transaction(
        project_root,
        "txn-new",
        "RUNTIME_FINALIZED",
        age_days=3,
    )
    middle = _transaction(project_root, "txn-mid", "ABORTED", age_days=2)
    oldest = _transaction(
        project_root,
        "txn-old",
        "RUNTIME_FINALIZED",
        age_days=1,
    )

    removed, removed_bytes = collect_project_transactions(
        project_root,
        retention=2,
    )

    # The whole directory is reclaimed, journal and snapshots alike.
    assert removed == 1
    assert removed_bytes >= 128
    assert newest.is_dir() and middle.is_dir()
    assert not oldest.exists()


def test_transactions_that_did_not_settle_are_kept(tmp_path):
    project_root = _managed(tmp_path)
    survivors = [
        _transaction(project_root, "prepared", "PREPARED", age_days=1),
        _transaction(project_root, "replaced", "PROJECT_REPLACED", age_days=1),
        _transaction(project_root, "no-journal", None, age_days=1),
        _transaction(project_root, "corrupt", None, age_days=1),
        _transaction(project_root, "settled", "RUNTIME_FINALIZED", age_days=1),
    ]

    removed, _size = collect_project_transactions(project_root, retention=0)

    # retention=0 drops settled history, but only what the journal vouches for.
    assert removed == 1
    assert [path.exists() for path in survivors[:4]] == [True] * 4


def test_an_unknown_state_is_not_treated_as_terminal(tmp_path):
    project_root = _managed(tmp_path)
    future = _transaction(
        project_root,
        "txn-future",
        "SOMETHING_NEW",
        age_days=1,
    )

    assert collect_project_transactions(project_root, retention=0) == (0, 0)
    assert future.is_dir()


def test_history_before_the_baseline_is_left_alone(tmp_path):
    project_root = _managed(tmp_path)
    _transaction(project_root, "txn-legacy", "ABORTED", age_days=-5)

    assert collect_project_transactions(project_root, retention=0) == (0, 0)
    assert (project_root / "runtime" / "transactions" / "txn-legacy").is_dir()


def test_a_project_without_a_baseline_is_skipped(tmp_path):
    project_root = _runtime(tmp_path)
    directory = _transaction(
        project_root,
        "txn-1",
        "RUNTIME_FINALIZED",
        age_days=1,
    )

    assert collect_project_transactions(project_root, retention=0) == (0, 0)
    assert directory.is_dir()


def test_the_settled_listing_is_invalidated(tmp_path):
    project_root = _managed(tmp_path)
    transactions_root = project_root / "runtime" / "transactions"
    _transaction(project_root, "txn-1", "RUNTIME_FINALIZED", age_days=1)
    _transaction(project_root, "txn-2", "RUNTIME_FINALIZED", age_days=2)
    record_transaction_scan(
        transactions_root,
        plan_transaction_scan(
            transactions_root,
            current_transaction_id="txn-2",
        ),
        {"txn-1": "RUNTIME_FINALIZED"},
    )

    collect_project_transactions(project_root, retention=1)

    assert not (transactions_root / ".journal-index.json").exists()


def test_a_no_op_sweep_keeps_the_index(tmp_path):
    project_root = _managed(tmp_path)
    transactions_root = project_root / "runtime" / "transactions"
    _transaction(project_root, "txn-1", "RUNTIME_FINALIZED", age_days=1)
    record_transaction_scan(
        transactions_root,
        plan_transaction_scan(
            transactions_root,
            current_transaction_id="txn-1",
        ),
        {"txn-1": "RUNTIME_FINALIZED"},
    )

    assert collect_project_transactions(project_root, retention=50) == (0, 0)

    stored = AtomicJsonRecordStore(
        transactions_root / ".journal-index.json",
        TransactionJournalIndex,
    ).read()
    # Untouched: the sweep removed nothing, so the commit path's cache still
    # describes the directory it was built from.
    assert stored.pending == ("txn-1",)


def test_switch_off_keeps_every_directory(tmp_path, monkeypatch):
    project_root = _managed(tmp_path)
    directory = _transaction(
        project_root,
        "txn-1",
        "RUNTIME_FINALIZED",
        age_days=1,
    )
    monkeypatch.setenv("CREATOR_TRANSACTION_GC_ENABLED", "0")
    assert not transaction_gc_enabled()

    assert collect_project_transactions(project_root, retention=0) == (0, 0)
    assert directory.is_dir()


class _Services:
    """The two Project-store methods the sweep needs."""

    def __init__(self, root: Path, broken: tuple[str, ...] = ()):
        self.root = root
        self.broken = broken

        projects = self

        class _Projects:
            @staticmethod
            def discover_project_ids():
                return ["project-1", "project-2", "project-broken"]

            @staticmethod
            def project_root(project_id):
                if project_id in projects.broken:
                    raise RuntimeError("unreadable store")
                return projects.root / project_id

        self.projects = _Projects


def test_sweep_covers_every_project_and_never_raises(tmp_path):
    first = tmp_path / "project-1" / "runtime" / "transactions"
    first.mkdir(parents=True)
    remember_scratch_baseline(tmp_path / "project-1", now=BASELINE)
    _transaction(tmp_path / "project-1", "p1-old", "ABORTED", age_days=1)
    _transaction(tmp_path / "project-1", "p1-new", "ABORTED", age_days=2)
    second = tmp_path / "project-2" / "runtime" / "transactions"
    second.mkdir(parents=True)
    # No baseline for project-2: its history is not provably this build's.
    _transaction(tmp_path / "project-2", "p2-old", "ABORTED", age_days=1)

    summary = collect_terminal_transactions(
        _Services(tmp_path, broken=("project-broken",)),
        retention=1,
    )

    assert summary.projects == 3
    assert summary.swept_projects == 1
    assert summary.removed_transactions == 1
    assert not (first / "p1-old").exists()
    assert (first / "p1-new").is_dir()
    assert (second / "p2-old").is_dir()
