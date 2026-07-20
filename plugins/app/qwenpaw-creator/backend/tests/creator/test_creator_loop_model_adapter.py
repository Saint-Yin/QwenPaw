from __future__ import annotations

import asyncio
from importlib.metadata import version

import pytest
from agentscope.message import (
    DataBlock,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from agentscope.model._model_response import ChatResponse

from services.creator.model_adapter import (
    AgentScopeCreatorModel,
    CreatorRuntimeContext,
    records_to_agentscope_messages,
)
from services.creator.tool_manifest import creator_tool_manifest

pytestmark = pytest.mark.unit


def _context() -> CreatorRuntimeContext:
    return CreatorRuntimeContext(
        project_id="project-1",
        creator_session_id="session-1",
        goal_id="goal-1",
        goal_intent="制作混合视频",
        success_criteria=("R2V 与 Edit 都完成",),
        goal_status="ACTIVE",
        remaining_work_refs=("unit:r2v-1",),
        transaction_id="transaction-1",
        transaction_status="ACTIVE",
        working_head="a" * 64,
        initial_attached_sources=(
            {
                "targetRef": "asset:source-video",
                "assetVersionRef": "asset-version:video-v1",
                "selectedVersionRefPath": (
                    "sources/source-video--clip/selected-version.ref"
                ),
            },
        ),
        active_waitable_runs=(
            {
                "id": "run-0123456789abcdef0123456789abcdef01234567",
                "role": "source_intelligence_agent",
                "status": "QUEUED",
                "targetRefs": ["asset:source-video"],
            },
        ),
        project_scenario="video_edit",
        project_content_type="highlight_reel",
    )


def test_agentscope_matches_qwenpaw_and_creator_receives_only_attachment_manifest() -> (
    None
):
    assert version("agentscope") == "2.0.4"
    messages = records_to_agentscope_messages(
        [
            {
                "role": "user",
                "content_parts": [
                    {"type": "text", "text": "看这张参考图"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/reference.png"},
                    },
                ],
            },
            {
                "role": "assistant",
                "content_parts": [
                    {"type": "text", "text": "已看到。"}
                ],
                "metadata": {
                    "toolCall": {
                        "id": "call-final",
                        "name": "final",
                        "arguments": {"message": "ok", "awaitUserInput": False},
                    }
                },
            },
            {
                "role": "tool",
                "content_parts": [{"type": "text", "text": '{"status":"IDLE"}'}],
                "metadata": {
                    "toolCallId": "call-final",
                    "toolName": "final",
                },
            },
        ],
        system_prompt="fixed creator prompt",
        runtime_context=_context(),
    )
    assert [item.role for item in messages] == ["system", "system", "user", "assistant", "assistant"]
    assert isinstance(messages[2].content[0], TextBlock)
    assert isinstance(messages[2].content[1], TextBlock)
    assert "native media withheld" in messages[2].content[1].text
    assert "remainingWorkRefs" in messages[1].content[0].text
    assert '"creatorPlan":null' in messages[1].content[0].text
    assert '"projectScenario":"video_edit"' in messages[1].content[0].text
    assert '"projectContentType":"highlight_reel"' in messages[1].content[0].text
    assert (
        '"activeWaitableRuns":[{"id":"run-0123456789abcdef0123456789abcdef01234567",'
        '"role":"source_intelligence_agent","status":"QUEUED",'
        '"targetRefs":["asset:source-video"]}]'
    ) in messages[1].content[0].text
    assert (
        '"initialAttachedSources":[{"assetVersionRef":"asset-version:video-v1",'
        '"selectedVersionRefPath":"sources/source-video--clip/selected-version.ref",'
        '"targetRef":"asset:source-video"}]'
    ) in messages[1].content[0].text
    # No flattened transcript is synthesized into one user string.
    assert isinstance(messages[3].content[-1], ToolCallBlock)
    assert isinstance(messages[4].content[0], ToolResultBlock)
    assert len(messages) == 5


def test_creator_replay_never_attaches_native_video_blocks() -> None:
    messages = records_to_agentscope_messages(
        [
            {
                "role": "user",
                "content_parts": [
                    {
                        "type": "video_url",
                        "video_url": {"url": "https://example.com/long.mp4"},
                        "attachment": {
                            "assetVersionRef": "asset-version:video-v1",
                            "mediaType": "video/mp4",
                        },
                    }
                ],
            },
            {
                "role": "user",
                "content_parts": [
                    {"type": "text", "text": "context refreshed"},
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": "https://example.com/long.mp4",
                            "versionId": "video-v1",
                        },
                    },
                ],
            },
        ],
        system_prompt="fixed creator prompt",
        runtime_context=_context(),
    )
    data_blocks = [
        block
        for message in messages
        for block in message.content
        if isinstance(block, DataBlock)
    ]
    assert data_blocks == []
    assert [type(block).__name__ for block in messages[-1].content] == ["TextBlock"]


