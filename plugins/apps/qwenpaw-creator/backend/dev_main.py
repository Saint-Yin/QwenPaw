# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position
"""Standalone FastAPI app for local Creator UI development."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from utils.env import load_project_env

load_project_env()

from api.dependencies import creator_error_handler  # noqa: E402
from api.router import router as creator_router  # noqa: E402
from domain.errors import CreatorError  # noqa: E402
from services.file_agent_runtime.registry import (  # noqa: E402
    start_creator_agent_runtime,
    stop_creator_agent_runtime,
)
from services.media_files import (  # noqa: E402
    shutdown_file_media_execution_services,
    start_file_media_execution_services,
)
from services.project_files.facade import (  # noqa: E402
    clear_creator_file_service_registry,
    creator_file_services,
)
from services.runtime_files.runtime_dependencies import (  # noqa: E402
    ensure_creator_runtime_dependencies,
)
from services.storage_root import require_creator_data_root  # noqa: E402
from services.source_analysis import (  # noqa: E402
    recover_interrupted_source_analysis,
    shutdown_source_analysis_services,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Construction performs Project and Review journal recovery before the API
    # accepts traffic.  No database migration or SQL runtime is part of boot.
    await asyncio.to_thread(ensure_creator_runtime_dependencies)
    services = creator_file_services(require_creator_data_root())
    recover_interrupted_source_analysis(services)
    try:
        await start_file_media_execution_services(services)
        await start_creator_agent_runtime(services)
        yield
    finally:
        try:
            await shutdown_file_media_execution_services()
        finally:
            try:
                await shutdown_source_analysis_services()
            finally:
                try:
                    await stop_creator_agent_runtime()
                finally:
                    clear_creator_file_service_registry()


app = FastAPI(title="QwenPaw-Creator Local Dev Backend", lifespan=lifespan)
app.add_exception_handler(CreatorError, creator_error_handler)
app.include_router(creator_router, prefix="/api/qwenpaw-creator")
