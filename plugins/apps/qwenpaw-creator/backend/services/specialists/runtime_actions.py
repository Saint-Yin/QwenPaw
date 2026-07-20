# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-branches,too-many-statements
"""Implemented-only Runtime control-action registry for Specialist model turns."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol

from domain.enums import SpecialistRole, TaskKind, TaskStatus
from domain.errors import ConflictError, PermissionDeniedError, ValidationError
from domain.ids import new_id
from domain.refs import parse_target_ref, validate_workspace_ref
from services.observability import trace_event, traced_async
from services.validators.r2v import (
    ProviderCapabilitySnapshot,
    R2VExecutionRequest,
    validate_r2v_execution,
)

from .contracts import SpecialistRunInput, TargetExpectation
from .tool_manifest import provider_function


def canonical_json_hash(value: Any) -> str:
    """Hash a JSON-compatible value without importing a persistence backend."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RuntimeActionState(StrEnum):
    COMPLETED = "COMPLETED"
    WAITING_RUNTIME = "WAITING_RUNTIME"
    WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class RuntimeActionDraft:
    kind: str
    target_ref: str
    input_refs: tuple[str, ...]
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RuntimeActionContext:
    run: Mapping[str, Any]
    run_input: SpecialistRunInput
    read_set: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class RuntimeActionResult:
    state: RuntimeActionState
    output: Mapping[str, Any]
    task_id: str | None = None
    continuation_token: str | None = None
    persisted_request: Mapping[str, Any] | None = None
    read_set_remove_paths: tuple[str, ...] = ()
    read_set_updates: tuple[Mapping[str, Any], ...] = ()


class RuntimeActionHandler(Protocol):
    async def __call__(
        self,
        context: RuntimeActionContext,
        draft: RuntimeActionDraft,
    ) -> RuntimeActionResult:
        ...


