# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,unused-argument
"""GET /storage/profile reports the runtime footprint without touching it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

TOTAL_KEYS = {
    "taskWorkBytes",
    "taskWorkLegacyBytes",
    "taskWorkReclaimableBytes",
    "transactionsBytes",
    "transactionsLegacyBytes",
    "orphanBytes",
}


def test_profile_answers_even_with_no_projects(
    api_request,
    app,
    api_runtime_root,
):
    response = api_request(app, "GET", "/storage/profile")

    assert response.status_code == 200
    body = response.json()
    assert Path(body["dataRoot"]).is_dir()
    assert body["scratchReleaseEnabled"] is True
    assert body["projects"] == []
    assert set(body["totals"]) == TOTAL_KEYS
    assert all(value == 0 for value in body["totals"].values())


def test_orphan_scan_is_opt_in(api_request, app):
    response = api_request(
        app,
        "GET",
        "/storage/profile",
        params={"includeOrphans": "true"},
    )

    assert response.status_code == 200
    assert set(response.json()["totals"]) == TOTAL_KEYS


PROJECT_A = "project-" + "a" * 32
PROJECT_B = "project-" + "b" * 32
BASELINE = datetime(2026, 1, 10, tzinfo=timezone.utc)


def _seed_legacy_project(root: Path, project_id: str, *, count: int) -> Path:
    """A Project whose whole commit history predates its baseline.

    This is the imported-Project shape from the field: every transaction
    settled, none of it after the day the Project started being managed, so an
    unauthorized sweep frees nothing at all.
    """

    project = root / project_id
    transactions = project / "runtime" / "transactions"
    transactions.mkdir(parents=True)
    (project / "project.json").write_text("{}", encoding="utf-8")
    (project / "runtime" / ".storage-baseline.json").write_text(
        json.dumps({"version": 1, "since": BASELINE.isoformat()}),
        encoding="utf-8",
    )
    for index in range(count):
        directory = transactions / f"txn-{index:03d}"
        directory.mkdir()
        (directory / "journal.json").write_text(
            json.dumps({"state": "RUNTIME_FINALIZED"}),
            encoding="utf-8",
        )
        (directory / "final.json").write_bytes(b"x" * 64)
        moment = (BASELINE - timedelta(days=count - index)).timestamp()
        os.utime(directory, (moment, moment))
    return transactions


def test_reclaim_history_refuses_an_unconfirmed_press(
    api_request,
    app,
    api_runtime_root,
):
    transactions = _seed_legacy_project(api_runtime_root, PROJECT_A, count=60)

    missing = api_request(
        app,
        "POST",
        f"/storage/projects/{PROJECT_A}/reclaim-history",
        json={},
    )
    denied = api_request(
        app,
        "POST",
        f"/storage/projects/{PROJECT_A}/reclaim-history",
        json={"confirm": False},
    )

    assert missing.status_code == 400
    assert denied.status_code == 400
    assert missing.json()["code"] == "BAD_REQUEST"
    assert len(list(transactions.iterdir())) == 60


def test_reclaim_history_sweeps_only_the_authorized_project(
    api_request,
    app,
    api_runtime_root,
):
    first = _seed_legacy_project(api_runtime_root, PROJECT_A, count=60)
    second = _seed_legacy_project(api_runtime_root, PROJECT_B, count=60)

    response = api_request(
        app,
        "POST",
        f"/storage/projects/{PROJECT_A}/reclaim-history",
        json={"confirm": True},
    )

    assert response.status_code == 200
    body = response.json()
    # Retention still applies: the newest 50 receipts are kept even when a
    # person authorizes the history, so only the surplus left the disk.
    assert body["removedTransactions"] == 10
    assert body["transactionBytes"] > 0
    assert len(list(first.iterdir())) == 50
    assert len(list(second.iterdir())) == 60

    profile = api_request(app, "GET", "/storage/profile").json()
    rows = {item["projectId"]: item for item in profile["projects"]}
    assert rows[PROJECT_A]["historyAuthorizedAt"]
    assert rows[PROJECT_B]["historyAuthorizedAt"] is None
