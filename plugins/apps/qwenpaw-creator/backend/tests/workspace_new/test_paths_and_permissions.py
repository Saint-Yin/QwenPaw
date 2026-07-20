# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

import pytest

from domain.enums import SpecialistRole
from domain.errors import ValidationError
from services.specialists.registry import SPECIALIST_REGISTRY
from services.workspace.paths import (
    glob_matches,
    scope_contains_path,
    scopes_overlap,
    workspace_directory,
    workspace_glob,
    workspace_text_path,
)
from services.workspace.permissions import (
    CREATOR_ROLE,
    FILE_TOOL_NAMES,
    PermissionRegistry,
    READ_FILE_TOOLS,
    path_owner,
    tools_for_role,
    write_patterns_for_role,
)
import services.workspace.permissions as permissions_module


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path",
    [
        "strategy/creative-brief.md",
        "settings/platform.txt",
        "sources/asset-1/understanding/versions/a1/transcript.vtt",
        "sources/asset-1/understanding/versions/a1/transcript-words.ctm",
        "visual/characters/c1/selected.ref",
    ],
)
def test_folder_first_text_paths_accept_only_five_formats(path):
    assert workspace_text_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../strategy/brief.md",
        "strategy/../../etc/passwd",
        "strategy/./brief.md",
        "strategy//brief.md",
        "strategy\\brief.md",
        "C:\\temp\\brief.md",
        "strategy/state.json",
        "strategy/brief.yaml",
        "strategy/.secret.md",
        "runs/run-1/output.md",
        "blobs/aa/content.txt",
    ],
)
def test_workspace_path_escape_private_roots_and_non_text_authority_are_rejected(
    path,
):
    with pytest.raises(ValidationError):
        workspace_text_path(path)


@pytest.mark.parametrize(
    "pattern",
    ["/story/**", "../story/**", "story/../**", "story\\**", "C:\\story\\**"],
)
def test_unsafe_search_globs_are_rejected(pattern):
    with pytest.raises(ValidationError):
        workspace_glob(pattern)


def test_workspace_glob_has_segment_aware_double_star_semantics():
    assert glob_matches("outline.md", "**/*.md")
    assert glob_matches("story/outline.md", "**/*.md")
    assert glob_matches("story/sections/s1/script.md", "story/**/script.md")
    assert not glob_matches(
        "story/sections/s1/script.txt",
        "story/**/script.md",
    )


def test_scoped_leases_are_explicit_and_hierarchical():
    target = "story/sections/s1/units/u1/route.txt"
    assert scope_contains_path("story/sections/s1/units/u1/**", target)
    assert scope_contains_path(target, target)
    assert not scope_contains_path("story/sections/s1/units/u2/**", target)
    assert scopes_overlap("visual/**", "visual/characters/**")
    assert scopes_overlap("visual/**", "visual/style.md")
    assert not scopes_overlap("visual/**", "strategy/**")
    assert workspace_directory("story/sections") == "story/sections"


def test_exact_seven_tool_names_and_role_filtered_manifests():
    assert FILE_TOOL_NAMES == (
        "read_file",
        "write_file",
        "edit_file",
        "append_file",
        "grep_search",
        "glob_search",
        "ast_search",
    )
    assert set(tools_for_role(CREATOR_ROLE)) == set(FILE_TOOL_NAMES)
    assert tools_for_role(SpecialistRole.REVIEW_CONSISTENCY) == READ_FILE_TOOLS
    assert tools_for_role(SpecialistRole.AI_EDITING_DIRECTOR) == ()
    assert tools_for_role(SpecialistRole.SOURCE_INTELLIGENCE) == ()
    for role in set(SPECIALIST_REGISTRY) - {
        SpecialistRole.REVIEW_CONSISTENCY,
        SpecialistRole.AI_EDITING_DIRECTOR,
        SpecialistRole.SOURCE_INTELLIGENCE,
    }:
        assert set(tools_for_role(role)) == set(FILE_TOOL_NAMES)


def test_permissions_module_has_no_second_role_scope_mapping() -> None:
    assert not hasattr(permissions_module, "ROLE_WRITE_PATHS")
    assert not hasattr(permissions_module, "ROLE_READ_PATHS")


