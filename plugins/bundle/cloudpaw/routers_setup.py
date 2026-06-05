# -*- coding: utf-8 -*-
"""API router builders for CloudPaw plugin.

Returns FastAPI APIRouter instances that the plugin registers via
``api.register_http_router()`` — no manual app mounting needed.
"""

import logging

logger = logging.getLogger(__name__)


def build_plugin_routers():
    """Build and return all plugin API routers.

    The caller should register each router via
    ``api.register_http_router(router, prefix=...)``.
    """
    from fastapi import APIRouter, Query

    # pylint: disable=no-name-in-module
    from qwenpaw.app.interaction import InteractionManager

    # ── Interaction router ──────────────────────────────────────────────

    interaction_router = APIRouter(
        prefix="/interaction",
        tags=["interaction"],
    )

    from pydantic import BaseModel

    class InteractionRequest(BaseModel):
        session_id: str
        result: str

    @interaction_router.post("")
    async def resolve_interaction(body: InteractionRequest) -> dict:
        success = InteractionManager.resolve(body.session_id, body.result)
        if not success:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail="No pending interaction for this session",
            )
        return {"status": "ok"}

    # ── PRD router ──────────────────────────────────────────────────────

    prd_router = APIRouter(prefix="/prd", tags=["prd"])

    @prd_router.get("")
    async def read_prd(
        loop_dir: str = Query(...),
        timestamp: str = Query(None, description="Snapshot timestamp"),
    ) -> dict:
        """Read prd.json (or a historical snapshot) from a mission loop dir."""
        import json
        from pathlib import Path
        from fastapi import HTTPException

        base = Path(loop_dir).expanduser().resolve()
        prd_path = base / "prd.json"

        if timestamp:
            snap_path = base / "snapshots" / f"{timestamp}.json"
            if snap_path.exists():
                prd_path = snap_path

        if not prd_path.exists():
            raise HTTPException(
                status_code=404,
                detail="prd.json not found",
            )

        try:
            return json.loads(prd_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prd.json: {exc}",
            ) from exc

    # ── A2A router ──────────────────────────────────────────────────────

    from .routers.a2a import router as a2a_router

    return [
        (interaction_router, "/interaction"),
        (prd_router, "/prd"),
        (a2a_router, "/a2a"),
    ]
