# -*- coding: utf-8 -*-
"""Storage accounting, plus the one action that takes settled history back."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from domain.errors import BadRequestError, NotFoundError
from schemas.storage import (
    HistoryReclaimRequest,
    HistoryReclaimResultData,
    StorageProfileData,
)
from services.media_files.task_scratch import project_storage_profile
from services.project_files.facade import CreatorFileServices
from services.project_files.storage_reclaim import reclaim_project_history
from services.project_files.store import ProjectNotFound

from .dependencies import CreatorErrorRoute, project_file_services


router = APIRouter(
    prefix="/storage",
    tags=["creator-storage"],
    route_class=CreatorErrorRoute,
)


@router.get("/profile", response_model=StorageProfileData)
async def get_storage_profile(
    include_orphans: bool = Query(False, alias="includeOrphans"),
    services: CreatorFileServices = Depends(project_file_services),
) -> StorageProfileData:
    """Report every Project's footprint split at its release baseline.

    Scanning is a walk over the runtime tree, so it runs off the event loop;
    the orphan scan additionally reads the Asset index and is opt-in.
    """

    profile = await asyncio.to_thread(
        project_storage_profile,
        services,
        include_orphans=include_orphans,
    )
    return StorageProfileData.model_validate(profile)


@router.post(
    "/projects/{project_id}/reclaim-history",
    response_model=HistoryReclaimResultData,
)
async def reclaim_history(
    project_id: str,
    payload: HistoryReclaimRequest,
    services: CreatorFileServices = Depends(project_file_services),
) -> HistoryReclaimResultData:
    """Take one Project's settled history back, for a person who asked for it.

    Pre-baseline history is protected by design -- an upgrade must not rewrite
    what the user arrived with -- so this is the only door, and it requires an
    explicit ``confirm``.  What runs afterwards is the pair of sweeps that
    already exist, over this Project alone: terminal transactions beyond the
    retention window, and terminal Task scratch.  The response reports bytes
    actually freed, never an estimate.
    """

    if not payload.confirm:
        raise BadRequestError("回收历史需要显式确认（confirm=true）")
    try:
        result = await asyncio.to_thread(
            reclaim_project_history,
            services,
            project_id,
        )
    except ProjectNotFound as exc:
        raise NotFoundError(str(exc)) from exc
    return HistoryReclaimResultData.model_validate(
        {
            "projectId": result.project_id,
            "authorizedAt": result.authorized_at.isoformat(),
            "removedTransactions": result.removed_transactions,
            "transactionBytes": result.transaction_bytes,
            "releasedFiles": result.released_files,
            "releasedBytes": result.released_bytes,
        },
    )