@dataclass(frozen=True, slots=True)
class RuntimeActionSpec:
    kind: str
    description: str
    roles: frozenset[SpecialistRole]
    category: str
    arguments_schema: Mapping[str, Any]

    def provider_schema(self) -> dict[str, Any]:
        if self.kind == "publish_source_intelligence":
            return provider_function(
                self.kind,
                {
                    "description": self.description,
                    "parameters": dict(self.arguments_schema),
                },
            )
        properties: dict[str, Any] = {
            "targetRef": {"type": "string", "minLength": 1},
            "arguments": dict(self.arguments_schema),
        }
        required = ["targetRef", "arguments"]
        if self.category == "execution":
            properties["inputRefs"] = {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            }
            required.append("inputRefs")
        return provider_function(
            self.kind,
            {
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        )


_WRITERS = frozenset(
    {
        SpecialistRole.STORY_PLANNING,
        SpecialistRole.VISUAL_DEVELOPMENT,
        SpecialistRole.UNIT_PLANNING_ROUTING,
        SpecialistRole.R2V_GENERATION_DIRECTOR,
    },
)


def _object_schema(
    properties: Mapping[str, Any],
    required: Sequence[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


RUNTIME_ACTION_SPECS: dict[str, RuntimeActionSpec] = {
    "publish_source_intelligence": RuntimeActionSpec(
        "publish_source_intelligence",
        (
            "提交本轮附带素材的视觉理解。summary 概述整体内容；视频 segments 使用毫秒"
            "时间范围和具体 text，按镜头及语义变化形成完整、细致的视觉时间线；"
            "静态图片可仅提交 summary。"
        ),
        frozenset({SpecialistRole.SOURCE_INTELLIGENCE}),
        "mutation",
        _object_schema(
            {
                "summary": {"type": "string", "minLength": 1},
                "segments": {
                    "type": "array",
                    "items": _object_schema(
                        {
                            "startMs": {
                                "type": ["integer", "null"],
                                "minimum": 0,
                            },
                            "endMs": {
                                "type": ["integer", "null"],
                                "minimum": 1,
                            },
                            "text": {"type": "string", "minLength": 1},
                        },
                        ("startMs", "endMs", "text"),
                    ),
                },
            },
            ("summary", "segments"),
        ),
    ),
    "create_path": RuntimeActionSpec(
        "create_path",
        (
            "建立本角色拥有的一个完整 Text Workspace 文本叶子路径（含虚拟父目录）；"
            "path 必须以 .md/.txt/.vtt/.ctm 结尾；.ref 必须直接用 set_reference 写入"
            "合法 exact ref。新路径的 expectedTargetVersion 传 JSON null；成功后用 "
            "write_file(path, content) 写入或覆盖。"
        ),
        _WRITERS,
        "mutation",
        _object_schema(
            {
                "path": {"type": "string"},
                "expectedTargetVersion": {"type": ["string", "null"]},
            },
            ("path", "expectedTargetVersion"),
        ),
    ),
    "write_multi_files": RuntimeActionSpec(
        "write_multi_files",
        (
            "在一次原子 Workspace mutation 中写入多个普通文本叶子。每个 path 都必须属于"
            "本 Run 的 target scope；新文件 expectedObjectVersion 传 null，覆盖既有文件必须"
            "传读取到的 exact objectVersion。不得写 .ref；任一文件校验失败时整批不提交。"
        ),
        _WRITERS,
        "mutation",
        _object_schema(
            {
                "files": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": _object_schema(
                        {
                            "path": {"type": "string", "minLength": 1},
                            "content": {"type": "string"},
                            "expectedObjectVersion": {
                                "type": ["string", "null"],
                            },
                        },
                        ("path", "content", "expectedObjectVersion"),
                    ),
                },
            },
            ("files",),
        ),
    ),
    "move_path": RuntimeActionSpec(
        "move_path",
        (
            "移动本角色拥有的目录/文件；先用 glob/read 读取完整 source。文件的 "
            "expectedTargetVersion 传其 objectVersion；目录可传完整 subtree hash 或其中"
            "一个已读取叶子的 objectVersion，Runtime 仍会对全部 source readSet 做 CAS，"
            "并原子写 Working Tree/Journal/Event。"
        ),
        frozenset(
            {
                SpecialistRole.UNIT_PLANNING_ROUTING,
                SpecialistRole.STORY_PLANNING,
            },
        ),
        "mutation",
        _object_schema(
            {
                "sourcePath": {"type": "string"},
                "destinationPath": {"type": "string"},
                "expectedTargetVersion": {"type": "string"},
            },
            ("sourcePath", "destinationPath", "expectedTargetVersion"),
        ),
    ),
    "delete_path": RuntimeActionSpec(
        "delete_path",
        (
            "删除本角色拥有的路径；先用 glob/read 读取完整 target。文件的 "
            "expectedTargetVersion 传其 objectVersion；目录可传完整 subtree hash 或其中"
            "一个已读取叶子的 objectVersion，Runtime 对全部 target readSet 做 CAS，并原子"
            "写 tombstone Journal/Revision Diff，active tree 不保留 deleted 内容。"
        ),
        _WRITERS,
        "mutation",
        _object_schema(
            {
                "path": {"type": "string"},
                "expectedTargetVersion": {"type": "string"},
            },
            ("path", "expectedTargetVersion"),
        ),
    ),
    "set_reference": RuntimeActionSpec(
        "set_reference",
        (
            "将可验证的 exact ref 写入本角色拥有的 .ref。结构引用只允许 "
            "project://section/{stableSectionId} 或 project://unit/{stableUnitId}；"
            "不可变版本引用只允许 asset://id@version、artifact://slot@version、"
            "analysis://assetVersion@analysisVersion 或 ai-edit-plan://unit@planVersion。"
            "禁止 beat://、section://、unit://、裸哈希、latest 和自造版本 id。"
        ),
        frozenset(
            {
                SpecialistRole.STORY_PLANNING,
                SpecialistRole.VISUAL_DEVELOPMENT,
                SpecialistRole.UNIT_PLANNING_ROUTING,
                SpecialistRole.R2V_GENERATION_DIRECTOR,
            },
        ),
        "mutation",
        _object_schema(
            {
                "path": {"type": "string"},
                "versionRef": {"type": "string"},
                "expectedTargetVersion": {"type": ["string", "null"]},
            },
            ("path", "versionRef", "expectedTargetVersion"),
        ),
    ),
    "set_multi_references": RuntimeActionSpec(
        "set_multi_references",
        (
            "在一次原子 Workspace mutation 中写入多个可验证的 exact .ref。新引用的 "
            "expectedTargetVersion 传 null，覆盖既有引用必须传读取到的 exact objectVersion；"
            "任一引用、权限或 CAS 校验失败时整批不提交。"
        ),
        _WRITERS,
        "mutation",
        _object_schema(
            {
                "references": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": _object_schema(
                        {
                            "path": {"type": "string", "minLength": 1},
                            "versionRef": {"type": "string", "minLength": 1},
                            "expectedTargetVersion": {
                                "type": ["string", "null"],
                            },
                        },
                        ("path", "versionRef", "expectedTargetVersion"),
                    ),
                },
            },
            ("references",),
        ),
    ),
    "select_artifact_version": RuntimeActionSpec(
        "select_artifact_version",
        "选择具体 Artifact Version；不接受 latest 或裸 URL。",
        frozenset(
            {
                SpecialistRole.R2V_GENERATION_DIRECTOR,
            },
        ),
        "mutation",
        _object_schema(
            {
                "slotId": {"type": "string"},
                "artifactVersionId": {"type": "string"},
                "expectedSlotGeneration": {"type": "integer", "minimum": 0},
            },
            ("slotId", "artifactVersionId", "expectedSlotGeneration"),
        ),
    ),
    "image_generation": RuntimeActionSpec(
        "image_generation",
        "异步生成图片；只提交 exact Asset/Artifact Version refs，URL/checksum/kind 由 Runtime 解析。",
        frozenset(
            {
                SpecialistRole.VISUAL_DEVELOPMENT,
                SpecialistRole.R2V_GENERATION_DIRECTOR,
            },
        ),
        "execution",
        _object_schema(
            {
                "prompt": {"type": "string", "minLength": 1},
                "aspectRatio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                    "description": (
                        "提示字段；实际图片宽高比由当前 Workspace "
                        "settings/aspect-ratio.txt 强制覆盖。"
                    ),
                },
                "referenceVersionRefs": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 5,
                    "uniqueItems": True,
                },
                "slotKey": {
                    "type": ["string", "null"],
                    "description": (
                        "Visual Development 生成实体锚点时必填，且必须等于 "
                        "visual/{characters|scenes|props}/{id}--{slug}；"
                        "同一实体重生成复用同一值。R2V 分镜不得填写。"
                    ),
                },
                "displayName": {
                    "type": ["string", "null"],
                    "description": (
                        "Visual Development 生成实体锚点时必填的用户可读语义名称；" "R2V 分镜不得填写。"
                    ),
                },
            },
            (
                "prompt",
                "aspectRatio",
                "referenceVersionRefs",
            ),
        ),
    ),
    "r2v_generation": RuntimeActionSpec(
        "r2v_generation",
        "异步提交 R2V；提交时才校验 route、storyboard-first、<=15 秒、provider 与 slot CAS。",
        frozenset({SpecialistRole.R2V_GENERATION_DIRECTOR}),
        "execution",
        _object_schema(
            {
                "unitRef": {"type": "string"},
                "route": {"const": "r2v"},
                "durationSeconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 15,
                },
                "ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                    "description": (
                        "提示字段；实际 provider ratio 由当前 Workspace "
                        "settings/aspect-ratio.txt 强制覆盖。"
                    ),
                },
                "resolution": {
                    "type": "string",
                    "enum": ["720p", "1080p", "720P", "1080P"],
                    "description": (
                        "提示字段；实际 provider resolution 由当前 Workspace "
                        "settings/resolution.txt 强制规范为 720p 或 1080p。"
                    ),
                },
                "watermark": {"type": "boolean"},
            },
            (
                "unitRef",
                "route",
                "durationSeconds",
                "ratio",
                "resolution",
                "watermark",
            ),
        ),
    ),
    "ai_edit": RuntimeActionSpec(
        "ai_edit",
        "调用冻结 AI Edit Task Bridge；service-backed Director 内部使用，不进入通用模型工具循环。",
        frozenset({SpecialistRole.AI_EDITING_DIRECTOR}),
        "execution",
        _object_schema(
            {
                "operation": {
                    # Runtime has one production semantic planner; the retired
                    # episode/highlight planning graph has no compatibility API.
                    "enum": ["build_plan", "execute"],
                },
            },
            ("operation",),
        ),
    ),
    "compose": RuntimeActionSpec(
        "compose",
        "异步合成明确顺序的具体 Artifact Versions。",
        frozenset(),
        "execution",
        _object_schema(
            {
                "selections": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "sourceRef": {"type": "string"},
                            "artifactVersionId": {"type": "string"},
                            "order": {"type": "integer", "minimum": 1},
                            "transition": {"type": "string"},
                        },
                        "required": [
                            "sourceRef",
                            "artifactVersionId",
                            "order",
                            "transition",
                        ],
                        "additionalProperties": False,
                    },
                },
                "outputPath": {"type": "string"},
                "transitionDuration": {
                    "type": ["number", "null"],
                    "minimum": 0,
                },
                "xfadeType": {"type": "string"},
            },
            ("selections", "outputPath", "transitionDuration", "xfadeType"),
        ),
    ),
}


