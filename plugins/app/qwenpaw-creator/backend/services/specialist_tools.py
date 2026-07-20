"""File-native toolkits owned by Creator specialists.

The Agent runtime consumes this registry as a generic AgentScope tool surface.
Business capabilities stay here: role admission, provider schemas and media
handlers.  Handlers publish through the existing file services, so generated
results update ``project.json``/Asset Index and Runtime records without a SQL
transaction or an overlay ChangeSet.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.enums import CreatorCommandType, SpecialistRole
from domain.errors import PermissionDeniedError, ValidationError
from services.media_files.image_execution import execute_file_image_command
from services.media_files.local_execution import execute_file_local_media_command
from services.media_files.r2v_execution import execute_file_r2v_command
from services.project_files.agent_tools import (
    AgentProjectTools,
    agent_project_tool_manifest,
)
from services.project_files.facade import CreatorFileServices
from services.source_analysis import source_analysis_service


class SpecialistToolWait(StrEnum):
    NONE = "NONE"
    TASK = "TASK"


_PROJECT_ASSETS_TARGET_REF = "project:assets"
_ASSET_TARGET_REF_PATTERN = r"^asset:.+$"


@dataclass(frozen=True, slots=True)
class SpecialistToolSpec:
    name: str
    description: str
    roles: frozenset[SpecialistRole]
    parameters: Mapping[str, Any]
    requires_execution_authorization: bool = False
    long_running: bool = False
    wait: SpecialistToolWait = SpecialistToolWait.NONE
    provider_kind: str | None = None

    def expands_project_assets_scope(
        self,
        *,
        role: SpecialistRole,
        admitted_target_refs: Sequence[str],
    ) -> bool:
        """Let a visual Project-assets run address its Asset children."""

        return (
            self.name == "image_generation"
            and role is SpecialistRole.VISUAL_DEVELOPMENT
            and _PROJECT_ASSETS_TARGET_REF in admitted_target_refs
        )

    def admits_target_ref(
        self,
        *,
        role: SpecialistRole,
        target_ref: str,
        admitted_target_refs: Sequence[str],
    ) -> bool:
        if self.expands_project_assets_scope(
            role=role,
            admitted_target_refs=admitted_target_refs,
        ):
            return target_ref.startswith("asset:") and bool(target_ref[6:])
        return target_ref in admitted_target_refs

    def manifest(
        self,
        *,
        role: SpecialistRole,
        admitted_target_refs: Sequence[str],
    ) -> dict[str, Any]:
        value = provider_function(
            self.name,
            {"description": self.description, "parameters": self.parameters},
        )
        targets = tuple(dict.fromkeys(admitted_target_refs))
        if targets:
            target = value["function"]["parameters"]["properties"].get("targetRef")
            if isinstance(target, dict):
                if self.expands_project_assets_scope(
                    role=role,
                    admitted_target_refs=targets,
                ):
                    target["pattern"] = _ASSET_TARGET_REF_PATTERN
                    target["description"] = (
                        "必须使用本 Project 中已存在的 exact asset:<entityId>，"
                        "不能直接使用 project:assets。"
                    )
                else:
                    target["enum"] = list(targets)
                    target["description"] = (
                        "必须逐字使用本 SpecialistRun 已准入的 targetRef。"
                    )
        return value


def provider_function(name: str, definition: Mapping[str, Any]) -> dict[str, Any]:
    """Build one native AgentScope/OpenAI function descriptor."""

    description = str(definition.get("description") or "").strip()
    parameters = definition.get("parameters")
    if not description or not isinstance(parameters, Mapping):
        raise ValidationError(f"非法 Specialist tool schema: {name}")
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": deepcopy(dict(parameters)),
        },
    }


@dataclass(frozen=True, slots=True)
class SpecialistToolResult:
    payload: dict[str, Any]
    task_id: str | None = None


def _arguments_schema(
    properties: Mapping[str, Any], required: Sequence[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


def _tool_schema(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "projectId": {"type": "string", "minLength": 1},
            "targetRef": {"type": "string", "minLength": 1},
            "arguments": dict(arguments),
        },
        "required": ["projectId", "targetRef", "arguments"],
        "additionalProperties": False,
    }


_IMAGE_ARGUMENTS = _arguments_schema(
    {
        "prompt": {"type": "string", "minLength": 1},
        "aspectRatio": {
            "type": "string",
            "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        },
        "referenceVersionIds": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "maxItems": 5,
            "uniqueItems": True,
        },
    },
    ("prompt",),
)

_R2V_ARGUMENTS = _arguments_schema(
    {
        "prompt": {"type": "string", "minLength": 1},
        "durationSeconds": {"type": "integer", "minimum": 1, "maximum": 60},
        "ratio": {
            "type": "string",
            "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        },
        "resolution": {"type": "string", "enum": ["720P", "1080P", "720p", "1080p"]},
        "watermark": {"type": "boolean"},
        "generateAudio": {"type": "boolean"},
    },
    ("prompt", "durationSeconds", "ratio", "resolution", "watermark"),
)

_SPECS = (
    SpecialistToolSpec(
        name="analyze_source_media",
        description=(
            "分析已入库的本地文件或公网 URL 源素材，并把结构化理解写入文件索引。"
            "首次分析使用 force=false；只有已有结果需要明确重做，或上一次调用因 "
            "ReadTimeout 等瞬时模型请求错误且没有产生新结果时，才使用 force=true "
            "重试一次。成功后重新读取 Project；失败时不得伪造素材理解关联。"
        ),
        roles=frozenset({SpecialistRole.SOURCE_INTELLIGENCE}),
        parameters=_tool_schema(
            _arguments_schema(
                {
                    "force": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "首次分析为 false。仅在用户明确要求重新分析，或上一次调用"
                            "因瞬时模型请求错误失败且未产生新结果时改为 true；同一失败"
                            "最多重试一次。"
                        ),
                    }
                },
                (),
            )
        ),
        long_running=True,
        wait=SpecialistToolWait.TASK,
        provider_kind="vlm",
    ),
    SpecialistToolSpec(
        name="image_generation",
        description=(
            "生成视觉资产或 R2V 分镜图片。只传 Project 中已存在的 exact version id；"
            "生成结果由文件媒体服务写入 Asset Index 与 project.json。"
        ),
        roles=frozenset(
            {SpecialistRole.VISUAL_DEVELOPMENT, SpecialistRole.R2V_GENERATION_DIRECTOR}
        ),
        parameters=_tool_schema(_IMAGE_ARGUMENTS),
        requires_execution_authorization=True,
        long_running=True,
        provider_kind="image",
    ),
    SpecialistToolSpec(
        name="r2v_generation",
        description=(
            "为已选择真实 storyboard ArtifactVersion 的 r2v Unit 提交视频生成；"
            "Runtime 文件任务完成后结果自动写回 Asset Index 与 project.json。"
        ),
        roles=frozenset({SpecialistRole.R2V_GENERATION_DIRECTOR}),
        parameters=_tool_schema(_R2V_ARGUMENTS),
        requires_execution_authorization=True,
        long_running=True,
        wait=SpecialistToolWait.TASK,
        provider_kind="video",
    ),
    SpecialistToolSpec(
        name="ai_edit",
        description=(
            "执行已经通过 jq_project 写入 project.json 的当前 AI Edit Plan。"
            "本工具不生成 plan；plan 的内容与规则来自本 Specialist 的 prompt。"
        ),
        roles=frozenset({SpecialistRole.AI_EDITING_DIRECTOR}),
        parameters=_tool_schema(
            _arguments_schema(
                {"operation": {"type": "string", "const": "execute"}},
                ("operation",),
            )
        ),
        long_running=True,
        provider_kind="local_media",
    ),
)

_SPECS_BY_NAME = {item.name: item for item in _SPECS}
_PROJECT_TOOL_NAMES = frozenset(
    item["function"]["name"] for item in agent_project_tool_manifest()
)


class FileSpecialistToolRegistry:
    """Role-scoped AgentScope tool registry for the file Project model."""

    def __init__(self, services: CreatorFileServices) -> None:
        self.services = services

    def spec_for(self, role: SpecialistRole, name: str) -> SpecialistToolSpec | None:
        spec = _SPECS_BY_NAME.get(name)
        if spec is None:
            return None
        if role not in spec.roles:
            raise PermissionDeniedError(f"{role.value} 无权调用 {name}")
        return spec

    def manifest_for(
        self,
        role: SpecialistRole,
        *,
        admitted_target_refs: Sequence[str],
    ) -> tuple[dict[str, Any], ...]:
        project_tools = list(agent_project_tool_manifest())
        if role is SpecialistRole.REVIEW_CONSISTENCY:
            project_tools = [
                item
                for item in project_tools
                if item["function"]["name"] != "jq_project"
            ]
        business_tools = [
            spec.manifest(role=role, admitted_target_refs=admitted_target_refs)
            for spec in _SPECS
            if role in spec.roles
        ]
        names = [item["function"]["name"] for item in (*project_tools, *business_tools)]
        if len(names) != len(set(names)):
            raise RuntimeError("Specialist tool manifest contains duplicate names")
        return tuple(deepcopy(item) for item in (*project_tools, *business_tools))

    async def invoke(
        self,
        *,
        role: SpecialistRole,
        name: str,
        arguments: Mapping[str, Any],
        project_id: str,
        admitted_target_refs: Sequence[str],
        project_tools: AgentProjectTools,
        idempotency_key: str,
    ) -> SpecialistToolResult:
        if name in _PROJECT_TOOL_NAMES:
            payload = await asyncio.to_thread(project_tools.invoke, name, arguments)
            return SpecialistToolResult(payload=dict(payload))

        spec = self.spec_for(role, name)
        if spec is None:
            raise ValidationError(f"Specialist manifest 不存在工具: {name}")
        requested_project_id = str(arguments.get("projectId") or "")
        target_ref = str(arguments.get("targetRef") or "")
        if requested_project_id != project_id:
            raise PermissionDeniedError("Specialist tool attempted another Project")
        if not spec.admits_target_ref(
            role=role,
            target_ref=target_ref,
            admitted_target_refs=admitted_target_refs,
        ):
            raise PermissionDeniedError("Specialist tool targetRef 不在本 Run 准入范围")
        payload = arguments.get("arguments")
        if not isinstance(payload, Mapping):
            raise ValidationError("Specialist tool arguments 必须是 object")

        if name == "analyze_source_media":
            dispatch = await source_analysis_service(self.services).dispatch(
                project_id=project_id,
                target_ref=target_ref,
                command_id=idempotency_key,
                arguments=payload,
                start=True,
            )
            return SpecialistToolResult(
                payload={
                    "ok": True,
                    "status": dispatch.task.status.value,
                    "taskId": dispatch.task.task_id,
                    "analysisRef": dispatch.job.intelligence_ref,
                },
                task_id=dispatch.task.task_id,
            )

        if name == "image_generation":
            command = (
                CreatorCommandType.GENERATE_ASSET
                if role is SpecialistRole.VISUAL_DEVELOPMENT
                else CreatorCommandType.GENERATE_STORYBOARD_IMAGE
            )
            execution = await execute_file_image_command(
                self.services,
                project_id=project_id,
                command=command,
                target_ref=target_ref,
                arguments=payload,
                idempotency_key=idempotency_key,
            )
            return SpecialistToolResult(
                payload={
                    "ok": True,
                    "status": "SUCCEEDED",
                    "taskId": execution.task_id,
                    "artifactVersionId": execution.artifact_version_id,
                    "generation": execution.project_generation,
                    "etag": execution.project_etag,
                    "replayed": execution.replayed,
                },
                task_id=execution.task_id,
            )

        if name == "r2v_generation":
            execution = await execute_file_r2v_command(
                self.services,
                project_id=project_id,
                target_ref=target_ref,
                arguments=payload,
                idempotency_key=idempotency_key,
            )
            return SpecialistToolResult(
                payload={
                    "ok": True,
                    "status": "QUEUED",
                    "taskId": execution.task_id,
                    "runId": execution.run_id,
                    "replayed": execution.replayed,
                },
                task_id=execution.task_id,
            )

        if name == "ai_edit":
            execution = await execute_file_local_media_command(
                self.services,
                project_id=project_id,
                command=CreatorCommandType.EXECUTE_EDIT,
                target_ref=target_ref,
                arguments=payload,
                idempotency_key=idempotency_key,
            )
            return SpecialistToolResult(
                payload={
                    "ok": True,
                    "status": "SUCCEEDED",
                    "taskId": execution.task_id,
                    "artifactVersionId": execution.artifact_version_id,
                    "generation": execution.project_generation,
                    "etag": execution.project_etag,
                    "replayed": execution.replayed,
                },
                task_id=execution.task_id,
            )
        raise RuntimeError(f"unhandled Specialist tool: {name}")


__all__ = [
    "FileSpecialistToolRegistry",
    "SpecialistToolResult",
    "SpecialistToolSpec",
    "SpecialistToolWait",
]
