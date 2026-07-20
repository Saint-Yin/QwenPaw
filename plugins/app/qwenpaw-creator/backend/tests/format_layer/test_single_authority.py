from __future__ import annotations

from pathlib import Path

import pytest

from services.format_layer import (
    ProjectionInputError,
    TextWorkspaceSnapshot,
    WorkspaceFile,
    build_plan_view,
)

FORMAT_ROOT = Path(__file__).resolve().parents[2] / "services" / "format_layer"


def test_format_layer_has_no_old_authority_or_global_join_implementation():
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(FORMAT_ROOT.glob("*.py")))
    forbidden = (
        "services.workspace.assembly",
        "assemble_project",
        "decompose_project",
        "project_state.json",
        "schemas.api_models",
        "review" + "Status",
        "JSON Patch",
        "Merge Patch",
        "Production" + "Run",
        "Pro" + "posalStore",
        "ReferenceGraph",
        "canvas" + "es",
    )
    assert [token for token in forbidden if token in source] == []
    assert "from services.workspace" not in source


def test_missing_target_version_is_rejected_instead_of_invented(projection_fixture):
    fixture = projection_fixture
    snapshot = TextWorkspaceSnapshot(
        project_id=fixture.snapshot.project_id,
        revision_id=fixture.snapshot.revision_id,
        files=fixture.snapshot.files,
        target_versions={
            ref: version
            for ref, version in fixture.snapshot.target_versions.items()
            if ref != "unit:u-edit"
        },
    )
    with pytest.raises(ProjectionInputError, match="target version is missing: unit:u-edit"):
        build_plan_view(snapshot, fixture.catalogs)


def test_workspace_snapshot_only_accepts_documented_text_formats():
    with pytest.raises(ProjectionInputError, match="invalid Text Workspace path"):
        TextWorkspaceSnapshot(
            project_id="p1",
            revision_id="r1",
            files={"story/project.json": WorkspaceFile("{}", "ov-1")},
            target_versions={},
        )