@pytest.mark.parametrize(
    ("path", "owner"),
    [
        ("settings/platform.txt", CREATOR_ROLE),
        ("strategy/creative-brief.md", CREATOR_ROLE),
        (
            "sources/a/understanding/versions/v1/summary.md",
            SpecialistRole.SOURCE_INTELLIGENCE,
        ),
        ("story/outline.md", SpecialistRole.STORY_PLANNING),
        ("story/sections/s1/script.md", SpecialistRole.STORY_PLANNING),
        ("visual/style.md", SpecialistRole.VISUAL_DEVELOPMENT),
        (
            "story/sections/s1/units/u1/route.txt",
            SpecialistRole.UNIT_PLANNING_ROUTING,
        ),
        (
            "story/sections/s1/units/u1/shots/sh1/camera.md",
            SpecialistRole.UNIT_PLANNING_ROUTING,
        ),
        (
            "story/sections/s1/units/u1/production/r2v/video/prompt.md",
            SpecialistRole.R2V_GENERATION_DIRECTOR,
        ),
        (
            "story/sections/s1/units/u1/production/edit/intent.md",
            SpecialistRole.AI_EDITING_DIRECTOR,
        ),
        ("post/final/rendered-video.ref", CREATOR_ROLE),
    ],
)
def test_each_domain_file_has_one_exact_role_owner(path, owner):
    registry = PermissionRegistry()
    assert path_owner(path) == owner
    if owner == CREATOR_ROLE:
        assert registry.can_write_path(CREATOR_ROLE, path)
        assert not any(
            registry.can_write_path(role, path) for role in SpecialistRole
        )
        return
    allowed = [
        role for role in SpecialistRole if registry.can_write_path(role, path)
    ]
    if owner in {
        SpecialistRole.SOURCE_INTELLIGENCE,
        SpecialistRole.AI_EDITING_DIRECTOR,
    }:
        # Source publishes one Runtime-owned immutable projection and AI Edit
        # writes through its deterministic service bridge.  Neither model has
        # a generic file-write loop, while the role still owns the projection.
        assert allowed == []
        assert registry.can_project_path(owner, path)
        assert not registry.can_project_path(
            SpecialistRole.R2V_GENERATION_DIRECTOR,
            path,
        )
    else:
        assert allowed == [owner]


def test_unit_planning_does_not_gain_r2v_story_or_section_wide_writes():
    registry = PermissionRegistry()
    role = SpecialistRole.UNIT_PLANNING_ROUTING
    assert registry.can_write_path(
        role,
        "story/sections/s1/units/u1/route.txt",
    )
    assert not registry.can_write_path(
        role,
        "story/sections/s1/units/u1/production/r2v/video/prompt.md",
    )
    assert not registry.can_write_path(role, "story/sections/s1/script.md")
    assert not registry.can_write_path(role, "story/outline.md")


@pytest.mark.parametrize(
    ("role", "path"),
    [
        (
            SpecialistRole.SOURCE_INTELLIGENCE,
            "sources/a/understanding/private-notes.md",
        ),
        (SpecialistRole.STORY_PLANNING, "story/sections/s1/arbitrary.md"),
        (
            SpecialistRole.UNIT_PLANNING_ROUTING,
            "story/sections/s1/units/u1/arbitrary.md",
        ),
    ],
)
def test_registry_scopes_keep_previously_broader_paths_forbidden(role, path):
    registry = PermissionRegistry()
    assert path_owner(path) is not role
    assert not registry.can_write_path(role, path)


def test_unit_shot_owner_and_prompt_manifest_share_the_same_dto_leaf_set():
    role = SpecialistRole.UNIT_PLANNING_ROUTING
    root = "story/sections/s1/units/u1/shots/sh1"
    expected_leaves = (
        "description.md",
        "camera.md",
        "dialogue.md",
        "duration.txt",
    )
    patterns = set(write_patterns_for_role(role))
    shot_pattern_prefix = "story/sections/*/units/*/shots/*/"

    for leaf in expected_leaves:
        path = f"{root}/{leaf}"
        assert path_owner(path) is role
        assert f"{shot_pattern_prefix}{leaf}" in patterns

    assert {
        pattern.removeprefix(shot_pattern_prefix)
        for pattern in patterns
        if pattern.startswith(shot_pattern_prefix)
    } == set(expected_leaves)

    assert path_owner(f"{root}/notes.md") is None
    assert f"{shot_pattern_prefix}notes.md" not in patterns


def test_unknown_roles_are_never_permitted():
    registry = PermissionRegistry()
    assert not registry.is_known_role("unknown_agent")
    assert not registry.can_read_path("unknown_agent", "story/outline.md")
    assert not registry.can_write_path("unknown_agent", "story/outline.md")
