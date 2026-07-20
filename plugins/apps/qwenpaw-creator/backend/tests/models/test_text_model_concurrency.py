# -*- coding: utf-8 -*-
# pylint: disable=protected-access
from __future__ import annotations

import asyncio

import pytest
from agentscope.message import TextBlock
from agentscope.model._model_response import ChatResponse

from domain.enums import SpecialistRole
from models import concurrency as model_concurrency
from services.creator.model_adapter import (
    AgentScopeCreatorModel,
    CreatorRuntimeContext,
)
from services.specialists.model_adapter import AgentScopeSpecialistModel


pytestmark = pytest.mark.unit


class SharedCallProbe:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.entered: list[str] = []
        self.first_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def call(self, label: str, text: str) -> ChatResponse:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.append(label)
        self.first_entered.set()
        try:
            await self.release.wait()
            return ChatResponse(
                id=f"response-{label}",
                content=[TextBlock(text=text)],
                is_last=True,
            )
        finally:
            self.active -= 1


class CreatorProvider:
    model = "qwen3.7-plus"

    def __init__(self, probe: SharedCallProbe, label: str) -> None:
        self.probe = probe
        self.label = label

    async def __call__(self, messages, *, tools=None):
        del messages
        assert tools is None
        return await self.probe.call(
            self.label,
            '完成。\n```json\n{"action":"final","message":"ok",'
            '"awaitUserInput":true}\n```',
        )


class SpecialistProvider:
    model = "qwen3.7-plus"

    def __init__(self, probe: SharedCallProbe) -> None:
        self.probe = probe

    async def __call__(self, messages, tools=None):
        del messages, tools
        return await self.probe.call("specialist", "[SUCCESS]\n\n完成。")


def _context(session_id: str) -> CreatorRuntimeContext:
    return CreatorRuntimeContext(
        project_id=f"project-{session_id}",
        creator_session_id=session_id,
        goal_id=f"goal-{session_id}",
        goal_intent="验证并发",
        success_criteria=(),
        goal_status="ACTIVE",
        remaining_work_refs=(),
        transaction_id=f"transaction-{session_id}",
        transaction_status="ACTIVE",
        working_head="a" * 64,
    )


def test_creator_sessions_and_specialist_share_global_text_concurrency(
    monkeypatch,
) -> None:
    async def scenario():
        monkeypatch.setattr(model_concurrency.config, "TEXT_CONCURRENCY", 1)
        model_concurrency._limiters.clear()
        probe = SharedCallProbe()
        creator_a = AgentScopeCreatorModel(CreatorProvider(probe, "creator-a"))
        creator_b = AgentScopeCreatorModel(CreatorProvider(probe, "creator-b"))
        specialist = AgentScopeSpecialistModel(SpecialistProvider(probe))

        creator_a_task = asyncio.create_task(
            creator_a.complete(
                system_prompt="creator",
                messages=[
                    {
                        "role": "user",
                        "content_parts": [{"type": "text", "text": "A"}],
                    },
                ],
                runtime_context=_context("session-a"),
            ),
        )
        await asyncio.wait_for(probe.first_entered.wait(), timeout=1)
        creator_b_task = asyncio.create_task(
            creator_b.complete(
                system_prompt="creator",
                messages=[
                    {
                        "role": "user",
                        "content_parts": [{"type": "text", "text": "B"}],
                    },
                ],
                runtime_context=_context("session-b"),
            ),
        )
        specialist_task = asyncio.create_task(
            specialist.complete(
                role=SpecialistRole.REVIEW_CONSISTENCY,
                messages=[
                    {
                        "role": "user",
                        "content_parts": [{"type": "text", "text": "review"}],
                        "metadata": {},
                    },
                ],
                tools=(),
            ),
        )
        await asyncio.sleep(0.03)
        assert probe.entered == ["creator-a"]
        assert probe.active == probe.max_active == 1

        probe.release.set()
        await asyncio.gather(creator_a_task, creator_b_task, specialist_task)
        return probe

    try:
        probe = asyncio.run(scenario())
    finally:
        model_concurrency._limiters.clear()
    assert sorted(probe.entered) == ["creator-a", "creator-b", "specialist"]
    assert probe.max_active == 1
