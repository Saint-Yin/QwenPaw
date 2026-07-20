# -*- coding: utf-8 -*-
"""File-native Source Intelligence analyze and read APIs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import Field

from schemas.assets import SourceIndexQueryResult, SourceIntelligenceIndex
from schemas.common import StrictModel
from services.project_files.facade import CreatorFileServices
from services.source_analysis import source_analysis_service

from .dependencies import (
    CreatorErrorRoute,
    project_file_services,
    resolve_idempotency_key,
)


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["source-intelligence-files"],
    route_class=CreatorErrorRoute,
)


class SourceAnalysisRequest(StrictModel):
    client_request_id: str = Field(alias="clientRequestId")
    source_id: str | None = Field(None, alias="sourceId")
    asset_version_id: str | None = Field(None, alias="assetVersionId")


class SourceAnalysisAccepted(StrictModel):
    task_id: str = Field(alias="taskId")
    run_id: str = Field(alias="runId")
    status: str
    transaction_id: str = Field(alias="transactionId")
    input_generation: int = Field(alias="inputGeneration", ge=0)
    input_etag: str = Field(alias="inputEtag")


@router.post(
    "/assets/{asset_id}/analyze",
    response_model=SourceAnalysisAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_source_asset(
    project_id: str,
    asset_id: str,
    request: SourceAnalysisRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, object]:
    key = resolve_idempotency_key(
        idempotency_key,
        stable_client_id=request.client_request_id,
    )
    arguments: dict[str, str] = {}
    if request.source_id:
        arguments["sourceId"] = request.source_id
    if request.asset_version_id:
        arguments["assetVersionId"] = request.asset_version_id
    dispatch = await source_analysis_service(services).dispatch(
        project_id=project_id,
        target_ref=f"asset:{asset_id}",
        command_id=key,
        arguments=arguments,
        start=True,
    )
    return {
        "taskId": dispatch.task.task_id,
        "runId": dispatch.run.run_id,
        "status": dispatch.task.status.value,
        "transactionId": dispatch.job.round_id,
        "inputGeneration": dispatch.job.input_generation,
        "inputEtag": dispatch.job.input_etag,
    }


@router.get(
    "/assets/{asset_id}/understanding",
    response_model=SourceIntelligenceIndex,
    response_model_by_alias=True,
)
@router.get(
    "/assets/{asset_id}/understanding/{version_id}",
    response_model=SourceIntelligenceIndex,
    response_model_by_alias=True,
)
async def get_asset_understanding(
    project_id: str,
    asset_id: str,
    version_id: str | None = None,
    services: CreatorFileServices = Depends(project_file_services),
) -> SourceIntelligenceIndex:
    return await asyncio.to_thread(
        source_analysis_service(services).load,
        project_id,
        asset_id,
        version_id,
    )


@router.get(
    "/assets/{asset_id}/source-index/query",
    response_model=SourceIndexQueryResult,
    response_model_by_alias=True,
)
async def query_source_index(
    project_id: str,
    asset_id: str,
    query: str = Query(""),
    services: CreatorFileServices = Depends(project_file_services),
) -> SourceIndexQueryResult:
    return await asyncio.to_thread(
        source_analysis_service(services).query,
        project_id,
        asset_id,
        query,
    )


__all__ = ["router"]
