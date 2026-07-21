# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""AgentScope provider tool schemas for every Creator control action."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.specialists.registry import (
    DELEGATE_TOOL_NAME,
    FINALIZE_VIDEO_TOOL_NAME,
    GROUND_PROMPT_CONTEXT_TOOL_NAME,
    READ_FILE_TOOLS,
    WRITE_FILE_TOOLS,
    creator_available_actions,
    creator_delegate_arguments_schema,
)
from services.specialists.tool_manifest import (
    FILE_TOOL_SCHEMAS,
    provider_function,
)


_STRING = {"type": "string"}


CREATOR_CONTROL_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "plan": {
        "description": "持久化当前 Goal 的执行计划；任何会修改 Workspace 的动作前必须先调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": _STRING,
                "steps": {
                    "type": "array",
                    "items": _STRING,
                    "minItems": 1,
                },
                "scope": {
                    "type": "array",
                    "items": _STRING,
                    "minItems": 1,
                },
            },
            "required": ["summary", "steps", "scope"],
            "additionalProperties": False,
        },
    },
    "final": {
        "description": "对只读问题给出最终回复，或在确实需要用户选择时结束当前轮。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": _STRING,
                "awaitUserInput": {"type": "boolean"},
            },
            "required": ["message", "awaitUserInput"],
            "additionalProperties": False,
        },
    },
    DELEGATE_TOOL_NAME: {
        "description": "把一个边界明确的专业任务委派给已注册的 Creator Specialist。",
        "parameters": creator_delegate_arguments_schema(),
    },
    GROUND_PROMPT_CONTEXT_TOOL_NAME: {
        "description": (
            "只读 web grounding：为真实人物、品牌、地点、赛事、IP、视觉风格或文化/服饰/材质引用"
            "获取 source-backed context 和下载后的视觉参考。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string", "minLength": 1},
                "prompt": _STRING,
                "queries": {
                    "type": "array",
                    "items": _STRING,
                },
                "includeVisuals": {"type": "boolean"},
                "context": {
                    "type": "object",
                    "additionalProperties": True,
                },
                "force": {"type": "boolean"},
                "detectOnly": {"type": "boolean"},
                "detector": {
                    "type": "string",
                    "enum": ["hybrid", "llm", "heuristic"],
                },
            },
            "required": ["projectId"],
            "additionalProperties": False,
        },
    },
    FINALIZE_VIDEO_TOOL_NAME: {
        "description": "使用当前 Workspace 的权威结果执行最终视频拼接。",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    "yield_until_runtime_event": {
        "description": "没有其他独立工作可推进时，等待一个或多个非终态 Specialist Run。",
        "parameters": {
            "type": "object",
            "properties": {
                "waitForRunIds": {
                    "type": "array",
                    "items": _STRING,
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "reason": _STRING,
            },
            "required": ["waitForRunIds", "reason"],
            "additionalProperties": False,
        },
    },
    "complete_current_change": {
        "description": "使用 Runtime 最新控制上下文提交当前修改的完成检查。",
        "parameters": {
            "type": "object",
            "properties": {
                "transactionId": _STRING,
                "expectedWorkingHead": _STRING,
                "lastConsumedMessageSeq": {"type": "integer", "minimum": 0},
                "consistencyReportId": _STRING,
                "completionIntent": {
                    "type": "string",
                    "enum": [
                        "CONTINUE_AFTER_REVIEW",
                        "COMPLETE_AFTER_REVIEW",
                    ],
                },
                "completedRequirement": _STRING,
                "completionSummary": _STRING,
            },
            "required": [
                "transactionId",
                "expectedWorkingHead",
                "lastConsumedMessageSeq",
                "consistencyReportId",
                "completionIntent",
                "completedRequirement",
                "completionSummary",
            ],
            "additionalProperties": False,
        },
    },
}


def creator_tool_manifest() -> tuple[dict[str, Any], ...]:
    """Return the complete, fixed Creator AgentScope tool manifest in registry order."""

    definitions: dict[str, dict[str, Any]] = {
        **{
            name: deepcopy(FILE_TOOL_SCHEMAS[name])
            for name in READ_FILE_TOOLS + WRITE_FILE_TOOLS
        },
        **deepcopy(CREATOR_CONTROL_TOOL_SCHEMAS),
    }
    manifest = tuple(
        provider_function(name, definitions[name])
        for name in creator_available_actions()
    )
    names = tuple(str(item["function"]["name"]) for item in manifest)
    if names != creator_available_actions():
        raise RuntimeError("Creator provider tool manifest drift")
    return manifest


__all__ = ["CREATOR_CONTROL_TOOL_SCHEMAS", "creator_tool_manifest"]
