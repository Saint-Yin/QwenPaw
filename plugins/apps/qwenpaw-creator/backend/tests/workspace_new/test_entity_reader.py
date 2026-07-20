# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

import pytest

from domain.errors import ValidationError


pytestmark = pytest.mark.unit


def test_entity_reader_reads_ordered_and_plain_entities_without_raw_io(
    workspace_stack,
):
    files = {
        "story/sections/001000--sec-1--opening/title.txt": "开场",
        "story/sections/001000--sec-1--opening/narrative.md": "建立故事",
        "story/sections/001000--sec-1--opening/units/001000--unit-1--shot/title.txt": "镜头一",
        "story/sections/002000--sec-2--ending/title.txt": "结尾",
        "sources/asset-1--source-video/user-notes.md": "用户素材",
        "sources/asset-1--source-video/selected-version.ref": "asset://asset-1@asset-v1",
    }
    revision = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files=files,
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=revision.id,
        branch_id="branch-1",
    )

    sections = workspace_stack.entities.list_entities(
        "project-1",
        "story/sections",
        ordered=True,
        branch_id=branch.id,
    )
    assert [(item.id, item.order, item.slug) for item in sections] == [
        ("sec-1", 1000, "opening"),
        ("sec-2", 2000, "ending"),
    ]
    section = workspace_stack.entities.read_entity(
        "project-1",
        "story/sections",
        "sec-1",
        ordered=True,
        branch_id=branch.id,
    )
    assert section.file_map()["title.txt"].text == "开场"
    assert section.file_map()["narrative.md"].text == "建立故事"
    assert (
        section.file_map()["units/001000--unit-1--shot/title.txt"].text
        == "镜头一"
    )

    sources = workspace_stack.entities.list_entities(
        "project-1",
        "sources",
        ordered=False,
        revision_id=revision.id,
    )
    assert [(item.id, item.order, item.slug) for item in sources] == [
        ("asset-1", None, "source-video"),
    ]
    assert (
        workspace_stack.entities.read_ref(
            "project-1",
            "sources/asset-1--source-video/selected-version.ref",
            revision_id=revision.id,
        )
        == "asset://asset-1@asset-v1"
    )


def test_entity_reader_keeps_revision_snapshot_isolated_from_working_change(
    workspace_stack,
):
    revision = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files={"story/sections/001000--sec-1--opening/title.txt": "旧标题"},
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=revision.id,
        branch_id="branch-1",
    )
    path = "story/sections/001000--sec-1--opening/title.txt"
    workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path=path,
        text="Working 标题",
    )

    assert (
        workspace_stack.entities.read_text(
            "project-1",
            path,
            branch_id=branch.id,
        )
        == "Working 标题"
    )
    assert (
        workspace_stack.entities.read_text(
            "project-1",
            path,
            revision_id=revision.id,
        )
        == "旧标题"
    )


def test_entity_reader_rejects_path_escape_and_ambiguous_snapshot_selector(
    workspace_stack,
):
    revision = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files={"title.txt": "safe"},
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=revision.id,
        branch_id="branch-1",
    )

    with pytest.raises(ValidationError, match="workspace path"):
        workspace_stack.entities.read_text(
            "project-1",
            "../title.txt",
            branch_id=branch.id,
        )
    with pytest.raises(ValidationError, match="只能指定"):
        workspace_stack.entities.read_text(
            "project-1",
            "title.txt",
            branch_id=branch.id,
            revision_id=revision.id,
        )