def _require_arguments(
    spec: RuntimeActionSpec,
    arguments: Mapping[str, Any],
) -> None:
    schema = spec.arguments_schema
    required = tuple(schema.get("required") or ())
    missing = [name for name in required if name not in arguments]
    extras = sorted(
        set(arguments) - set((schema.get("properties") or {}).keys()),
    )
    if missing or extras:
        raise ValidationError(
            "Runtime control action 参数不符合 manifest",
            details={"kind": spec.kind, "missing": missing, "extras": extras},
        )
    _validate_schema(arguments, schema, path=f"{spec.kind}.arguments")


def _source_publish_provider_arguments(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize only the retired Source action envelope for durable replay."""

    if "arguments" not in arguments:
        return dict(arguments)
    extras = sorted(set(arguments) - {"targetRef", "arguments"})
    nested = arguments.get("arguments")
    if isinstance(nested, str):
        try:
            nested = json.loads(nested)
        except json.JSONDecodeError:
            nested = None
    if extras or not isinstance(nested, Mapping):
        raise ValidationError(
            "非法旧版 Source Intelligence action envelope",
            details={"extras": extras},
        )
    nested_extras = sorted(set(nested) - {"summary", "semanticEntries"})
    entries = nested.get("semanticEntries")
    if nested_extras or not isinstance(entries, list):
        raise ValidationError(
            "非法旧版 Source Intelligence arguments",
            details={"extras": nested_extras},
        )
    legacy_entry_fields = {
        "id",
        "startMs",
        "endMs",
        "confidence",
        "text",
        "tags",
    }
    segments: list[Any] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            segments.append(entry)
            continue
        entry_extras = sorted(set(entry) - legacy_entry_fields)
        if entry_extras:
            raise ValidationError(
                f"旧版 Source Intelligence semanticEntries[{index}] 包含未知字段",
                details={"extras": entry_extras},
            )
        segments.append(
            {
                "startMs": entry.get("startMs"),
                "endMs": entry.get("endMs"),
                "text": entry.get("text"),
            },
        )
    return {"summary": nested.get("summary"), "segments": segments}


def _source_publish_runtime_arguments(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Inject deterministic compatibility fields outside the model contract."""

    return {
        "summary": arguments["summary"],
        "semanticEntries": [
            {
                "id": f"segment-{index:03d}",
                "startMs": segment["startMs"],
                "endMs": segment["endMs"],
                "confidence": 0.5,
                "text": segment["text"],
                "tags": [],
            }
            for index, segment in enumerate(arguments["segments"], 1)
        ],
    }


def _validate_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
) -> None:
    """Validate the bounded schema subset used by frozen Runtime actions."""

    if "const" in schema and value != schema["const"]:
        raise ValidationError(f"{path} 必须等于 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path} 不在允许枚举中")
    expected = schema.get("type")
    expected_types = (
        (expected,) if isinstance(expected, str) else tuple(expected or ())
    )
    if expected_types:
        matches = any(
            (
                (item == "null" and value is None)
                or (item == "object" and isinstance(value, Mapping))
                or (
                    item == "array"
                    and isinstance(value, Sequence)
                    and not isinstance(value, (str, bytes, bytearray))
                )
                or (item == "string" and isinstance(value, str))
                or (item == "boolean" and isinstance(value, bool))
                or (
                    item == "integer"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                )
                or (
                    item == "number"
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                )
            )
            for item in expected_types
        )
        if not matches:
            raise ValidationError(f"{path} 类型不符合 manifest: {expected_types}")
    if value is None:
        return
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ValidationError(f"{path} 字符串过短")
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path} 小于 minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path} 大于 maximum")
        if (
            "exclusiveMinimum" in schema
            and value <= schema["exclusiveMinimum"]
        ):
            raise ValidationError(f"{path} 必须大于 exclusiveMinimum")
        return
    if isinstance(value, Mapping):
        properties = dict(schema.get("properties") or {})
        required = tuple(schema.get("required") or ())
        missing = [name for name in required if name not in value]
        extras = (
            sorted(set(value) - set(properties))
            if schema.get("additionalProperties") is False
            else []
        )
        if missing or extras:
            raise ValidationError(
                f"{path} object 字段不符合 manifest",
                details={"missing": missing, "extras": extras},
            )
        for name, item in value.items():
            child = properties.get(name)
            if isinstance(child, Mapping):
                _validate_schema(item, child, path=f"{path}.{name}")
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        if len(value) < int(schema.get("minItems", 0)):
            raise ValidationError(f"{path} 数组项目不足")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValidationError(f"{path} 数组项目过多")
        if schema.get("uniqueItems"):
            serialized = [
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for item in value
            ]
            if len(serialized) != len(set(serialized)):
                raise ValidationError(f"{path} 数组项目必须唯一")
        child = schema.get("items")
        if isinstance(child, Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, child, path=f"{path}[{index}]")


