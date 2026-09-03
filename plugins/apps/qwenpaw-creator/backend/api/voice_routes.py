# -*- coding: utf-8 -*-
"""Character-voice HTTP surface: capability probe plus direct enrollment.

Voice enrollment used to be reachable only through the assistant agent's
create_character_voice tool. The asset library drives it directly here —
same executor, no agent turn.

Notification semantics: completion publishes a quiet-level event on the
runtime notification bus — it lands in the per-project outbox and rides
along with the next steer/digest, never waking the agent by itself
(same policy as manual work-graph dispatch node transitions).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header

from domain.errors import ValidationError
from models import tts_capabilities
from models.config import get_tts_model_name
from services.file_agent_runtime.notifications import RuntimeEventKind
from services.file_agent_runtime.registry import get_creator_agent_runtime
from services.project_files.facade import CreatorFileServices
from services.specialist_tools import (
    character_voice_tool_spec,
    invoke_character_voice_tool,
)

from .dependencies import CreatorErrorRoute, project_file_services


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["character-voice"],
    route_class=CreatorErrorRoute,
)


@router.get("/voice-capabilities")
async def get_voice_capabilities(project_id: str) -> dict[str, Any]:
    # Capability is deployment-wide; kept per-project for URL symmetry.
    del project_id
    model = get_tts_model_name()
    capability = tts_capabilities.capability_for(model)
    return {
        "model": model,
        "configured": character_voice_tool_spec() is not None,
        # Design = build a timbre from a plain-language prompt; when false the
        # UI must collect an audio sample instead of a voice prompt.
        "supportsDesign": bool(capability and capability.supports_design),
    }


@router.post("/character-voice")
async def create_character_voice(
    project_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    character_ref = str(payload.get("characterRef") or "").strip()
    if not character_ref:
        raise ValidationError("characterRef is required")
    if not character_ref.startswith("asset:"):
        character_ref = f"asset:{character_ref.replace('visual-entity:', '')}"
    request_key = idempotency_key or f"voice-http-{uuid4().hex}"
    result = await invoke_character_voice_tool(
        services,
        project_id=project_id,
        target_ref=character_ref,
        arguments=payload,
        idempotency_key=request_key,
    )
    runtime = get_creator_agent_runtime()
    if runtime is not None and not result.get("replayed"):
        try:
            await runtime.notifications.notify(
                project_id,
                kind=RuntimeEventKind.VOICE_ENROLLED,
                request_id=f"voice-enrolled-{request_key}",
                text=(
                    f"角色 {result.get('entityId')} 的参考音色已通过资产库"
                    f"直接生成并绑定（{result.get('voiceOrigin')}）。"
                    "这是状态同步，不是新的用户指令。"
                ),
                payload={
                    "entityId": result.get("entityId"),
                    "voiceOrigin": result.get("voiceOrigin"),
                    "sampleSourceVersionId": result.get(
                        "sampleSourceVersionId",
                    ),
                },
            )
        except Exception:  # noqa: BLE001 - the bind already succeeded
            pass
    return result
