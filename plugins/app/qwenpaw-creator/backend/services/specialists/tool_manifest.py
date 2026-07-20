"""Provider tool schemas for the one seven-file-tool Specialist surface."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

from domain.enums import SpecialistRole
from domain.errors import ValidationError
from services.workspace.permissions import FILE_TOOL_NAMES, resolve_role

_STRING = {"type": "string"}
_NULLABLE_STRING = {"type": ["string", "null"]}


FILE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": {
        "description": "读取获授权 Text Workspace 文件并记录具体 blob/object version。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": _STRING,
                "start_line": {"type": ["integer", "null"], "minimum": 1},
                "end_line": {"type": ["integer", "null"], "minimum": 1},
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    "write_file": {
        "description": (
            "创建或覆盖本角色拥有的 Text Workspace 文本叶子；参数与 QwenPaw write_file "
            "一致，只需 file_path 和 content。Runtime 会在 writer lease 内绑定当前文件版本，"
            "父虚拟目录尚不存在时先用 create_path 建立首个叶子。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": _STRING,
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
            "additionalProperties": False,
        },
    },
    "edit_file": {
        "description": "以显式 blob/object CAS 替换本角色拥有文件中的精确文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": _STRING,
                "old_text": {"type": "string", "minLength": 1},
                "new_text": {"type": "string"},
                "replace_all": {"type": "boolean", "default": True},
                "expected_blob_hash": _NULLABLE_STRING,
                "expected_object_version": _NULLABLE_STRING,
            },
            "required": [
                "file_path",
                "old_text",
                "new_text",
                "expected_blob_hash",
                "expected_object_version",
            ],
            "additionalProperties": False,
        },
    },
    "append_file": {
        "description": "以显式 blob/object CAS 向本角色拥有的文件追加文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": _STRING,
                "content": {"type": "string"},
                "expected_blob_hash": _NULLABLE_STRING,
                "expected_object_version": _NULLABLE_STRING,
            },
            "required": [
                "file_path",
                "content",
                "expected_blob_hash",
                "expected_object_version",
            ],
            "additionalProperties": False,
        },
    },
    "grep_search": {
        "description": "在获授权文本范围内搜索内容并记录所有实际读取版本。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _STRING,
                "path": _NULLABLE_STRING,
                "is_regex": {"type": "boolean", "default": False},
                "case_sensitive": {"type": "boolean", "default": True},
                "context_lines": {"type": "integer", "minimum": 0, "maximum": 5},
                "include_pattern": _NULLABLE_STRING,
                "max_results": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    "glob_search": {
        "description": "列出获授权 Text Workspace 中匹配的文件及其版本。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _STRING,
                "path": _NULLABLE_STRING,
                "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    "ast_search": {
        "description": "搜索 Markdown/VTT/CTM/TXT/REF 的结构化文本节点。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _STRING,
                "path": _NULLABLE_STRING,
                "max_results": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
}

if tuple(FILE_TOOL_SCHEMAS) != FILE_TOOL_NAMES:
    raise RuntimeError("file tool schemas must follow the exact seven-tool ordering")


def provider_function(name: str, definition: Mapping[str, Any]) -> dict[str, Any]:
    """Return the AgentScope/OpenAI-compatible function descriptor."""

    try:
        description = str(definition["description"])
        parameters = deepcopy(dict(definition["parameters"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"非法 model tool schema: {name}") from exc
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def file_tool_manifest(role: SpecialistRole) -> tuple[dict[str, Any], ...]:
    allowed = set(resolve_role(role).tools)
    return tuple(
        provider_function(name, FILE_TOOL_SCHEMAS[name])
        for name in FILE_TOOL_NAMES
        if name in allowed
    )


def combine_tool_manifests(*manifests: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for manifest in manifests:
        for item in manifest:
            value = deepcopy(dict(item))
            name = str((value.get("function") or {}).get("name") or "")
            if not name or name in seen:
                raise ValidationError(f"重复或非法 model tool: {name!r}")
            seen.add(name)
            combined.append(value)
    return tuple(combined)


__all__ = [
    "FILE_TOOL_SCHEMAS",
    "combine_tool_manifests",
    "file_tool_manifest",
    "provider_function",
]
