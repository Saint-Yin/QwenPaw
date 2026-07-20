# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,redefined-outer-name,reimported
# pylint: disable=too-many-branches,too-many-nested-blocks,too-many-statements
"""Direct AgentScope 2.0 adapter for the persistent Creator conversation.

Every Creator control action is offered and returned through AgentScope's
native ``ToolCallBlock``/``ToolResultBlock`` boundary. Creator still receives
only lightweight immutable attachment identity; native media remains scoped to
the targeted Source Specialist.
"""

from __future__ import annotations

import inspect
import json
import mimetypes
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from agentscope.credential import DashScopeCredential
from agentscope.message import (
    AssistantMsg,
    Msg,
    SystemMsg,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
    ToolResultState,
    UserMsg,
)
from agentscope.model import DashScopeChatModel

from domain.errors import ValidationError
from models import config as model_config
from models.concurrency import model_slot
from models.dashscope_multimodal import (
    DashScopeNativeFormatter,
)


class CreatorModelProtocolError(ValueError):
    """The provider returned a shape outside the frozen Creator protocol."""


@dataclass(frozen=True, slots=True)
class CreatorRuntimeContext:
    project_id: str
    creator_session_id: str
    goal_id: str
    goal_intent: str
    success_criteria: tuple[Any, ...]
    goal_status: str
    remaining_work_refs: tuple[str, ...]
    transaction_id: str | None
    transaction_status: str | None
    working_head: str | None
    creator_plan: Mapping[str, Any] | None = None
    creator_plan_invalidated_by_message_seq: int | None = None
    initial_attached_sources: tuple[Mapping[str, str], ...] = ()
    active_waitable_runs: tuple[Mapping[str, Any], ...] = ()
    project_scenario: str = "general"
    project_content_type: str | None = None

    def as_text(self) -> str:
        import json

        return "[CREATOR_CONTEXT]\n" + json.dumps(
            {
                "projectId": self.project_id,
                "projectScenario": self.project_scenario,
                "projectContentType": self.project_content_type,
                "creatorSessionId": self.creator_session_id,
                "goal": {
                    "id": self.goal_id,
                    "intent": self.goal_intent,
                    "successCriteria": list(self.success_criteria),
                    "status": self.goal_status,
                    "remainingWorkRefs": list(self.remaining_work_refs),
                },
                "transaction": (
                    {
                        "id": self.transaction_id,
                        "status": self.transaction_status,
                        "workingHead": self.working_head,
                    }
                    if self.transaction_id
                    else None
                ),
                "creatorPlan": dict(self.creator_plan)
                if self.creator_plan
                else None,
                "creatorPlanInvalidatedByMessageSeq": (
                    self.creator_plan_invalidated_by_message_seq
                ),
                "initialAttachedSources": [
                    dict(source) for source in self.initial_attached_sources
                ],
                "activeWaitableRuns": [
                    {
                        **dict(run),
                        "status": (
                            "WAITING_RESULT"
                            if str(run.get("status") or "")
                            == "WAITING_RUNTIME"
                            else run.get("status")
                        ),
                    }
                    for run in self.active_waitable_runs
                ],
                "validTargetRefFormats": [
                    f"project:{self.project_id}",
                    "project:header",
                    "project:plan",
                    "project:assets",
                    "section:<sectionId>",
                    "unit:<unitId>",
                    "shot:<shotId>",
                    "asset:<logicalAssetId>",
                    "artifact:<slotId>",
                    "analysis:<assetId>",
                    "post:<sectionId|final>",
                ],
                "targetRefIdentityRule": (
                    "For ordered directory 001000--intro--mixed-video, the stable id is the "
                    "middle segment intro, so use section:intro. Apply the same rule to "
                    "unit and shot refs; never put the full directory segment in a ref."
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class CreatorToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CreatorModelTurn:
    text: str
    tool_call: CreatorToolCall | None = None
    thinking: str = ""
    provider_message_id: str | None = None
    provider_conversation_handle: str | None = None


class CreatorModelPort(Protocol):
    provider_name: str
    model_name: str

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Mapping[str, Any]],
        runtime_context: CreatorRuntimeContext,
        tools: Sequence[Mapping[str, Any]] = (),
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[str, str, str], Awaitable[None]]
        | None = None,
    ) -> CreatorModelTurn:
        ...


