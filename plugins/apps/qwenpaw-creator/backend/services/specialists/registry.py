# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""The only specialist role, permission, prompt and delegate registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from domain.enums import SpecialistRole
from domain.errors import ValidationError
from domain.refs import parse_target_ref

READ_FILE_TOOLS = ("read_file", "grep_search", "glob_search", "ast_search")
WRITE_FILE_TOOLS = ("write_file", "edit_file", "append_file")
DELEGATE_TOOL_NAME = "delegate_to_agent"
FINALIZE_VIDEO_TOOL_NAME = "finalize_video"


@dataclass(frozen=True, slots=True)
class SpecialistSpec:
    role: SpecialistRole
    display_name: str
    runner_type: Literal["llm_backed", "hybrid", "service_backed"]
    prompt_spec_id: str | None
    read_scopes: tuple[str, ...]
    write_scopes: tuple[str, ...]
    allowed_file_tools: tuple[str, ...]
    multimodal_kinds: tuple[str, ...]
    delegate_target_kinds: tuple[str, ...]
    delegate_target_guidance: str
    delegate_project_targets: tuple[str, ...] = ()
    allow_project_id_target: bool = False
    terminal_protocol: str = "specialist_marker_text.v1"


def _writable(
    role: SpecialistRole,
    display_name: str,
    runner_type: Literal["llm_backed", "hybrid"],
    prompt: str | None,
    read: tuple[str, ...],
    write: tuple[str, ...],
    target_kinds: tuple[str, ...],
    target_guidance: str,
    project_targets: tuple[str, ...] = (),
    allow_project_id_target: bool = False,
    media: tuple[str, ...] = (),
    file_tools: tuple[str, ...] = READ_FILE_TOOLS + WRITE_FILE_TOOLS,
) -> SpecialistSpec:
    return SpecialistSpec(
        role=role,
        display_name=display_name,
        runner_type=runner_type,
        prompt_spec_id=prompt,
        read_scopes=read,
        write_scopes=write,
        allowed_file_tools=file_tools,
        multimodal_kinds=media,
        delegate_target_kinds=target_kinds,
        delegate_target_guidance=target_guidance,
        delegate_project_targets=project_targets,
        allow_project_id_target=allow_project_id_target,
    )


_SPECS = (
    _writable(
        SpecialistRole.SOURCE_INTELLIGENCE,
        "素材理解",
        "llm_backed",
        "source_intelligence.system",
        ("sources/**",),
        (
            "sources/*/understanding/versions/**",
            "sources/*/understanding/current.ref",
        ),
        ("asset",),
        "asset:<logicalAssetId>",
        media=("image", "video"),
        file_tools=(),
    ),
    _writable(
        SpecialistRole.STORY_PLANNING,
        "故事规划",
        "llm_backed",
        None,
        ("settings/**", "strategy/**", "sources/**", "story/**"),
        (
            "story/outline.md",
            "story/sections/*/title.txt",
            "story/sections/*/narrative.md",
            "story/sections/*/script.md",
            "story/sections/*/constraints.md",
            "story/sections/*/duration-budget.txt",
            "story/sections/*/source-analysis.ref",
        ),
        ("project", "section"),
        "新建/整体故事用 project:plan；已有单节修改用 section:<id>",
        project_targets=("plan",),
        media=("image", "video", "document"),
    ),
    _writable(
        SpecialistRole.VISUAL_DEVELOPMENT,
        "视觉开发",
        "llm_backed",
        "visual_development.system",
        ("settings/**", "strategy/**", "sources/**", "story/**", "visual/**"),
        ("visual/**",),
        ("project", "section", "unit", "asset", "artifact"),
        (
            "整体视觉用 project:assets；局部视觉用 section:<id>、unit:<id>、"
            "asset:<logicalId> 或 artifact:<slotId>"
        ),
        project_targets=("assets",),
        media=("image", "video"),
    ),
    _writable(
        SpecialistRole.UNIT_PLANNING_ROUTING,
        "Unit 规划",
        "llm_backed",
        None,
        ("strategy/**", "sources/**", "visual/**", "story/**"),
        (
            "story/sections/*/units/*/title.txt",
            "story/sections/*/units/*/route.txt",
            "story/sections/*/units/*/duration.txt",
            "story/sections/*/units/*/continuity.md",
            "story/sections/*/units/*/refs/*.ref",
            "story/sections/*/units/*/refs/*/*.ref",
            "story/sections/*/units/*/shots/*/description.md",
            "story/sections/*/units/*/shots/*/camera.md",
            "story/sections/*/units/*/shots/*/dialogue.md",
            "story/sections/*/units/*/shots/*/duration.txt",
        ),
        ("section", "unit"),
        "必须指向已存在的 section:<id> 或 unit:<id>；Section 尚未建立时先等待故事规划",
        media=("image", "video"),
    ),
    _writable(
        SpecialistRole.R2V_GENERATION_DIRECTOR,
        "R2V 生成导演",
        "hybrid",
        "r2v_generation.system",
        ("strategy/**", "visual/**", "story/sections/*/units/**"),
        ("story/sections/*/units/*/production/r2v/**",),
        ("unit",),
        "unit:<id>（该 Unit route 必须是 r2v）",
        media=("image", "video"),
    ),
    SpecialistSpec(
        role=SpecialistRole.AI_EDITING_DIRECTOR,
        display_name="AI 剪辑导演",
        runner_type="service_backed",
        prompt_spec_id=None,
        read_scopes=("sources/**", "story/sections/*/units/**"),
        write_scopes=("story/sections/*/units/*/production/edit/**",),
        allowed_file_tools=(),
        # The durable executor reads local media, but the Director's model
        # receives only versioned Source Intelligence text candidates.
        multimodal_kinds=(),
        delegate_target_kinds=("unit",),
        delegate_target_guidance="unit:<id>（该 Unit route 必须是 edit）",
    ),
    SpecialistSpec(
        role=SpecialistRole.REVIEW_CONSISTENCY,
        display_name="一致性质检",
        runner_type="llm_backed",
        prompt_spec_id=None,
        read_scopes=("**",),
        write_scopes=(),
        allowed_file_tools=READ_FILE_TOOLS,
        multimodal_kinds=("image", "video", "audio", "document"),
        delegate_target_kinds=("project", "section", "unit", "post"),
        delegate_target_guidance=(
            "project:<projectId from CREATOR_RUNTIME_CONTEXT>、project:plan 或具体 "
            "section/unit/post ref"
        ),
        delegate_project_targets=("plan",),
        allow_project_id_target=True,
    ),
)

