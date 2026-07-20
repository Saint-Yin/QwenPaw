from __future__ import annotations

import pytest

from domain.enums import SpecialistRole
from domain.errors import ConflictError
from services.specialists.registry import (
    SPECIALIST_REGISTRY,
    creator_delegatable_registry,
)
from services.workspace.file_tools import ReadSetAccumulator, ReadSetEntry
from services.workspace.permissions import (
    PermissionRegistry,
    WorkspacePermissionDenied,
    path_owner,
    resolve_role,
)

pytestmark = pytest.mark.unit


OWNED_PATH = {
    SpecialistRole.SOURCE_INTELLIGENCE: (
        "sources/source-1/understanding/versions/run-source/index.txt"
    ),
    SpecialistRole.STORY_PLANNING: "story/outline.md",
    SpecialistRole.VISUAL_DEVELOPMENT: "visual/style.md",
    SpecialistRole.UNIT_PLANNING_ROUTING: "story/sections/sec-1/units/unit-1/title.txt",
    SpecialistRole.R2V_GENERATION_DIRECTOR: "story/sections/sec-1/units/unit-1/production/r2v/prompt.md",
    SpecialistRole.AI_EDITING_DIRECTOR: "story/sections/sec-1/units/unit-1/production/edit/intent.md",
    SpecialistRole.REVIEW_CONSISTENCY: None,
}


@pytest.mark.parametrize(
    "path",
    [
        "story/sections/sec-1/title.txt",
        "story/sections/sec-1/duration-budget.txt",
    ],
)
def test_story_planning_owns_documented_section_scalar_fields(path: str) -> None:
    permissions = PermissionRegistry()
    assert permissions.can_write_path(SpecialistRole.STORY_PLANNING, path)
    assert path_owner(path) is SpecialistRole.STORY_PLANNING


@pytest.mark.parametrize("role", tuple(SPECIALIST_REGISTRY))
def test_every_role_rejects_an_unauthorized_project_content_write(
    role: SpecialistRole,
) -> None:
    permissions = PermissionRegistry()
    own = OWNED_PATH[role]
    foreign = "settings/brief.md"
    with pytest.raises(WorkspacePermissionDenied):
        permissions.ensure_write_path(role, foreign)

    resolved = resolve_role(role)
    if role in {
        SpecialistRole.SOURCE_INTELLIGENCE,
        SpecialistRole.AI_EDITING_DIRECTOR,
        SpecialistRole.REVIEW_CONSISTENCY,
    }:
        # AI Edit writes only via its deterministic service bridge; Review is
        # strictly read-only. Neither can enter a generic file write loop.
        assert not any(
            name in resolved.tools
            for name in ("write_file", "edit_file", "append_file")
        )
        if role is SpecialistRole.SOURCE_INTELLIGENCE:
            assert own is not None and path_owner(own) is role
            assert not permissions.can_write_path(role, own)
            assert permissions.can_project_path(role, own)
    else:
        assert own is not None and permissions.can_write_path(role, own)
        assert path_owner(own) is role


@pytest.mark.parametrize("role", tuple(SPECIALIST_REGISTRY))
def test_every_role_run_read_set_detects_same_locator_version_cas_change(
    role: SpecialistRole,
) -> None:
    # The accumulator is run-local but role-independent by design: all nine
    # roles, including read-only Review and service-backed AI Edit, must refuse
    # to reinterpret the same observed locator at a different version.
    assert role in SPECIALIST_REGISTRY
    accumulator = ReadSetAccumulator()
    first = ReadSetEntry(
        path="settings/project-title.txt",
        blob_hash="a" * 64,
        object_version=f"{role.value}:v1",
        view_kind="working",
        view_id="branch-1",
    )
    accumulator.record(first)
    accumulator.record(first)
    with pytest.raises(ConflictError, match="版本已变化"):
        accumulator.record(
            ReadSetEntry(
                path=first.path,
                blob_hash="b" * 64,
                object_version=f"{role.value}:v2",
                view_kind="working",
                view_id="branch-1",
            )
        )


def test_registry_keeps_historical_roles_but_exposes_only_active_specialists() -> None:
    assert len(SPECIALIST_REGISTRY) == 7
    assert set(creator_delegatable_registry()) == {
        SpecialistRole.SOURCE_INTELLIGENCE,
        SpecialistRole.VISUAL_DEVELOPMENT,
        SpecialistRole.R2V_GENERATION_DIRECTOR,
        SpecialistRole.AI_EDITING_DIRECTOR,
    }
    values = {item.value for item in SpecialistRole}
    assert not values & {
        "script_agent",
        "storyboard_agent",
        "style_guide_agent",
        "asset_planning_agent",
        "video_prompt_agent",
        "creator_" + "main_agent",
    }
