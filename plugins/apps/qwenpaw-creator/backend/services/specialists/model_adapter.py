# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-branches,too-many-statements
"""AgentScope 2.0.2 direct multimodal model adapter for Specialist turns."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import mimetypes
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agentscope.credential import DashScopeCredential
from agentscope.message import (
    AssistantMsg,
    Base64Source,
    DataBlock,
    Msg,
    SystemMsg,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
    ToolResultState,
    URLSource,
    UserMsg,
)
from agentscope.model import DashScopeChatModel

from domain.enums import SpecialistRole
from domain.errors import ValidationError
from models import config as model_config
from models.concurrency import model_slot
from models.dashscope_multimodal import (
    DashScopeNativeDataBlock,
    DashScopeNativeFormatter,
)


class SpecialistModelProtocolError(ValueError):
    pass


_TEXT_TOOL_CALL = re.compile(
    r"\A\s*(?:<tool_call>\s*)?<function=([A-Za-z_][A-Za-z0-9_.-]*)>"
    r"\s*(.*?)\s*</function>\s*(?:</tool_call>)?\s*\Z",
    re.DOTALL,
)
_TEXT_TOOL_CALL_PREFIX = re.compile(
    r"\A\s*(?:<tool_call>\s*)?<function=([A-Za-z_][A-Za-z0-9_.-]*)>"
    r"\s*(.*?)\s*</function>\s*(?:</tool_call>)?",
    re.DOTALL,
)
_TEXT_TOOL_PARAMETER = re.compile(
    r"<parameter=([A-Za-z_][A-Za-z0-9_.-]*)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)
_MACHINE_MARKUP_START = re.compile(
    r"<(?:tool_call\s*>|function=[A-Za-z_][A-Za-z0-9_.-]*>)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SpecialistModelTurn:
    text: str
    tool_call: ModelToolCall | None = None
    provider_message_id: str | None = None
    thinking: str = ""
    raw_text: str | None = None


class SpecialistModelPort(Protocol):
    provider_name: str
    model_name: str

    async def complete(
        self,
        *,
        role: SpecialistRole,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[str, str, str], Awaitable[None]]
        | None = None,
    ) -> SpecialistModelTurn:
        ...


def validate_model_tool_call(call: ModelToolCall) -> ModelToolCall:
    """Reject malformed provider actions before an action boundary is persisted.

    A provider response with an empty id or function name is not a machine-readable
    action from the current manifest.  In particular, it must never be followed by
    a durable ``role=tool`` record because such a record cannot be replayed as a
    valid provider action/result pair.
    """

    call_id = str(call.id or "").strip()
    name = str(call.name or "").strip()
    if not call_id:
        raise SpecialistModelProtocolError("tool call id 不能为空")
    if not name:
        raise SpecialistModelProtocolError("tool call name 不能为空")
    if not isinstance(call.arguments, Mapping):
        raise SpecialistModelProtocolError("tool call arguments 必须是 object")
    return ModelToolCall(id=call_id, name=name, arguments=dict(call.arguments))


def _normalize_manifest_bound_call(
    call: ModelToolCall,
    definition: Mapping[str, Any],
) -> ModelToolCall:
    """Canonicalize provider serialization without expanding its authority."""

    arguments = dict(call.arguments)
    parameters = definition.get("parameters")
    properties = (
        parameters.get("properties")
        if isinstance(parameters, Mapping)
        else None
    )
    if not isinstance(properties, Mapping):
        return call

    target_schema = properties.get("targetRef")
    if isinstance(target_schema, Mapping):
        admitted = target_schema.get("enum")
        if (
            isinstance(admitted, Sequence)
            and not isinstance(admitted, (str, bytes, bytearray))
            and len(admitted) == 1
            and isinstance(admitted[0], str)
        ):
            # The one admitted target is durable Runtime authority.  Persist
            # that exact value instead of a provider copy typo so SSE/tool
            # history and the eventual mutation agree.
            arguments["targetRef"] = admitted[0]

    nested_schema = properties.get("arguments")
    nested = arguments.get("arguments")
    if isinstance(nested_schema, Mapping) and isinstance(nested, str):
        expected_type = nested_schema.get("type")
        expects_object = expected_type == "object" or (
            isinstance(expected_type, Sequence)
            and not isinstance(expected_type, (str, bytes, bytearray))
            and "object" in expected_type
        )
        if expects_object:
            try:
                decoded = json.loads(nested)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, Mapping):
                arguments["arguments"] = dict(decoded)
    return ModelToolCall(call.id, call.name, arguments)


def _tool_call_from_text_match(
    match: re.Match[str],
    *,
    allowed_names: set[str],
) -> ModelToolCall | None:
    """Parse one already-delimited textual provider action."""

    name = match.group(1)
    if name not in allowed_names:
        return None
    body = match.group(2)
    arguments: dict[str, Any] = {}
    cursor = 0
    for parameter in _TEXT_TOOL_PARAMETER.finditer(body):
        if body[cursor : parameter.start()].strip():
            return None
        key = parameter.group(1)
        if key in arguments:
            raise SpecialistModelProtocolError(
                f"textual tool call parameter 重复：{key}",
            )
        raw_value = parameter.group(2).strip()
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        arguments[key] = value
        cursor = parameter.end()
    if body[cursor:].strip() or not arguments:
        return None
    matched_text = match.group(0)
    digest = hashlib.sha256(matched_text.encode("utf-8")).hexdigest()[:24]
    return validate_model_tool_call(
        ModelToolCall(
            id=f"text-tool-{digest}",
            name=name,
            arguments=arguments,
        ),
    )


def _textual_tool_call(
    text: str,
    *,
    allowed_names: set[str],
) -> ModelToolCall | None:
    """Recover Qwen's strict full-text XML fallback as one machine action.

    DashScope normally returns ``ToolCallBlock``.  In long multimodal turns it
    can instead place its documented-looking function syntax in a TextBlock.
    Only a full-string match for a currently offered tool is accepted; prose
    containing an example remains ordinary text and is therefore never
    executed.  The content-derived id keeps replay deterministic.
    """

    match = _TEXT_TOOL_CALL.fullmatch(text)
    if match is None:
        return None
    return _tool_call_from_text_match(match, allowed_names=allowed_names)


def _first_textual_tool_call(
    text: str,
    *,
    allowed_names: set[str],
) -> ModelToolCall | None:
    """Recover only the first action from Qwen's machine-only batch fallback.

    The provider can ignore ``parallel_tool_calls=False`` by returning one
    native ``ToolCallBlock`` and serializing additional calls into a
    ``TextBlock``, or by serializing several calls into one text response.
    Runtime still executes exactly one action boundary per turn.  When no
    native action exists, accepting only the first complete, offered call lets
    the next model turn observe its result without ever treating the remaining
    control markup as conversation text.
    """

    match = _TEXT_TOOL_CALL_PREFIX.match(text)
    if match is None:
        return None
    return _tool_call_from_text_match(match, allowed_names=allowed_names)


def _visible_text_before_machine_markup(text: str) -> str:
    """Return the prose used by the internal Specialist result protocol.

    The raw provider text is retained separately in ``raw_text`` and streamed
    without this normalization.  Only the runtime's action/result parser uses
    this view so machine markup cannot be mistaken for a terminal response.
    """

    match = _MACHINE_MARKUP_START.search(text)
    if match is None:
        return text
    prefix = text[: match.start()]
    return prefix.rstrip() if prefix.strip() else ""


def _data_block(
    url: str,
    *,
    media_type: str,
    video_options: Mapping[str, Any] | None = None,
) -> DataBlock:
    options = dict(video_options or {})
    native_options = {
        field: options.get(field, options.get(camel))
        for field, camel in (
            ("fps", "fps"),
            ("min_pixels", "minPixels"),
            ("max_pixels", "maxPixels"),
            ("total_pixels", "totalPixels"),
        )
        if options.get(field, options.get(camel)) is not None
    }
    if url.startswith("data:"):
        try:
            header, encoded = url.split(",", 1)
            declared = header[5:].split(";", 1)[0] or media_type
            if ";base64" not in header:
                raise ValueError("not base64")
            base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValidationError("非法 media data URL") from exc
        source = Base64Source(data=encoded, media_type=declared)
    else:
        source = URLSource(url=url, media_type=media_type)
    if media_type.startswith("video/"):
        return DashScopeNativeDataBlock(source=source, **native_options)
    return DataBlock(source=source)


def _media_type(url: str, payload: Mapping[str, Any], fallback: str) -> str:
    explicit = payload.get("mediaType") or payload.get("media_type")
    if explicit:
        return str(explicit)
    guessed, _ = mimetypes.guess_type(url)
    return guessed or fallback


def _content_blocks(
    parts: Sequence[Mapping[str, Any]],
    *,
    seen_media: set[tuple[str, str]] | None = None,
) -> list[TextBlock | DataBlock]:
    blocks: list[TextBlock | DataBlock] = []
    observed_media = seen_media if seen_media is not None else set()
    for part in parts:
        part_type = part.get("type")
        if part_type == "text":
            blocks.append(TextBlock(text=str(part.get("text") or "")))
            continue
        if part_type in {"image_url", "video_url"}:
            key = str(part_type)
            payload = part.get(key)
            if not isinstance(payload, Mapping) or not payload.get("url"):
                raise ValidationError(f"{key} content part 缺少 URL")
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
            media_identity = (key, version_identity or f"url:{url}")
            if media_identity in observed_media:
                continue
            observed_media.add(media_identity)
            fallback = "image/png" if part_type == "image_url" else "video/mp4"
            video_options = dict(payload) if part_type == "video_url" else None
            if video_options is not None:
                # Historical messages predate sampling metadata. A conservative
                # documented fallback keeps them replayable instead of silently
                # restoring DashScope's 2 fps default for a long public video.
                video_options.setdefault("fps", 0.1)
            blocks.append(
                _data_block(
                    url,
                    media_type=_media_type(url, payload, fallback),
                    video_options=video_options,
                ),
            )
            continue
        if part_type in {"audio", "document"}:
            attachment = part.get("attachment")
            if not isinstance(attachment, Mapping):
                raise ValidationError(
                    f"{part_type} content part 缺少 attachment",
                )
            # Documents unsupported as native data by the selected model must
            # arrive with a canonical extraction and explicit provenance.
            canonical_text = attachment.get("canonicalText") or attachment.get(
                "text",
            )
            if part_type == "document" and canonical_text is not None:
                provenance = (
                    attachment.get("versionId")
                    or attachment.get("url")
                    or "document"
                )
                blocks.append(
                    TextBlock(
                        text=f"[规范文档提取物 provenance={provenance}]\n{canonical_text}",
                    ),
                )
                continue
            if part_type == "document":
                raise ValidationError(
                    "当前 Specialist 模型只接受带 provenance 的规范文档提取物",
                )
            url = str(attachment.get("url") or "")
            if not url:
                raise ValidationError(f"{part_type} attachment 缺少 URL/规范提取物")
            fallback = (
                "audio/wav" if part_type == "audio" else "application/pdf"
            )
            blocks.append(
                _data_block(
                    url,
                    media_type=_media_type(url, attachment, fallback),
                ),
            )
            continue
        raise ValidationError(f"未知 Specialist content part: {part_type!r}")
    return blocks


def records_to_agentscope_messages(
    records: Sequence[Mapping[str, Any]],
) -> list[Msg]:
    """Rehydrate persisted native parts and action boundaries without flattening."""

    messages: list[Msg] = []
    seen_media: set[tuple[str, str]] = set()
    for record in records:
        role = str(record.get("role") or "")
        parts = record.get("content_parts") or []
        if not isinstance(parts, Sequence):
            raise ValidationError("Specialist message content_parts 损坏")
        normalized_parts = [
            dict(item) for item in parts if isinstance(item, Mapping)
        ]
        metadata = dict(record.get("metadata") or {})
        if role == "system":
            text = "\n".join(
                str(item.get("text") or "") for item in normalized_parts
            )
            messages.append(SystemMsg("specialist_context", text))
        elif role == "user":
            messages.append(
                UserMsg(
                    "creator_runtime",
                    _content_blocks(normalized_parts, seen_media=seen_media),
                ),
            )
        elif role == "assistant":
            blocks: list[Any] = _content_blocks(
                normalized_parts,
                seen_media=seen_media,
            )
            tool_call = metadata.get("toolCall")
            if isinstance(tool_call, Mapping):
                arguments = tool_call.get("arguments")
                if not isinstance(arguments, Mapping):
                    raise ValidationError("assistant tool call arguments 损坏")
                try:
                    call = validate_model_tool_call(
                        ModelToolCall(
                            id=str(tool_call.get("id") or ""),
                            name=str(tool_call.get("name") or ""),
                            arguments=dict(arguments),
                        ),
                    )
                except SpecialistModelProtocolError as exc:
                    raise ValidationError(
                        f"assistant action boundary metadata 损坏：{exc}",
                    ) from exc
                blocks.append(
                    ToolCallBlock(
                        id=call.id,
                        name=call.name,
                        input=json.dumps(
                            dict(call.arguments),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            messages.append(AssistantMsg("specialist", blocks))
        elif role == "tool":
            call_id = metadata.get("toolCallId")
            tool_name = metadata.get("toolName")
            if not call_id or not tool_name:
                raise ValidationError(
                    "tool message 缺少 action boundary metadata",
                )
            output = "\n".join(
                str(item.get("text") or "") for item in normalized_parts
            )
            messages.append(
                AssistantMsg(
                    "specialist_runtime",
                    [
                        ToolResultBlock(
                            id=str(call_id),
                            name=str(tool_name),
                            output=output,
                            state=ToolResultState.SUCCESS,
                        ),
                    ],
                ),
            )
        else:
            raise ValidationError(f"非法 Specialist message role: {role!r}")
    return messages


class AgentScopeSpecialistModel:
    """One direct AgentScope chat-model call; no flat transcript Agent wrapper."""

    provider_name = "dashscope"

    def __init__(self, model: DashScopeChatModel | None = None) -> None:
        self.model_name = model_config.get_vlm_model_name() or "qwen3.7-plus"
        self._injected = model is not None
        self._configuration: tuple[str, str, str, int] | None = None
        if model is not None:
            self.model_name = str(getattr(model, "model", self.model_name))
        self.model = model

    def _configured_model(self) -> DashScopeChatModel:
        if self._injected:
            assert self.model is not None
            return self.model
        api_key = model_config.get_vlm_api_key()
        base_url = model_config.get_vlm_base_url()
        model_name = model_config.get_vlm_model_name() or "qwen3.7-plus"
        timeout_seconds = model_config.get_vlm_timeout_seconds()
        if not api_key:
            raise ValidationError("Specialist model API key 未配置")
        configuration = (api_key, base_url, model_name, timeout_seconds)
        if self.model is None or self._configuration != configuration:
            self.model = DashScopeChatModel(
                credential=DashScopeCredential(
                    api_key=api_key,
                    base_url=base_url,
                ),
                model=model_name,
                parameters=DashScopeChatModel.Parameters(
                    # Qwen3.7 separates provider reasoning into ThinkingBlock.
                    # The adapter streams that channel independently while the
                    # terminal protocol continues to parse TextBlock only.
                    thinking_enable=True,
                    parallel_tool_calls=False,
                ),
                stream=True,
                formatter=DashScopeNativeFormatter(),
                # DashScope's model-bound temporary ``oss://`` URLs require
                # this documented header. It is harmless for ordinary
                # HTTP(S)/data content parts and keeps one reusable client.
                client_kwargs={
                    # AgentScope delegates to the OpenAI-compatible client.
                    # Pin the call deadline to Creator's configured VLM
                    # boundary instead of inheriting the SDK's much longer
                    # default, so the durable outer retry can run promptly
                    # after the SDK has exhausted its own transport retries.
                    "timeout": timeout_seconds,
                    "default_headers": {
                        "X-DashScope-OssResourceResolve": "enable",
                    },
                },
            )
            self._configuration = configuration
            self.model_name = model_name
        return self.model

    async def complete(
        self,
        *,
        role: SpecialistRole,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[str, str, str], Awaitable[None]]
        | None = None,
    ) -> SpecialistModelTurn:
        del role  # role behavior is already frozen in the persisted system prompt
        native_messages = records_to_agentscope_messages(messages)
        # Creator and Specialist both use the configured qwen3.7 text/chat
        # provider, including native multimodal parts.  They therefore share
        # one global TEXT_CONCURRENCY budget instead of oversubscribing it via
        # separate process-local semaphore names.
        async with model_slot("text"):
            response = await self._configured_model()(
                native_messages,
                tools=[dict(item) for item in tools] or None,
            )
            streamed_text = False
            streamed_thinking = False
            streamed_tool_call_ids: set[str] = set()
            if inspect.isasyncgen(response):
                final = None
                async for item in response:
                    if not item.is_last:
                        for block in item.content:
                            if isinstance(block, TextBlock) and block.text:
                                if on_text_delta is not None:
                                    await on_text_delta(block.text)
                                    streamed_text = True
                            elif (
                                isinstance(block, ThinkingBlock)
                                and block.thinking
                            ):
                                if on_thinking_delta is not None:
                                    await on_thinking_delta(block.thinking)
                                    streamed_thinking = True
                            elif (
                                isinstance(block, ToolCallBlock)
                                and block.id
                                and block.name
                                and on_tool_call_delta is not None
                            ):
                                await on_tool_call_delta(
                                    block.id,
                                    block.name,
                                    block.input,
                                )
                                streamed_tool_call_ids.add(block.id)
                    if item.is_last:
                        final = item
                if final is None:
                    raise SpecialistModelProtocolError(
                        "AgentScope stream 缺少 final response",
                    )
                response = final

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        calls: list[ModelToolCall] = []
        offered_functions = {
            str((item.get("function") or {}).get("name") or ""): dict(
                item["function"],
            )
            for item in tools
            if isinstance(item, Mapping)
            and isinstance(item.get("function"), Mapping)
        }
        offered_functions.pop("", None)
        allowed_names = set(offered_functions)
        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolCallBlock):
                try:
                    arguments = json.loads(block.input or "{}")
                except json.JSONDecodeError as exc:
                    raise SpecialistModelProtocolError(
                        "tool call arguments 不是合法 JSON",
                    ) from exc
                if not isinstance(arguments, dict):
                    raise SpecialistModelProtocolError(
                        "tool call arguments 必须是 object",
                    )
                validated_call = validate_model_tool_call(
                    ModelToolCall(block.id, block.name, arguments),
                )
                if validated_call.name not in allowed_names:
                    raise SpecialistModelProtocolError(
                        "provider 返回了本轮未提供的 control action: "
                        f"{validated_call.name}",
                    )
                calls.append(
                    _normalize_manifest_bound_call(
                        validated_call,
                        offered_functions[validated_call.name],
                    ),
                )
            elif isinstance(block, ThinkingBlock):
                thinking_parts.append(block.thinking)
        if len(calls) > 1:
            raise SpecialistModelProtocolError(
                "Specialist 每轮只允许一个 control action",
            )
        raw_visible_text = "".join(text_parts)
        thinking = "".join(thinking_parts)
        visible_text = _visible_text_before_machine_markup(raw_visible_text)
        if not calls:
            fallback_call = _textual_tool_call(
                raw_visible_text,
                allowed_names=allowed_names,
            )
            if fallback_call is None:
                fallback_call = _first_textual_tool_call(
                    raw_visible_text,
                    allowed_names=allowed_names,
                )
            if fallback_call is not None:
                calls.append(fallback_call)
        if (
            on_text_delta is not None
            and raw_visible_text
            and not streamed_text
        ):
            await on_text_delta(raw_visible_text)
        if (
            on_thinking_delta is not None
            and thinking
            and not streamed_thinking
        ):
            await on_thinking_delta(thinking)
        if on_tool_call_delta is not None:
            for block in response.content:
                if (
                    isinstance(block, ToolCallBlock)
                    and block.id
                    and block.name
                    and block.id not in streamed_tool_call_ids
                ):
                    await on_tool_call_delta(block.id, block.name, block.input)
        return SpecialistModelTurn(
            text=visible_text,
            tool_call=calls[0] if calls else None,
            provider_message_id=getattr(response, "id", None),
            thinking=thinking,
            raw_text=raw_visible_text,
        )


__all__ = [
    "AgentScopeSpecialistModel",
    "ModelToolCall",
    "SpecialistModelPort",
    "SpecialistModelProtocolError",
    "SpecialistModelTurn",
    "records_to_agentscope_messages",
    "validate_model_tool_call",
]
