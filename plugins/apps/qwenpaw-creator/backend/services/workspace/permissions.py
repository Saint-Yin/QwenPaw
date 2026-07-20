# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=unused-argument
"""Role-filtered file-tool and Text Workspace path permissions.

The Specialist Registry remains the source of role/runner/tool facts.  This
module adds the narrower file ownership predicates required to ensure that one
content file has at most one writer.  Shared structure changes are Runtime
mutations, not broad overlapping file grants.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from domain.enums import SpecialistRole
from domain.errors import PermissionDeniedError, ValidationError
from services.specialists.registry import SPECIALIST_REGISTRY

from .paths import compile_workspace_glob, workspace_text_path


CREATOR_ROLE = "creator_agent"
CREATOR_WRITE_PATTERNS = ("settings/**", "strategy/**", "post/**")
READ_FILE_TOOLS = ("read_file", "grep_search", "glob_search", "ast_search")
WRITE_FILE_TOOLS = ("write_file", "edit_file", "append_file")
FILE_TOOL_NAMES = (
    "read_file",
    "write_file",
    "edit_file",
    "append_file",
    "grep_search",
    "glob_search",
    "ast_search",
)

if len(FILE_TOOL_NAMES) != 7 or len(set(FILE_TOOL_NAMES)) != 7:
    raise RuntimeError(
        "File tool registry must contain exactly seven unique names",
    )


class WorkspacePermissionDenied(PermissionDeniedError):
    """A principal attempted a tool or path operation it does not own."""

    def __init__(self, role: str, action: str, target: str) -> None:
        super().__init__(
            f"角色 {role!r} 无权执行 {action}: {target}",
            details={"role": role, "action": action, "target": target},
        )


# Stable export name used by service callers; this is the new domain error,
# not the retired package-document permission system.
PermissionDenied = WorkspacePermissionDenied


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = workspace_text_path(path)
    return any(
        compile_workspace_glob(pattern).fullmatch(normalized)
        for pattern in patterns
    )


def path_owner(path: str) -> SpecialistRole | str | None:
    """Resolve the sole writer from the authoritative Specialist Registry."""

    normalized = workspace_text_path(path)
    owners: tuple[SpecialistRole | str, ...] = tuple(
        spec.role
        for spec in SPECIALIST_REGISTRY.values()
        if spec.write_scopes and path_matches(normalized, spec.write_scopes)
    )
    if path_matches(normalized, CREATOR_WRITE_PATTERNS):
        owners += (CREATOR_ROLE,)
    if len(owners) > 1:
        raise RuntimeError(
            "Specialist Registry contains overlapping write scopes for "
            f"{normalized}: {[role.value for role in owners]}",
        )
    return owners[0] if owners else None


def _normalize_role(role: SpecialistRole | str) -> str:
    value = role.value if isinstance(role, SpecialistRole) else role
    if not isinstance(value, str) or not value:
        raise ValidationError("workspace role 不能为空")
    if value != CREATOR_ROLE:
        try:
            SpecialistRole(value)
        except ValueError as exc:
            raise ValidationError(
                "未知 workspace role",
                details={"role": value},
            ) from exc
    return value


def tools_for_role(role: SpecialistRole | str) -> tuple[str, ...]:
    value = _normalize_role(role)
    if value == CREATOR_ROLE:
        return READ_FILE_TOOLS + WRITE_FILE_TOOLS
    specialist_role = SpecialistRole(value)
    spec = SPECIALIST_REGISTRY.get(specialist_role)
    if spec is None:
        raise ValidationError(
            "该历史 specialist role 已停用",
            details={"role": value},
        )
    # Registry tuples are normalized to the one public seven-name ordering.
    allowed = set(spec.allowed_file_tools)
    return tuple(name for name in FILE_TOOL_NAMES if name in allowed)


def read_patterns_for_role(role: SpecialistRole | str) -> tuple[str, ...]:
    value = _normalize_role(role)
    if value == CREATOR_ROLE:
        return ("**",)
    return SPECIALIST_REGISTRY[SpecialistRole(value)].read_scopes


def write_patterns_for_role(role: SpecialistRole | str) -> tuple[str, ...]:
    value = _normalize_role(role)
    if value == CREATOR_ROLE:
        return CREATOR_WRITE_PATTERNS
    specialist_role = SpecialistRole(value)
    spec = SPECIALIST_REGISTRY.get(specialist_role)
    if spec is None:
        raise ValidationError(
            "该历史 specialist role 已停用",
            details={"role": value},
        )
    return spec.write_scopes


@dataclass(frozen=True, slots=True)
class ResolvedRolePermissions:
    role: str
    tools: tuple[str, ...]
    read_patterns: tuple[str, ...]
    write_patterns: tuple[str, ...]


def resolve_role(role: SpecialistRole | str) -> ResolvedRolePermissions:
    value = _normalize_role(role)
    return ResolvedRolePermissions(
        role=value,
        tools=tools_for_role(value),
        read_patterns=read_patterns_for_role(value),
        write_patterns=write_patterns_for_role(value),
    )


class PermissionRegistry:
    """Hard checks applied by every public file-tool method."""

    def resolve(self, role: SpecialistRole | str) -> ResolvedRolePermissions:
        return resolve_role(role)

    def is_known_role(self, role: SpecialistRole | str) -> bool:
        try:
            _normalize_role(role)
        except ValidationError:
            return False
        return True

    def can_use_tool(self, role: SpecialistRole | str, tool_name: str) -> bool:
        try:
            return tool_name in tools_for_role(role)
        except ValidationError:
            return False

    def ensure_tool(self, role: SpecialistRole | str, tool_name: str) -> None:
        value = role.value if isinstance(role, SpecialistRole) else str(role)
        if tool_name not in FILE_TOOL_NAMES:
            raise ValidationError("未知 file tool", details={"tool": tool_name})
        if not self.can_use_tool(role, tool_name):
            raise WorkspacePermissionDenied(value, "调用文件工具", tool_name)

    def can_read_path(self, role: SpecialistRole | str, path: str) -> bool:
        try:
            patterns = read_patterns_for_role(role)
            return bool(patterns and path_matches(path, patterns))
        except ValidationError:
            return False

    def ensure_read_path(self, role: SpecialistRole | str, path: str) -> None:
        value = role.value if isinstance(role, SpecialistRole) else str(role)
        if not self.can_read_path(role, path):
            raise WorkspacePermissionDenied(value, "读取 Workspace 文件", path)

    def can_write_path(self, role: SpecialistRole | str, path: str) -> bool:
        try:
            value = _normalize_role(role)
            if "write_file" not in tools_for_role(value):
                return False
            owner = path_owner(path)
            return owner == value or owner is SpecialistRole(value)
        except (ValidationError, ValueError):
            return False

    def can_project_path(self, role: SpecialistRole | str, path: str) -> bool:
        """Authorize deterministic service output without granting file tools."""

        try:
            value = _normalize_role(role)
            if value == CREATOR_ROLE:
                return False
            return path_owner(path) is SpecialistRole(value)
        except (ValidationError, ValueError):
            return False

    def ensure_project_path(
        self,
        role: SpecialistRole | str,
        path: str,
    ) -> None:
        value = role.value if isinstance(role, SpecialistRole) else str(role)
        if not self.can_project_path(role, path):
            raise WorkspacePermissionDenied(value, "投影 Runtime 服务结果", path)

    def ensure_write_path(self, role: SpecialistRole | str, path: str) -> None:
        value = role.value if isinstance(role, SpecialistRole) else str(role)
        if not self.can_write_path(role, path):
            raise WorkspacePermissionDenied(value, "写入 Workspace 文件", path)

    def ensure_run_write_path(
        self,
        role: SpecialistRole | str,
        path: str,
        *,
        specialist_run_id: str,
        target_ref: str,
    ) -> None:
        """Apply only static role ownership; per-Run Source isolation is disabled."""

        value = role.value if isinstance(role, SpecialistRole) else str(role)
        if value == SpecialistRole.SOURCE_INTELLIGENCE.value:
            normalized = workspace_text_path(path)
            if (
                path_owner(normalized)
                is not SpecialistRole.SOURCE_INTELLIGENCE
            ):
                raise WorkspacePermissionDenied(
                    value,
                    "写入 Workspace 文件",
                    normalized,
                )
            return
        self.ensure_write_path(role, path)


__all__ = [
    "CREATOR_ROLE",
    "FILE_TOOL_NAMES",
    "PermissionDenied",
    "PermissionRegistry",
    "READ_FILE_TOOLS",
    "ResolvedRolePermissions",
    "WRITE_FILE_TOOLS",
    "WorkspacePermissionDenied",
    "path_matches",
    "path_owner",
    "read_patterns_for_role",
    "resolve_role",
    "tools_for_role",
    "write_patterns_for_role",
]