def test_creator_replay_never_attaches_audio_or_document_data_blocks() -> None:
    messages = records_to_agentscope_messages(
        [
            {
                "role": "user",
                "content_parts": [
                    {
                        "type": "audio",
                        "attachment": {
                            "url": "https://example.com/voice.wav",
                            "assetVersionRef": "asset-version:audio-v1",
                            "mediaType": "audio/wav",
                        },
                    },
                    {
                        "type": "document",
                        "attachment": {
                            "url": "https://example.com/brief.pdf",
                            "assetVersionRef": "asset-version:doc-v1",
                            "mediaType": "application/pdf",
                        },
                    },
                    {
                        "type": "document",
                        "attachment": {
                            "assetVersionRef": "asset-version:doc-v2",
                            "canonicalText": "已经过 Runtime 规范提取的文本",
                        },
                    },
                ],
            }
        ],
        system_prompt="fixed creator prompt",
        runtime_context=_context(),
    )

    blocks = messages[-1].content
    assert all(isinstance(block, TextBlock) for block in blocks)
    assert not any(isinstance(block, DataBlock) for block in blocks)
    assert "native media withheld" in blocks[0].text
    assert "audio-v1" in blocks[0].text
    assert "doc-v1" in blocks[1].text
    assert "规范文档提取物" in blocks[2].text


def test_direct_creator_adapter_uses_native_agentscope_tool_call() -> None:
    class FakeDashScopeModel:
        model = "qwen3.7-plus"

        def __init__(self) -> None:
            self.messages = None
            self.tools = "unset"

        async def __call__(self, messages, *, tools=None):
            self.messages = messages
            self.tools = tools
            return ChatResponse(
                id="response-1",
                content=[
                    TextBlock(text="先制定计划。"),
                    ToolCallBlock(
                        id="call-plan",
                        name="plan",
                        input='{"summary":"计划","steps":["执行"],"scope":["project:plan"]}',
                    )
                ],
                is_last=True,
            )

    async def scenario():
        fake = FakeDashScopeModel()
        adapter = AgentScopeCreatorModel(fake)  # type: ignore[arg-type]
        turn = await adapter.complete(
            system_prompt="fixed creator prompt",
            messages=[
                {
                    "role": "user",
                    "content_parts": [{"type": "text", "text": "开始"}],
                }
            ],
            runtime_context=_context(),
            tools=creator_tool_manifest(),
        )
        return fake, turn

    fake, turn = asyncio.run(scenario())
    assert isinstance(fake.tools, list)
    assert {item["function"]["name"] for item in fake.tools} >= {"plan", "final", "delegate_to_agent"}
    assert fake.messages is not None
    assert turn.provider_message_id == "response-1"
    assert turn.text == "先制定计划。"
    assert turn.tool_call is not None
    assert turn.tool_call.name == "plan"
    assert turn.tool_call.arguments["summary"] == "计划"


