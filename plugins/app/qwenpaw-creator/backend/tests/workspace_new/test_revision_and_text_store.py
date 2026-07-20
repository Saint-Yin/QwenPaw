from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from domain.errors import ConflictError, ValidationError
from services.workspace.revision_store import RevisionKind
from services.workspace.text_store import UNSET_EXPECTATION


pytestmark = pytest.mark.unit


INITIAL_FILES = {
    "title.txt": "初始标题",
    "description.md": "初始描述",
    "story/sections/001000--sec-1--opening/title.txt": "开场",
    "story/sections/001000--sec-1--opening/units/001000--unit-1--shot/route.txt": "r2v",
    "story/sections/001000--sec-1--opening/units/001000--unit-1--shot/refs/scene.ref": "asset://scene-a@scene-v1",
}


def test_initial_approved_revision_is_idempotent_immutable_and_persistent(workspace_stack):
    first = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=INITIAL_FILES
    )
    second = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=dict(reversed(list(INITIAL_FILES.items())))
    )

    assert first.id == second.id
    assert first.kind is RevisionKind.APPROVED
    assert first.tree_hash == second.tree_hash
    assert workspace_stack.revisions.get_approved("project-1") == first
    assert [entry.path for entry in first.entries] == sorted(INITIAL_FILES)

    with pytest.raises(FrozenInstanceError):
        first.tree_hash = "0" * 64
    with pytest.raises(FrozenInstanceError):
        first.entries[0].blob_hash = "0" * 64

    with pytest.raises(ConflictError, match="different|不同"):
        workspace_stack.revisions.create_initial_approved_revision(
            project_id="project-1", files={**INITIAL_FILES, "title.txt": "另一个初始值"}
        )


def test_same_entry_tree_has_same_hash_across_distinct_revisions(workspace_stack):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=INITIAL_FILES
    )
    one = workspace_stack.revisions.create_revision(
        project_id="project-1",
        kind=RevisionKind.REVIEW,
        entries=initial.entries,
        parent_revision_id=initial.id,
    )
    two = workspace_stack.revisions.create_revision(
        project_id="project-1",
        kind=RevisionKind.REVIEW,
        entries=reversed(initial.entries),
        parent_revision_id=initial.id,
    )

    assert one.id != two.id
    assert one.manifest_hash != two.manifest_hash
    assert one.tree_hash == two.tree_hash == initial.tree_hash


def test_immutable_revision_id_cannot_be_overwritten(workspace_stack):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=INITIAL_FILES
    )
    changed_entries = workspace_stack.revisions.entries_from_files({"title.txt": "changed"})

    with pytest.raises(ConflictError, match="immutable revision"):
        workspace_stack.revisions.create_revision(
            project_id="project-1",
            kind=RevisionKind.APPROVED,
            entries=changed_entries,
            revision_id=initial.id,
        )

    assert workspace_stack.revisions.get("project-1", initial.id) == initial


def test_working_tree_reads_and_writes_only_through_blob_mapping(workspace_stack):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=INITIAL_FILES
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1", base_revision_id=initial.id, branch_id="branch-1"
    )
    initial_title = initial.entry_map()["title.txt"]

    updated = workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path="title.txt",
        text="新标题",
        expected_head=branch.head,
        expected_blob_hash=initial_title.blob_hash,
    )
    assert updated.changed is True
    assert updated.kind.value == "update"
    assert updated.after_entry.blob_hash != initial_title.blob_hash
    assert workspace_stack.text.read_text(
        "project-1", "title.txt", branch_id=branch.id
    ) == "新标题"
    # The immutable base revision remains unchanged.
    assert workspace_stack.text.read_text(
        "project-1", "title.txt", revision_id=initial.id
    ) == "初始标题"

    created = workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path="strategy/creative-brief.md",
        text="新策略",
        expected_blob_hash=None,
    )
    assert created.kind.value == "create"
    moved = workspace_stack.text.move(
        project_id="project-1",
        branch_id=branch.id,
        source_path="strategy/creative-brief.md",
        destination_path="strategy/archive/creative-brief.md",
        expected_source_blob_hash=created.after_entry.blob_hash,
    )
    assert moved.kind.value == "move"
    deleted = workspace_stack.text.delete(
        project_id="project-1",
        branch_id=branch.id,
        path="description.md",
        expected_blob_hash=initial.entry_map()["description.md"].blob_hash,
    )
    assert deleted.kind.value == "delete"

    sealed = workspace_stack.text.seal_revision(
        project_id="project-1",
        branch_id=branch.id,
        kind=RevisionKind.REVIEW,
    )
    current_branch = workspace_stack.text.get_working_tree("project-1", branch.id)
    assert sealed.tree_hash == current_branch.tree_hash
    assert sealed.parent_revision_id == initial.id

    branch_metadata = next(
        (workspace_stack.content.root / "working-tree-store").rglob("branch-1.json")
    )
    metadata_text = branch_metadata.read_text(encoding="utf-8")
    assert "新标题" not in metadata_text
    assert "新策略" not in metadata_text
    payload = json.loads(metadata_text)
    assert all("blobHash" in entry and "text" not in entry for entry in payload["entries"])
    assert not (workspace_stack.content.root / "project-workspaces").exists()