def _media_type(url: str, payload: Mapping[str, Any], fallback: str) -> str:
    explicit = payload.get("mediaType") or payload.get("media_type")
    if explicit:
        return str(explicit)
    guessed, _encoding = mimetypes.guess_type(url)
    return guessed or fallback


def _content_blocks(
    parts: Sequence[Mapping[str, Any]],
    *,
    seen_media: set[tuple[str, str]] | None = None,
) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    observed_media = seen_media if seen_media is not None else set()
    for part in parts:
        part_type = part.get("type")
        if part_type == "text":
            blocks.append(TextBlock(text=str(part.get("text") or "")))
            continue
        if part_type in {"image_url", "video_url"}:
            payload = part.get(str(part_type))
            if not isinstance(payload, Mapping) or not payload.get("url"):
                raise ValidationError(f"{part_type} content part 缺少 URL")
            url = str(payload["url"])
            attachment = part.get("attachment")
            attachment_ref = (
                str(attachment.get("assetVersionRef") or "")
                if isinstance(attachment, Mapping)
                else ""
            )
            if attachment_ref.startswith("asset-version:"):
                attachment_ref = attachment_ref[len("asset-version:") :]
            version_identity = str(payload.get("versionId") or attachment_ref)
            media_identity = (str(part_type), version_identity or f"url:{url}")
            if media_identity in observed_media:
                continue
            observed_media.add(media_identity)
            blocks.append(
                TextBlock(
                    text=(
                        "[Creator attachment manifest: native media withheld; "
                        "delegate source_intelligence_agent for observation] "
                        f"type={part_type} assetVersionId="
                        f"{version_identity or 'unresolved'} mediaType="
                        f"{_media_type(url, payload, 'image/png' if part_type == 'image_url' else 'video/mp4')}"
                    ),
                ),
            )
            continue
        if part_type in {"audio", "document"}:
            attachment = part.get("attachment")
            if not isinstance(attachment, Mapping):
                raise ValidationError(
                    f"{part_type} content part 缺少 attachment",
                )
            canonical_text = attachment.get("canonicalText") or attachment.get(
                "text",
            )
            if part_type == "document" and canonical_text is not None:
                provenance = (
                    attachment.get("assetVersionRef")
                    or attachment.get("versionId")
                    or attachment.get("url")
                    or "document"
                )
                blocks.append(
                    TextBlock(
                        text=f"[规范文档提取物 provenance={provenance}]\n{canonical_text}",
                    ),
                )
                continue
            url = str(attachment.get("url") or "")
            version_identity = str(
                attachment.get("versionId")
                or attachment.get("assetVersionRef")
                or "unresolved",
            )
            fallback = (
                "audio/wav" if part_type == "audio" else "application/pdf"
            )
            blocks.append(
                TextBlock(
                    text=(
                        "[Creator attachment manifest: native media withheld; "
                        "delegate a scoped Specialist for observation] "
                        f"type={part_type} assetVersionId={version_identity} "
                        f"mediaType={_media_type(url, attachment, fallback)}"
                    ),
                ),
            )
            continue
        raise ValidationError(f"未知 Creator content part: {part_type!r}")
    return blocks