class RuntimeRequestRegistry:
    """Only actions with a real injected dispatcher can reach a model manifest."""

    def __init__(
        self,
        handlers: Mapping[str, RuntimeActionHandler] | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})
        unknown = sorted(set(self._handlers) - set(RUNTIME_ACTION_SPECS))
        if unknown:
            raise ValidationError(
                f"未定义 Runtime action handler: {', '.join(unknown)}",
            )

    def implemented_for(
        self,
        role: SpecialistRole,
    ) -> tuple[RuntimeActionSpec, ...]:
        return tuple(
            spec
            for kind, spec in RUNTIME_ACTION_SPECS.items()
            if kind in self._handlers and role in spec.roles
        )

    def manifest_for(
        self,
        role: SpecialistRole,
        *,
        admitted_target_refs: Sequence[str] = (),
    ) -> tuple[dict[str, Any], ...]:
        manifest = tuple(
            spec.provider_schema() for spec in self.implemented_for(role)
        )
        if not admitted_target_refs:
            return manifest

        admitted = tuple(
            dict.fromkeys(str(item) for item in admitted_target_refs if item),
        )
        if not admitted:
            raise ValidationError(
                "Specialist Runtime action manifest 至少需要一个 admitted targetRef",
            )
        if role is SpecialistRole.SOURCE_INTELLIGENCE and (
            len(admitted) != 1 or not admitted[0].startswith("asset:")
        ):
            raise ValidationError(
                "Source Intelligence Runtime action manifest 必须绑定唯一 asset targetRef",
            )
        for item in manifest:
            if (
                role is SpecialistRole.SOURCE_INTELLIGENCE
                and item["function"]["name"] == "publish_source_intelligence"
            ):
                continue
            target_schema = item["function"]["parameters"]["properties"][
                "targetRef"
            ]
            target_schema["enum"] = list(admitted)
            target_schema["description"] = (
                "必须逐字使用本 Run 已准入的 targetRef，并且只能从本字段 enum 中选择；"
                "transaction/run/task id 或不可变版本引用均不能作为 targetRef。"
            )
        return manifest

    def prompt_lines_for(self, role: SpecialistRole) -> tuple[str, ...]:
        lines: list[str] = []
        for spec in self.implemented_for(role):
            schema = spec.provider_schema()["function"]["parameters"]
            lines.append(
                f"{spec.kind}: {spec.description} 参数 schema="
                + json.dumps(
                    schema,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return tuple(lines)

    @traced_async(
        "creator.runtime_action.dispatch",
        component="runtime_action",
        context=lambda _self, *, role, name, arguments, context: {
            "projectId": context.run_input.project_id,
            "sessionId": context.run_input.creator_session_id,
            "transactionId": context.run_input.transaction_id,
            "runId": context.run_input.run_id,
        },
        attributes=lambda _self, *, role, name, arguments, context: {
            "role": role.value,
            "action": name,
        },
    )
    async def dispatch(
        self,
        *,
        role: SpecialistRole,
        name: str,
        arguments: Mapping[str, Any],
        context: RuntimeActionContext,
    ) -> RuntimeActionResult:
        trace_event(
            "creator.runtime_action.requested",
            component="runtime_action",
            attributes={"role": role.value, "action": name},
            projectId=context.run_input.project_id,
            sessionId=context.run_input.creator_session_id,
            goalId=context.run.get("goal_id"),
            transactionId=context.run_input.transaction_id,
            runId=context.run_input.run_id,
        )
        spec = RUNTIME_ACTION_SPECS.get(name)
        handler = self._handlers.get(name)
        if spec is None or handler is None:
            raise ValidationError("本轮 manifest 不存在该 Runtime control action")
        if role not in spec.roles:
            raise PermissionDeniedError(f"{role.value} 无权执行 {name}")
        source_publish = (
            role is SpecialistRole.SOURCE_INTELLIGENCE
            and name == "publish_source_intelligence"
        )
        if source_publish:
            target_ref = (
                context.run_input.target_refs[0]
                if len(context.run_input.target_refs) == 1
                and context.run_input.target_refs[0].startswith("asset:")
                else None
            )
            provider_arguments = _source_publish_provider_arguments(arguments)
            _require_arguments(spec, provider_arguments)
            action_arguments: Any = _source_publish_runtime_arguments(
                provider_arguments,
            )
            extras: list[str] = []
        else:
            allowed = {"targetRef", "arguments"}
            if spec.category == "execution":
                allowed.add("inputRefs")
            extras = sorted(set(arguments) - allowed)
            target_ref = arguments.get("targetRef")
            action_arguments = arguments.get("arguments")
            if isinstance(action_arguments, str):
                try:
                    decoded_arguments = json.loads(action_arguments)
                except json.JSONDecodeError:
                    decoded_arguments = None
                if isinstance(decoded_arguments, Mapping):
                    action_arguments = decoded_arguments

        if (
            extras
            or not isinstance(target_ref, str)
            or not target_ref
            or not isinstance(action_arguments, Mapping)
        ):
            raise ValidationError(
                "非法 Runtime control action envelope",
                details={"kind": name, "extras": extras},
            )
        if target_ref not in context.run_input.target_refs:
            raise ValidationError(
                "Runtime action targetRef 必须与本 Run 已准入的 targetRef 完全一致",
                details={
                    "targetRef": target_ref,
                    "admittedTargetRefs": list(context.run_input.target_refs),
                },
            )
        parsed_target = parse_target_ref(target_ref)
        if (
            parsed_target.kind == "project"
            and parsed_target.identifier
            not in {
                context.run_input.project_id,
                "header",
                "plan",
                "assets",
            }
        ):
            raise ValidationError("Runtime action targetRef 不属于当前 Project")
        input_refs = arguments.get("inputRefs", ())
        if spec.category == "execution" and (
            not isinstance(input_refs, Sequence)
            or isinstance(input_refs, (str, bytes))
        ):
            raise ValidationError("Execution action inputRefs 必须是数组")
        if any(not isinstance(item, str) or not item for item in input_refs):
            raise ValidationError("Execution action inputRefs 必须是非空 ref 字符串")
        if len(input_refs) != len(set(input_refs)):
            raise ValidationError("Execution action inputRefs 不能重复")
        for input_ref in input_refs:
            try:
                parsed_input = parse_target_ref(input_ref)
            except ValidationError:
                # Execution inputs intentionally carry exact immutable
                # workspace/version refs (asset://...@version,
                # artifact://...@version).  Their Project ownership is
                # resolved from the current Project snapshot and file index by
                # the operation preparer, not inferred from the model envelope.
                validate_workspace_ref(input_ref)
            else:
                if (
                    parsed_input.kind == "project"
                    and parsed_input.identifier
                    not in {
                        context.run_input.project_id,
                        "header",
                        "plan",
                        "assets",
                    }
                ):
                    raise ValidationError(
                        "Runtime action inputRef 不属于当前 Project",
                    )
        if not source_publish:
            _require_arguments(spec, action_arguments)
        result = await handler(
            context,
            RuntimeActionDraft(
                kind=name,
                target_ref=target_ref,
                input_refs=tuple(str(item) for item in input_refs),
                arguments=dict(action_arguments),
            ),
        )
        trace_event(
            "creator.runtime_action.completed",
            component="runtime_action",
            attributes={
                "role": role.value,
                "action": name,
                "category": spec.category,
                "state": result.state.value,
                "targetRef": target_ref,
            },
            projectId=context.run_input.project_id,
            sessionId=context.run_input.creator_session_id,
            goalId=context.run.get("goal_id"),
            transactionId=context.run_input.transaction_id,
            runId=context.run_input.run_id,
            taskId=result.task_id,
        )
        return result


@dataclass(frozen=True, slots=True)
class PreparedExecution:
    expected_target_version: str
    input_fingerprint: str
    idempotency_key: str
    request: Mapping[str, Any]
    resolved_arguments: Mapping[str, Any] | None = None
    resolved_input_refs: tuple[str, ...] | None = None
    resolved_read_set: tuple[Mapping[str, Any], ...] | None = None


ExecutionPreparer = Callable[
    [RuntimeActionContext, RuntimeActionDraft],
    PreparedExecution | Awaitable[PreparedExecution],
]


class DurableTaskExecutionHandler:
    """Register first, then let the managed media worker consume the request."""

    def __init__(
        self,
        *,
        task_registry: Any,
        task_kind: TaskKind,
        prepare: ExecutionPreparer,
    ) -> None:
        self.task_registry = task_registry
        self.task_kind = task_kind
        self.prepare = prepare

    async def __call__(
        self,
        context: RuntimeActionContext,
        draft: RuntimeActionDraft,
    ) -> RuntimeActionResult:
        prepared = self.prepare(context, draft)
        if inspect.isawaitable(prepared):
            prepared = await prepared  # type: ignore[assignment,misc]
        assert isinstance(prepared, PreparedExecution)
        task_read_set = (
            prepared.resolved_read_set
            if prepared.resolved_read_set is not None
            else context.read_set
        )
        task = await self.task_registry.register(
            project_id=context.run_input.project_id,
            transaction_id=context.run_input.transaction_id,
            specialist_run_id=context.run_input.run_id,
            kind=self.task_kind,
            target_ref=draft.target_ref,
            input_fingerprint=prepared.input_fingerprint,
            expected_target_version=prepared.expected_target_version,
            idempotency_key=prepared.idempotency_key,
            read_set=task_read_set,
        )
        trace_event(
            "creator.task.registered",
            component="runtime_action",
            attributes={
                "kind": self.task_kind.value,
                "status": task["status"],
                "targetRef": draft.target_ref,
                "inputFingerprint": prepared.input_fingerprint,
            },
            projectId=context.run_input.project_id,
            sessionId=context.run_input.creator_session_id,
            goalId=context.run.get("goal_id"),
            transactionId=context.run_input.transaction_id,
            runId=context.run_input.run_id,
            taskId=task["id"],
        )
        if task["status"] == TaskStatus.SUCCEEDED.value:
            return RuntimeActionResult(
                RuntimeActionState.COMPLETED,
                {
                    "taskId": task["id"],
                    "status": task["status"],
                    "result": task.get("result"),
                },
            )
        if task["status"] not in {
            TaskStatus.QUEUED.value,
            TaskStatus.RUNNING.value,
        }:
            raise ConflictError(
                f"Runtime Task 当前不可 continuation: {task['status']}",
            )
        continuation_token = new_id("continuation-token")
        request = {
            "kind": draft.kind,
            "targetRef": draft.target_ref,
            "inputRefs": list(
                prepared.resolved_input_refs
                if prepared.resolved_input_refs is not None
                else draft.input_refs,
            ),
            "arguments": dict(prepared.resolved_arguments or draft.arguments),
            "governance": {
                "runId": context.run_input.run_id,
                "transactionId": context.run_input.transaction_id,
                "expectedTargetVersion": prepared.expected_target_version,
                "inputFingerprint": prepared.input_fingerprint,
                "idempotencyKey": prepared.idempotency_key,
                "readSet": [dict(item) for item in task_read_set],
            },
            **dict(prepared.request),
        }
        return RuntimeActionResult(
            RuntimeActionState.WAITING_RUNTIME,
            {"accepted": True, "taskId": task["id"], "status": task["status"]},
            task_id=task["id"],
            continuation_token=continuation_token,
            persisted_request=request,
        )


class AuthorizationGatedExecutionHandler:
    """Pause one Run before any costly Task is created.

    The model's concrete execution request has already crossed a durable
    assistant/action boundary when this handler runs.  Re-dispatching that same
    unresolved action after approval is safe: ``execution_request_id`` is
    stable, the authorization store replays its decision, and the wrapped task
    handler retains its own idempotency key.
    """

    def __init__(
        self,
        *,
        authorization_store: Any,
        execution_handler: DurableTaskExecutionHandler,
        provider: str,
        model: str,
        estimated_cost: float = 0.0,
        requested_candidates: int = 1,
    ) -> None:
        if not provider.strip() or not model.strip():
            raise ValidationError(
                "execution authorization provider/model 不能为空",
            )
        if estimated_cost < 0 or requested_candidates < 1:
            raise ValidationError("execution authorization cost/candidates 非法")
        self.authorization_store = authorization_store
        self.execution_handler = execution_handler
        self.provider = provider.strip()
        self.model = model.strip()
        self.estimated_cost = float(estimated_cost)
        self.requested_candidates = int(requested_candidates)

    async def _prepare(
        self,
        context: RuntimeActionContext,
        draft: RuntimeActionDraft,
    ) -> PreparedExecution:
        prepared = self.execution_handler.prepare(context, draft)
        if inspect.isawaitable(prepared):
            prepared = await prepared  # type: ignore[assignment,misc]
        assert isinstance(prepared, PreparedExecution)
        return prepared

    async def __call__(
        self,
        context: RuntimeActionContext,
        draft: RuntimeActionDraft,
    ) -> RuntimeActionResult:
        prepared = await self._prepare(context, draft)
        resolved_input_refs = (
            prepared.resolved_input_refs
            if prepared.resolved_input_refs is not None
            else draft.input_refs
        )
        target_scope = (draft.target_ref, *resolved_input_refs)
        resolved_arguments = dict(
            prepared.resolved_arguments or draft.arguments,
        )
        authorization_parameters = {
            key: resolved_arguments[key]
            for key in (
                "unitRef",
                "durationSeconds",
                "ratio",
                "resolution",
                "watermark",
                "aspectRatio",
            )
            if key in resolved_arguments
        }
        authorization = await self.authorization_store.authorize_or_request(
            project_id=context.run_input.project_id,
            transaction_id=context.run_input.transaction_id,
            specialist_run_id=context.run_input.run_id,
            execution_request_id=prepared.idempotency_key,
            operation=draft.kind,
            target_scope=target_scope,
            summary=f"执行 {draft.kind}：{draft.target_ref}",
            scope={
                "operation": draft.kind,
                "targetRefs": list(target_scope),
                "parameters": authorization_parameters,
                "inputFingerprint": prepared.input_fingerprint,
            },
            requested_provider=self.provider,
            requested_model=self.model,
            estimated_cost=self.estimated_cost,
            requested_candidates=self.requested_candidates,
        )
        if authorization["status"] == "PENDING":
            return RuntimeActionResult(
                RuntimeActionState.WAITING_AUTHORIZATION,
                {
                    "accepted": True,
                    "authorizationId": authorization["id"],
                    "status": "PENDING",
                    "executionRequestId": prepared.idempotency_key,
                },
            )
        if authorization["status"] != "APPROVED":
            raise ConflictError(
                f"execution authorization 不可执行: {authorization['status']}",
            )
        approved = await self.authorization_store.require_approved(
            project_id=context.run_input.project_id,
            transaction_id=context.run_input.transaction_id,
            specialist_run_id=context.run_input.run_id,
            execution_request_id=prepared.idempotency_key,
            provider=self.provider,
            model=self.model,
            cost=self.estimated_cost,
            candidates=self.requested_candidates,
        )
        result = await self.execution_handler(context, draft)
        if result.persisted_request is None:
            return result
        decision = dict((approved.get("metadata") or {}).get("decision") or {})
        request = {
            **dict(result.persisted_request),
            "executionAuthorization": {
                "authorizationId": approved["id"],
                "executionRequestId": prepared.idempotency_key,
                "provider": decision.get("provider"),
                "model": decision.get("model"),
                "maxCost": decision.get("maxCost"),
                "maxCandidates": decision.get("maxCandidates"),
            },
        }
        return replace(result, persisted_request=request)


def _expectation_for(
    run_input: SpecialistRunInput,
    target_ref: str,
) -> TargetExpectation:
    matches = [
        item
        for item in run_input.target_expectations
        if item.ref == target_ref
    ]
    if len(matches) != 1:
        raise ConflictError(
            "Execution action targetRef 必须精确等于本 Run 已准入的 targetRef",
            details={
                "targetRef": target_ref,
                "admittedTargetRefs": [
                    item.ref for item in run_input.target_expectations
                ],
            },
        )
    return matches[0]


def _target_version(expectation: TargetExpectation) -> str:
    if expectation.object_version:
        return expectation.object_version
    if expectation.slot_generation is not None:
        return f"slot-generation:{expectation.slot_generation}"
    raise ConflictError("目标 expectation 未携带 object version 或 slot generation")


def execution_target_version(
    context: RuntimeActionContext,
    target_ref: str,
) -> str:
    """Return the Runtime-owned CAS value for one concrete execution target."""

    return _target_version(_expectation_for(context.run_input, target_ref))


def _execution_idempotency(
    context: RuntimeActionContext,
    draft: RuntimeActionDraft,
) -> str:
    payload = json.dumps(
        {
            "projectId": context.run_input.project_id,
            "transactionId": context.run_input.transaction_id,
            "runId": context.run_input.run_id,
            "kind": draft.kind,
            "targetRef": draft.target_ref,
            "inputRefs": list(draft.input_refs),
            "arguments": dict(draft.arguments),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"specialist:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def execution_idempotency_key(
    context: RuntimeActionContext,
    draft: RuntimeActionDraft,
) -> str:
    """Bind idempotency to the authoritative, resolved execution request."""

    return _execution_idempotency(context, draft)


def prepare_generic_execution(
    context: RuntimeActionContext,
    draft: RuntimeActionDraft,
) -> PreparedExecution:
    expectation = _expectation_for(context.run_input, draft.target_ref)
    return PreparedExecution(
        expected_target_version=_target_version(expectation),
        input_fingerprint=canonical_json_hash(
            {
                "kind": draft.kind,
                "targetRef": draft.target_ref,
                "inputRefs": list(draft.input_refs),
                "arguments": dict(draft.arguments),
            },
        ),
        idempotency_key=_execution_idempotency(context, draft),
        request={},
    )


def image_execution_preparer(
    context: RuntimeActionContext,
    draft: RuntimeActionDraft,
) -> PreparedExecution:
    expectation = _expectation_for(context.run_input, draft.target_ref)
    arguments = draft.arguments
    reference_urls = arguments.get("referenceImageUrls", ())
    fingerprint = canonical_json_hash(
        {
            "prompt": str(arguments["prompt"]),
            "aspectRatio": str(arguments["aspectRatio"]),
            "referenceImageUrls": [str(item) for item in reference_urls],
            "referenceVersionRefs": [],
            "referenceChecksums": [],
            "resolvedInputManifest": {},
        },
    )
    return PreparedExecution(
        expected_target_version=_target_version(expectation),
        input_fingerprint=fingerprint,
        idempotency_key=_execution_idempotency(context, draft),
        request={},
    )


def compose_execution_preparer(
    context: RuntimeActionContext,
    draft: RuntimeActionDraft,
) -> PreparedExecution:
    expectation = _expectation_for(context.run_input, draft.target_ref)
    arguments = draft.arguments
    selections = [
        {
            "sourceRef": str(item["sourceRef"]),
            "artifactVersionId": str(item["artifactVersionId"]),
            "order": int(item["order"]),
            "transition": str(item["transition"]),
        }
        for item in arguments["selections"]
    ]
    orders = [item["order"] for item in selections]
    if orders != list(range(1, len(orders) + 1)) or len(orders) != len(
        set(orders),
    ):
        raise ValidationError("Compose order 必须从 1 连续且唯一")
    fingerprint = canonical_json_hash(
        {
            "selections": selections,
            "outputPath": str(arguments["outputPath"]),
            "transitionDuration": arguments["transitionDuration"],
            "xfadeType": str(arguments["xfadeType"]),
            "resolvedInputManifest": {},
        },
    )
    return PreparedExecution(
        expected_target_version=_target_version(expectation),
        input_fingerprint=fingerprint,
        idempotency_key=_execution_idempotency(context, draft),
        request={},
    )


def _capability_payload(
    capability: ProviderCapabilitySnapshot,
) -> dict[str, Any]:
    return {
        "provider": capability.provider,
        "model": capability.model,
        "version": capability.version,
        "capturedAt": capability.captured_at.isoformat(),
        "minDurationSeconds": float(capability.min_duration_seconds),
        "maxDurationSeconds": float(capability.max_duration_seconds),
        "maxReferenceImages": capability.max_reference_images,
        "allowedDurationsSeconds": [
            float(item) for item in capability.allowed_durations_seconds
        ],
    }


def r2v_execution_preparer(
    capability: ProviderCapabilitySnapshot,
) -> ExecutionPreparer:
    """Build the operation-level validator; never use this during delegate admission."""

    def prepare(
        context: RuntimeActionContext,
        draft: RuntimeActionDraft,
    ) -> PreparedExecution:
        expectation = _expectation_for(context.run_input, draft.target_ref)
        arguments = draft.arguments
        reference_versions = tuple(
            str(item) for item in arguments["referenceVersionIds"]
        )
        expected_generation = expectation.slot_generation
        capability_payload = _capability_payload(capability)
        capability_fingerprint = dict(capability_payload)
        # The observation timestamp remains in the persisted capability
        # snapshot, but it is not a provider constraint and must not make an
        # otherwise identical request change identity after a restart.
        capability_fingerprint.pop("capturedAt", None)
        fingerprint = canonical_json_hash(
            {
                "unitRef": str(arguments["unitRef"]),
                "durationSeconds": arguments["durationSeconds"],
                "storyboardVersionId": str(arguments["storyboardVersionId"]),
                "storyboardChecksum": str(arguments["storyboardChecksum"]),
                "videoPromptHash": (
                    "sha256:"
                    + hashlib.sha256(
                        str(arguments["videoPrompt"]).encode("utf-8"),
                    ).hexdigest()
                ),
                "referenceVersionIds": [
                    str(item) for item in arguments["referenceVersionIds"]
                ],
                "referenceUrls": [
                    str(item) for item in arguments["referenceUrls"]
                ],
                "referenceVersionRefs": [],
                "expectedSlotGeneration": expected_generation,
                "ratio": str(arguments["ratio"]),
                "resolution": str(arguments["resolution"]),
                "watermark": bool(arguments["watermark"]),
                "capability": capability_fingerprint,
                "resolvedInputManifest": {},
            },
        )
        report = validate_r2v_execution(
            R2VExecutionRequest(
                unit_ref=str(arguments["unitRef"]),
                route=str(arguments["route"]),
                duration_seconds=float(arguments["durationSeconds"]),
                storyboard_version_ref=str(
                    arguments["storyboardVersionId"] or "",
                ),
                storyboard_checksum=str(arguments["storyboardChecksum"] or ""),
                video_prompt=str(arguments["videoPrompt"]),
                reference_image_refs=reference_versions,
                transaction_active=True,
                input_fingerprint=fingerprint,
                expected_slot_generation=expected_generation,
                observed_slot_generation=expected_generation,
                capability=capability,
            ),
        )
        if not report.valid:
            raise ValidationError(
                "; ".join(
                    f"{item.code}: {item.message}" for item in report.issues
                ),
            )
        reference_urls = tuple(
            str(item) for item in arguments["referenceUrls"]
        )
        if reference_versions[0:1] != (str(arguments["storyboardVersionId"]),):
            raise ValidationError(
                "R2V storyboard version 必须位于 referenceVersionIds 第一位",
            )
        if reference_urls[0:1] != (str(arguments["storyboardUrl"]),):
            raise ValidationError("R2V storyboard URL 必须位于 referenceUrls 第一位")
        if len(reference_urls) != len(reference_versions):
            raise ValidationError("R2V reference version/url manifest 长度不一致")
        return PreparedExecution(
            expected_target_version=_target_version(expectation),
            input_fingerprint=fingerprint,
            idempotency_key=_execution_idempotency(context, draft),
            request={
                "providerCapabilitySnapshot": capability_payload,
            },
        )

    return prepare


__all__ = [
    "AuthorizationGatedExecutionHandler",
    "DurableTaskExecutionHandler",
    "PreparedExecution",
    "RUNTIME_ACTION_SPECS",
    "RuntimeActionContext",
    "RuntimeActionDraft",
    "RuntimeActionResult",
    "RuntimeActionSpec",
    "RuntimeActionState",
    "RuntimeRequestRegistry",
    "compose_execution_preparer",
    "execution_idempotency_key",
    "execution_target_version",
    "image_execution_preparer",
    "prepare_generic_execution",
    "r2v_execution_preparer",
]