SPECIALIST_REGISTRY: dict[SpecialistRole, SpecialistSpec] = {
    spec.role: spec for spec in _SPECS
}

# Retired planning roles remain readable in historical Runtime records, but new
# Creator runs author their fields directly. Review is likewise unavailable.
CREATOR_DISABLED_DELEGATE_ROLES = frozenset(
    {
        SpecialistRole.STORY_PLANNING,
        SpecialistRole.UNIT_PLANNING_ROUTING,
        SpecialistRole.REVIEW_CONSISTENCY,
    },
)


def creator_delegatable_registry() -> dict[SpecialistRole, SpecialistSpec]:
    return {
        role: spec
        for role, spec in SPECIALIST_REGISTRY.items()
        if role not in CREATOR_DISABLED_DELEGATE_ROLES
    }


if len(SPECIALIST_REGISTRY) != 7:  # import-time invariant
    raise RuntimeError("Specialist registry must contain exactly seven roles")


def delegate_registry() -> dict[SpecialistRole, SpecialistSpec]:
    """Return the currently enabled Creator delegate targets.

    A role is data selected by ``delegate_to_agent(role=...)``; it is not a
    separately named tool.  Keeping the role registry distinct from the tool
    registry prevents AgentDock and provider manifests from presenting many
    copies of the same control capability.
    """

    return creator_delegatable_registry()


def creator_delegate_arguments_schema() -> dict[str, Any]:
    """Build the one Creator delegate schema from the role registry."""

    return {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": [
                    spec.role.value
                    for spec in creator_delegatable_registry().values()
                ],
            },
            "target_refs": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
                "description": "每个 ref 必须符合所选 role 的 Registry target contract",
            },
            "task": {
                "type": "string",
                "minLength": 1,
                "description": "面向专业角色的完整自然语言委派",
            },
        },
        "required": ["role", "target_refs", "task"],
        "additionalProperties": False,
    }


def creator_delegate_role_contracts() -> tuple[dict[str, Any], ...]:
    """Project Registry target rules into the Creator model-visible manifest."""

    return tuple(
        {
            "role": spec.role.value,
            "targetGuidance": spec.delegate_target_guidance,
            "allowedTargetKinds": list(spec.delegate_target_kinds),
            "allowedProjectTargets": list(spec.delegate_project_targets),
            "allowProjectIdTarget": spec.allow_project_id_target,
            "writeScopes": list(spec.write_scopes),
        }
        for spec in creator_delegatable_registry().values()
    )


def creator_can_delegate(role: SpecialistRole) -> bool:
    return role in creator_delegatable_registry()


def validate_delegate_targets(
    spec: SpecialistSpec,
    *,
    project_id: str,
    target_refs: tuple[str, ...],
) -> None:
    """Reject role/target mismatches before a SpecialistRun is accepted."""

    if not target_refs:
        raise ValidationError("Specialist delegate 至少需要一个 target ref")
    for target_ref in target_refs:
        parsed = parse_target_ref(target_ref)
        allowed = parsed.kind in spec.delegate_target_kinds
        if allowed and parsed.kind == "project":
            allowed = parsed.identifier in spec.delegate_project_targets or (
                spec.allow_project_id_target
                and parsed.identifier == project_id
            )
        if not allowed:
            raise ValidationError(
                f"{spec.role.value} 不允许委派到 targetRef {target_ref}",
                details={
                    "role": spec.role.value,
                    "targetRef": target_ref,
                    "allowedTargetKinds": list(spec.delegate_target_kinds),
                    "allowedProjectTargets": list(
                        spec.delegate_project_targets,
                    ),
                    "allowProjectIdTarget": spec.allow_project_id_target,
                },
            )


def creator_available_actions() -> tuple[str, ...]:
    return (
        "plan",
        "final",
        *READ_FILE_TOOLS,
        *WRITE_FILE_TOOLS,
        DELEGATE_TOOL_NAME,
        FINALIZE_VIDEO_TOOL_NAME,
        "yield_until_runtime_event",
        "complete_current_change",
    )