def records_to_agentscope_messages(
    records: Sequence[Mapping[str, Any]],
    *,
    system_prompt: str,
    runtime_context: CreatorRuntimeContext,
) -> list[Msg]:
    """Rehydrate the authoritative transcript without flattening or summarizing it."""

    messages: list[Msg] = [
        SystemMsg("creator_agent", system_prompt),
        SystemMsg("creator_context", runtime_context.as_text()),
    ]
    seen_media: set[tuple[str, str]] = set()
    for record in records:
        role = str(record.get("role") or "")
        raw_parts = record.get("content_parts") or []
        if not isinstance(raw_parts, Sequence):
            raise ValidationError("Creator message content_parts 损坏")
        parts = [dict(item) for item in raw_parts if isinstance(item, Mapping)]
        if role == "system":
            text = "\n".join(str(item.get("text") or "") for item in parts)
            messages.append(SystemMsg("creator_context", text))
        elif role == "user":
            messages.append(
                UserMsg("user", _content_blocks(parts, seen_media=seen_media)),
            )
        elif role == "assistant":
            blocks: list[Any] = _content_blocks(parts, seen_media=seen_media)
            tool_call = dict(record.get("metadata") or {}).get("toolCall")
            if isinstance(tool_call, Mapping):
                call_id = str(tool_call.get("id") or "").strip()
                name = str(tool_call.get("name") or "").strip()
                arguments = tool_call.get("arguments")
                if (
                    not call_id
                    or not name
                    or not isinstance(arguments, Mapping)
                ):
                    raise ValidationError(
                        "Creator assistant toolCall metadata 损坏",
                    )
                blocks.append(
                    ToolCallBlock(
                        id=call_id,
                        name=name,
                        input=json.dumps(
                            dict(arguments),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            messages.append(AssistantMsg("creator_agent", blocks))
        elif role == "tool":
            metadata = dict(record.get("metadata") or {})
            call_id = str(metadata.get("toolCallId") or "").strip()
            name = str(metadata.get("toolName") or "").strip()
            if not call_id or not name:
                raise ValidationError("Creator tool result metadata 损坏")
            output = "\n".join(
                str(item.get("text") or "")
                for item in parts
                if item.get("type") == "text"
            )
            messages.append(
                AssistantMsg(
                    "creator_runtime",
                    [
                        ToolResultBlock(
                            id=call_id,
                            name=name,
                            output=output,
                            state=(
                                ToolResultState.ERROR
                                if metadata.get("failed") is True
                                else ToolResultState.SUCCESS
                            ),
                        ),
                    ],
                ),
            )
        else:
            raise ValidationError(f"非法 Creator message role: {role!r}")
    return messages


class AgentScopeCreatorModel:
    """One direct qwen3.7-plus AgentScope call over the complete transcript."""

    provider_name = "dashscope"

    def __init__(self, model: DashScopeChatModel | None = None) -> None:
        self.model_name = model_config.get_text_model_name() or "qwen3.7-plus"
        self._injected = model is not None
        self._configuration: tuple[str, str, str] | None = None
        if model is not None:
            self.model_name = str(getattr(model, "model", self.model_name))
        self.model = model

    def _configured_model(self) -> DashScopeChatModel:
        if self._injected:
            assert self.model is not None
            return self.model
        api_key = model_config.get_text_api_key()
        base_url = model_config.get_text_base_url()
        model_name = model_config.get_text_model_name() or "qwen3.7-plus"
        if not api_key:
            raise ValidationError("Creator text model API key 未配置")
        configuration = (api_key, base_url, model_name)
        if self.model is None or self._configuration != configuration:
            self.model = DashScopeChatModel(
                credential=DashScopeCredential(
                    api_key=api_key,
                    base_url=base_url,
                ),
                model=model_name,
                parameters=DashScopeChatModel.Parameters(
                    max_tokens=4096,
                    thinking_enable=True,
                    parallel_tool_calls=False,
                ),
                stream=True,
                formatter=DashScopeNativeFormatter(),
            )
            self._configuration = configuration
            self.model_name = model_name
        return self.model

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Mapping[str, Any]],
        runtime_context: CreatorRuntimeContext,
        tools: Sequence[Mapping[str, Any]] = (),
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[str, str, str], Awaitable[None]]
        | None = None,
    ) -> CreatorModelTurn:
        allowed_names = {
            str((item.get("function") or {}).get("name") or "")
            for item in tools
            if isinstance(item, Mapping)
            and isinstance(item.get("function"), Mapping)
        }
        allowed_names.discard("")
        native = records_to_agentscope_messages(
            messages,
            system_prompt=system_prompt,
            runtime_context=runtime_context,
        )
        async with model_slot("text"):
            response = await self._configured_model()(
                native,
                tools=[dict(item) for item in tools] or None,
            )
            streamed_text = False
            streamed_thinking = False
            streamed_tool_call_ids: set[str] = set()
            streamed_tool_names: dict[str, str] = {}
            pending_tool_inputs: dict[str, list[str]] = {}
            if inspect.isasyncgen(response):
                final = None
                async for item in response:
                    if item.is_last:
                        final = item
                        continue
                    for block in item.content:
                        if isinstance(block, TextBlock) and block.text:
                            if on_text_delta is not None:
                                await on_text_delta(block.text)
                                streamed_text = True
                        elif (
                            isinstance(block, ThinkingBlock) and block.thinking
                        ):
                            if on_thinking_delta is not None:
                                await on_thinking_delta(block.thinking)
                                streamed_thinking = True
                        elif isinstance(block, ToolCallBlock) and block.id:
                            raw_name = str(block.name or "").strip()
                            if raw_name in allowed_names:
                                streamed_tool_names[block.id] = raw_name
                            effective_name = streamed_tool_names.get(
                                block.id,
                                raw_name,
                            )
                            if block.input:
                                if effective_name in allowed_names:
                                    deltas = [
                                        *pending_tool_inputs.pop(block.id, []),
                                        block.input,
                                    ]
                                    if on_tool_call_delta is not None:
                                        for delta in deltas:
                                            await on_tool_call_delta(
                                                block.id,
                                                effective_name,
                                                delta,
                                            )
                                        streamed_tool_call_ids.add(block.id)
                                else:
                                    pending_tool_inputs.setdefault(
                                        block.id,
                                        [],
                                    ).append(block.input)
                            elif (
                                effective_name in allowed_names
                                and pending_tool_inputs.get(block.id)
                            ):
                                deltas = pending_tool_inputs.pop(block.id)
                                if on_tool_call_delta is not None:
                                    for delta in deltas:
                                        await on_tool_call_delta(
                                            block.id,
                                            effective_name,
                                            delta,
                                        )
                                    streamed_tool_call_ids.add(block.id)
                if final is None:
                    raise CreatorModelProtocolError(
                        "AgentScope stream 缺少 final response",
                    )
                response = final

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        calls: list[CreatorToolCall] = []
        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ThinkingBlock):
                thinking_parts.append(block.thinking)
            elif isinstance(block, ToolCallBlock):
                call_id = str(block.id or "").strip()
                raw_name = str(block.name or "").strip()
                name = (
                    raw_name
                    if raw_name in allowed_names
                    else streamed_tool_names.get(call_id, raw_name)
                )
                if not call_id or not name:
                    raise CreatorModelProtocolError(
                        "Creator tool call id/name 不能为空",
                    )
                if name not in allowed_names:
                    raise CreatorModelProtocolError(
                        f"Creator 返回了本轮未提供的 tool call: {name}",
                    )
                try:
                    arguments = json.loads(block.input or "{}")
                except json.JSONDecodeError as exc:
                    raise CreatorModelProtocolError(
                        "Creator tool call arguments 不是合法 JSON",
                    ) from exc
                if not isinstance(arguments, dict):
                    raise CreatorModelProtocolError(
                        "Creator tool call arguments 必须是 object",
                    )
                calls.append(CreatorToolCall(call_id, name, arguments))
        text = "".join(text_parts)
        thinking = "".join(thinking_parts)
        if tools and len(calls) != 1:
            raise CreatorModelProtocolError("Creator 每轮必须且只能返回一个 tool call")
        if not tools and calls:
            raise CreatorModelProtocolError("无工具模型调用不能返回 tool call")
        if not tools and not text.strip():
            raise CreatorModelProtocolError("无工具模型调用返回空文本")
        # Injected providers can legitimately return one complete response.
        # Preserve the same observable callback contract for those calls.
        if on_text_delta is not None and text and not streamed_text:
            await on_text_delta(text)
        if (
            on_thinking_delta is not None
            and thinking
            and not streamed_thinking
        ):
            await on_thinking_delta(thinking)
        call = calls[0] if calls else None
        if (
            call is not None
            and on_tool_call_delta is not None
            and call.id not in streamed_tool_call_ids
        ):
            await on_tool_call_delta(
                call.id,
                call.name,
                json.dumps(
                    dict(call.arguments),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return CreatorModelTurn(
            text=text,
            tool_call=call,
            thinking=thinking,
            provider_message_id=getattr(response, "id", None),
        )


__all__ = [
    "AgentScopeCreatorModel",
    "CreatorModelPort",
    "CreatorModelProtocolError",
    "CreatorModelTurn",
    "CreatorRuntimeContext",
    "CreatorToolCall",
    "records_to_agentscope_messages",
]