def test_stale_head_or_target_version_cannot_overwrite_new_value(workspace_stack):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files={"title.txt": "v1"}
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1", base_revision_id=initial.id, branch_id="branch-1"
    )
    v1_hash = initial.entries[0].blob_hash
    first = workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path="title.txt",
        text="v2",
        expected_head=branch.head,
        expected_blob_hash=v1_hash,
    )

    with pytest.raises(ConflictError, match="target blob CAS"):
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="title.txt",
            text="stale target write",
            expected_blob_hash=v1_hash,
        )
    with pytest.raises(ConflictError, match="working head"):
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="description.md",
            text="stale head write",
            expected_head=branch.head,
            expected_blob_hash=None,
        )

    current = workspace_stack.text.get_working_tree("project-1", branch.id)
    assert current.head == first.working_tree.head
    assert workspace_stack.text.read_text(
        "project-1", "title.txt", branch_id=branch.id
    ) == "v2"


def test_failed_branch_metadata_publish_keeps_previous_authoritative_head(
    workspace_stack, monkeypatch
):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files={"title.txt": "before"}
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1", base_revision_id=initial.id, branch_id="branch-1"
    )

    def fail_before_replace(*args, **kwargs):
        raise OSError("simulated metadata fsync/rename failure")

    monkeypatch.setattr(
        "services.workspace.text_store.atomic_replace_bytes", fail_before_replace
    )
    with pytest.raises(OSError, match="simulated"):
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="title.txt",
            text="must not become current",
        )

    restored = workspace_stack.text.get_working_tree("project-1", branch.id)
    assert restored.head == branch.head
    assert workspace_stack.text.read_text(
        "project-1", "title.txt", branch_id=branch.id
    ) == "before"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        "/etc/passwd",
        "../title.txt",
        "story/../../title.txt",
        "story/./title.txt",
        "story//title.txt",
        "story\\title.txt",
        "C:\\temp\\title.txt",
        "title.txt/",
        " title.txt",
    ],
)
def test_workspace_path_escape_is_rejected(workspace_stack, unsafe_path):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files={"title.txt": "safe"}
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1", base_revision_id=initial.id, branch_id="branch-1"
    )
    with pytest.raises(ValidationError, match="workspace path"):
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path=unsafe_path,
            text="escape",
            expected_blob_hash=UNSET_EXPECTATION,
        )


@pytest.mark.parametrize(
    ("path", "text", "message"),
    [
        ("state.json", "{}", "只允许"),
        ("brief.md", "---\ntitle: hidden\n---\nbody", "frontmatter"),
        ("scene.ref", "asset://scene@v1\n", "单行"),
        ("scene.ref", "../asset", "workspace ref"),
    ],
)
def test_text_workspace_format_rules_are_enforced(workspace_stack, path, text, message):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files={}
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1", base_revision_id=initial.id, branch_id="branch-1"
    )
    with pytest.raises(ValidationError, match=message):
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path=path,
            text=text,
        )
