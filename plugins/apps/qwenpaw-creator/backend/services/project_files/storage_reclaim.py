# -*- coding: utf-8 -*-
"""Authorize and run the history reclaim for one Project.

Two sweeps already exist -- terminal transactions and terminal task
scratch -- and both stop at a Project's reclaim baseline: history a
Project arrived with belongs to the user, and an upgrade must not rewrite
it.  A person can lift that boundary, and this module is the only door.  It
records the authorization for one Project, then runs both existing sweeps
over that Project alone and reports what actually left the disk.

Nothing here deletes by hand, so every rule the sweeps already enforce still
applies: only a transaction whose own ``journal.json`` names a terminal state,
the newest receipts inside the retention window, ``QUARANTINED`` work kept as
evidence, a quiet period before a terminal Task's scratch is touched, and both
environment switches.  Authorization opens the date gate; it opens
nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.media_files.task_scratch import (
    authorize_history_reclaim,
    release_orphaned_scratch,
)

from .store import ProjectNotFound
from .transaction_gc import collect_terminal_transactions


@dataclass(frozen=True, slots=True)
class HistoryReclaimResult:
    """What one authorized sweep actually freed."""

    project_id: str
    authorized_at: datetime
    removed_transactions: int
    transaction_bytes: int
    released_files: int
    released_bytes: int


def reclaim_project_history(
    services: Any,
    project_id: str,
    *,
    now: datetime | None = None,
) -> HistoryReclaimResult:
    """Authorize and reclaim one Project's settled history; report the delta.

    The Project is addressed on disk before anything is written, so a malformed
    or unknown id fails without leaving an authorization behind.  Existence is
    the only assertion: a Project whose ``project.json`` no longer validates is
    precisely the case where freeing its settled history still has to work.
    """

    moment = now or datetime.now(timezone.utc)
    project_root = Path(services.projects.project_root(project_id))
    if not services.projects.project_path(project_id).is_file():
        raise ProjectNotFound(f"Project does not exist: {project_id}")
    authorized_at = authorize_history_reclaim(project_root, now=moment)
    transactions = collect_terminal_transactions(
        services,
        project_ids=(project_id,),
    )
    scratch = release_orphaned_scratch(
        services,
        now=moment,
        project_ids=(project_id,),
    )
    return HistoryReclaimResult(
        project_id=project_id,
        authorized_at=authorized_at,
        removed_transactions=transactions.removed_transactions,
        transaction_bytes=transactions.removed_bytes,
        released_files=scratch.removed_files,
        released_bytes=scratch.removed_bytes,
    )