def test_direct_creator_adapter_does_not_emit_empty_text_delta_for_tool_only_turn() -> None:
    class ToolOnlyDashScopeModel:
        model = "qwen3.7-plus"

        async def __call__(self, messages, *, tools=None):
            del messages
            assert tools
            return ChatResponse(
                id="response-tool-only",
                content=[
                    ToolCallBlock(
                        id="call-final",
                        name="final",
                        input='{"message":"完成","awaitUserInput":false}',
                    )
                ],
                is_last=True,
            )

    async def scenario():
        text_deltas: list[str] = []
        tool_deltas: list[tuple[str, str, str]] = []

        async def collect_text(delta: str) -> None:
            text_deltas.append(delta)

        async def collect_tool(call_id: str, name: str, delta: str) -> None:
            tool_deltas.append((call_id, name, delta))

        turn = await AgentScopeCreatorModel(  # type: ignore[arg-type]
            ToolOnlyDashScopeModel()
        ).complete(
            system_prompt="fixed creator prompt",
            messages=[
                {
                    "role": "user",
                    "content_parts": [{"type": "text", "text": "回答"}],
                }
            ],
            runtime_context=_context(),
            tools=creator_tool_manifest(),
            on_text_delta=collect_text,
            on_tool_call_delta=collect_tool,
        )
        return turn, text_deltas, tool_deltas

    turn, text_deltas, tool_deltas = asyncio.run(scenario())
    assert turn.text == ""
    assert turn.tool_call is not None and turn.tool_call.name == "final"
    assert text_deltas == []
    assert tool_deltas == [
        (
            "call-final",
            "final",
            '{"awaitUserInput":false,"message":"完成"}',
        )
    ]


def test_direct_creator_adapter_streams_raw_text_and_provider_thinking_deltas() -> None:
    class StreamingDashScopeModel:
        model = "qwen3.7-plus"

        async def __call__(self, messages, *, tools=None):
            del messages
            assert tools

            async def chunks():
                yield ChatResponse(
                    content=[
                        ThinkingBlock(thinking="private"),
                        TextBlock(text="正在"),
                        ToolCallBlock(id="call-plan", name="unknown", input=""),
                    ],
                    is_last=False,
                    id="response-stream",
                )
                yield ChatResponse(
                    content=[
                        TextBlock(text="处理"),
                        ToolCallBlock(id="call-plan", name="plan", input=""),
                    ],
                    is_last=False,
                    id="response-stream",
                )
                yield ChatResponse(
                    content=[
                        ToolCallBlock(
                            id="call-plan",
                            name="unknown",
                            input='{"summary":"计划",',
                        ),
                    ],
                    is_last=False,
                    id="response-stream",
                )
                yield ChatResponse(
                    content=[
                        ThinkingBlock(thinking="private complete"),
                        TextBlock(text="正在处理"),
                        ToolCallBlock(
                            id="call-plan",
                            name="unknown",
                            input='{"summary":"计划","steps":["执行"],"scope":["project:plan"]}',
                        ),
                    ],
                    is_last=True,
                    id="response-stream",
                )

            return chunks()

    async def scenario():
        deltas: list[str] = []
        thinking_deltas: list[str] = []
        tool_deltas: list[tuple[str, str, str]] = []

        async def collect(delta: str) -> None:
            deltas.append(delta)

        async def collect_thinking(delta: str) -> None:
            thinking_deltas.append(delta)

        async def collect_tool(call_id: str, name: str, delta: str) -> None:
            tool_deltas.append((call_id, name, delta))

        adapter = AgentScopeCreatorModel(StreamingDashScopeModel())  # type: ignore[arg-type]
        turn = await adapter.complete(
            system_prompt="fixed creator prompt",
            messages=[
                {
                    "role": "user",
                    "content_parts": [{"type": "text", "text": "开始"}],
                }
            ],
            runtime_context=_context(),
            tools=creator_tool_manifest(),
            on_text_delta=collect,
            on_thinking_delta=collect_thinking,
            on_tool_call_delta=collect_tool,
        )
        return turn, deltas, thinking_deltas, tool_deltas

    turn, deltas, thinking_deltas, tool_deltas = asyncio.run(scenario())
    assert turn.text == "正在处理"
    assert deltas == ["正在", "处理"]
    assert thinking_deltas == ["private"]
    assert turn.thinking == "private complete"
    assert turn.tool_call is not None
    assert turn.tool_call.id == "call-plan"
    assert tool_deltas == [("call-plan", "plan", '{"summary":"计划",')]
