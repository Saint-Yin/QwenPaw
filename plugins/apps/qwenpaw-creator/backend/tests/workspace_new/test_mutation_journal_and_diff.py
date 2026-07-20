# -*- coding: utf-8 -*-
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from domain.errors import ConflictError, StorageIntegrityError
from services.workspace.diff_service import DiffService
from services.workspace.mutation_journal import MutationJournal
from services.workspace.mutations import (
    MutationActor,
    MutationKind,
    new_mutation,
)


pytestmark = pytest.mark.unit


BASE_FILES = {
    "update.txt": "before update",
    "delete.md": "delete me",
    "move/old.txt": "move identity",
    "rename/old.txt": "rename identity",
    "refs/story.ref": "project://unit/unit-1",
    "refs/media.ref": "asset://video-a@asset-v1",
}


def _record_for_result(result, *, target_ref: str):
    if result.kind in {MutationKind.MOVE, MutationKind.RENAME}:
        return new_mutation(
            project_id="project-1",
            transaction_id="tx-1",
            actor=MutationActor.SUBAGENT,
            kind=result.kind,
            target_ref=target_ref,
            source_path=result.source_path,
            destination_path=result.destination_path,
            before_blob_hash=result.before_entry.blob_hash,
            after_blob_hash=result.after_entry.blob_hash,
        )
    path = result.destination_path or result.source_path
    return new_mutation(
        project_id="project-1",
        transaction_id="tx-1",
        actor=MutationActor.SUBAGENT,
        kind=result.kind,
        target_ref=target_ref,
        path=path,
        before_blob_hash=(
            result.before_entry.blob_hash if result.before_entry else None
        ),
        after_blob_hash=(
            result.after_entry.blob_hash if result.after_entry else None
        ),
    )


def test_typed_journal_and_full_tree_diff_cover_every_change_kind(
    workspace_stack,
):
    base = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files=BASE_FILES,
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=base.id,
        branch_id="branch-1",
    )

    results = [
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="create.md",
            text="created",
            expected_blob_hash=None,
        ),
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="update.txt",
            text="after update",
        ),
        workspace_stack.text.delete(
            project_id="project-1",
            branch_id=branch.id,
            path="delete.md",
        ),
        workspace_stack.text.move(
            project_id="project-1",
            branch_id=branch.id,
            source_path="move/old.txt",
            destination_path="archive/moved.txt",
        ),
        workspace_stack.text.move(
            project_id="project-1",
            branch_id=branch.id,
            source_path="rename/old.txt",
            destination_path="rename/new.txt",
        ),
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="refs/story.ref",
            text="project://unit/unit-2",
        ),
        workspace_stack.text.write_text(
            project_id="project-1",
            branch_id=branch.id,
            path="refs/media.ref",
            text="artifact://unit-video@artifact-v2",
        ),
    ]
    assert [result.kind for result in results] == [
        MutationKind.CREATE,
        MutationKind.UPDATE,
        MutationKind.DELETE,
        MutationKind.MOVE,
        MutationKind.RENAME,
        MutationKind.CHANGE_REFERENCE,
        MutationKind.REPLACE_MEDIA,
    ]

    journal = MutationJournal(workspace_stack.content.root)
    drafts = tuple(
        _record_for_result(result, target_ref=f"path:{index}")
        for index, result in enumerate(results, 1)
    )
    records = journal.append_many(drafts, expected_last_seq=0)

    assert [record.seq for record in records] == list(range(1, 8))
    assert journal.seq_range("project-1", "tx-1") == (1, 7)
    assert journal.records("project-1", "tx-1", after_seq=4) == records[4:]

    # Replaying the exact same mutation id is idempotent.
    assert journal.append(records[0]) == records[0]
    with pytest.raises(ConflictError, match="payload 不同"):
        journal.append(replace(records[0], target_ref="different-target"))

    reloaded = MutationJournal(workspace_stack.content.root)
    assert reloaded.records("project-1", "tx-1") == records

    target = workspace_stack.text.get_working_tree("project-1", branch.id)
    diff = DiffService(workspace_stack.content).compare(
        base,
        target,
        journal=records,
    )

    assert {operation.kind for operation in diff.operations} == {
        MutationKind.CREATE,
        MutationKind.UPDATE,
        MutationKind.DELETE,
        MutationKind.MOVE,
        MutationKind.RENAME,
        MutationKind.CHANGE_REFERENCE,
        MutationKind.REPLACE_MEDIA,
    }
    assert len(diff.operations) == 7
    assert DiffService.unjournaled_paths(diff) == ()

    by_kind = {operation.kind: operation for operation in diff.operations}
    assert by_kind[MutationKind.MOVE].source_path == "move/old.txt"
    assert by_kind[MutationKind.MOVE].destination_path == "archive/moved.txt"
    assert by_kind[MutationKind.RENAME].source_path == "rename/old.txt"
    assert by_kind[MutationKind.RENAME].destination_path == "rename/new.txt"
    assert (
        by_kind[MutationKind.CHANGE_REFERENCE].before_ref
        == "project://unit/unit-1"
    )
    assert (
        by_kind[MutationKind.CHANGE_REFERENCE].after_ref
        == "project://unit/unit-2"
    )
    assert (
        by_kind[MutationKind.REPLACE_MEDIA].before_ref
        == "asset://video-a@asset-v1"
    )
    assert (
        by_kind[MutationKind.REPLACE_MEDIA].after_ref
        == "artifact://unit-video@artifact-v2"
    )
    assert all(operation.mutation_ids for operation in diff.operations)


def test_full_tree_diff_exposes_unjournaled_real_change(workspace_stack):
    base = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files={"title.txt": "before"},
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=base.id,
        branch_id="branch-1",
    )
    workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path="title.txt",
        text="after without journal",
    )

    target = workspace_stack.text.get_working_tree("project-1", branch.id)
    diff = DiffService(workspace_stack.content).compare(base, target)

    assert len(diff.operations) == 1
    assert diff.operations[0].kind is MutationKind.UPDATE
    assert DiffService.unjournaled_paths(diff) == ("title.txt",)


def test_journal_hash_detects_private_metadata_tampering(workspace_stack):
    initial = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1",
        files={"title.txt": "before"},
    )
    branch = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=initial.id,
        branch_id="branch-1",
    )
    result = workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=branch.id,
        path="title.txt",
        text="after",
    )
    journal = MutationJournal(workspace_stack.content.root)
    journal.append(_record_for_result(result, target_ref="project:title"))

    path = next(
        (workspace_stack.content.root / "mutation-journal").rglob("tx-1.json"),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0]["targetRef"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StorageIntegrityError, match="Journal hash"):
        journal.records("project-1", "tx-1")
