from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import pytest

from domain.enums import SpecialistRole, TransactionStatus
from domain.errors import (
    ConflictError,
    PhaseConflictError,
    ValidationError,
)
from services.workspace.file_tools import (
    CommittedWorkspaceMutation,
    RuntimeWriteState,
    TextWriteRequest,
    WorkspaceFileTools,
    WorkspaceToolContext,
)
from services.workspace.permissions import PermissionRegistry


pytestmark = pytest.mark.unit


FILES = {
    "title.txt": "Demo",
    "strategy/constraints.md": "# Constraints\n\nKeep it concise.\n",
    "strategy/creative-brief.md": "# Brief\n\nA calm opening.\n",
    "sources/asset-1/understanding/current.ref": "analysis://asset-v1@analysis-v1",
    "sources/asset-1/understanding/versions/analysis-v1/summary.md": "# Source\n\nOcean footage.",
    "visual/style.md": "# Style\n\nWatercolor.",
    "story/outline.md": "# Outline\n\nOpening, middle, end.",
    "story/sections/sec-1/script.md": "# Script\n\nWelcome.",
    "story/sections/sec-1/units/unit-1/route.txt": "r2v",
    "story/sections/sec-1/units/unit-1/duration.txt": "8",
    "story/sections/sec-1/units/unit-1/production/r2v/video/prompt.md": "slow dolly",
    "post/final/audio-plan.md": "# Mix\n\nStereo.",
}


@dataclass
class StateProvider:
    state: RuntimeWriteState | None

    def get_write_state(self, *, project_id: str, transaction_id: str, lease_id: str):
        return self.state


class RecordingGateway:
    def __init__(self, text_store, *, race_text: str | None = None):
        self.text_store = text_store
        self.requests: list[TextWriteRequest] = []
        self.race_text = race_text
        self._seq = 0

    def commit_text_write(self, request: TextWriteRequest) -> CommittedWorkspaceMutation:
        self.requests.append(request)
        if self.race_text is not None:
            self.text_store.write_text(
                project_id=request.context.project_id,
                branch_id=request.context.working_branch_id,
                path=request.path,
                text=self.race_text,
                expected_blob_hash=request.expected_blob_hash,
            )
        result = self.text_store.write_text(
            project_id=request.context.project_id,
            branch_id=request.context.working_branch_id,
            path=request.path,
            text=request.text,
            expected_blob_hash=request.expected_blob_hash,
        )
        if not result.changed:
            return CommittedWorkspaceMutation(result, None, None)
        self._seq += 1
        return CommittedWorkspaceMutation(result, f"mutation-{self._seq}", self._seq)


@pytest.fixture()
def branch(workspace_stack):
    revision = workspace_stack.revisions.create_initial_approved_revision(
        project_id="project-1", files=FILES
    )
    working = workspace_stack.text.open_working_tree(
        project_id="project-1",
        base_revision_id=revision.id,
        branch_id="branch-1",
    )
    return revision, working


def _context(
    role: SpecialistRole | str,
    *,
    branch_id: str = "branch-1",
    observed_head: str,
    scope_target: str = "unit:unit-1",
) -> WorkspaceToolContext:
    return WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role=role,
        working_branch_id=branch_id,
        transaction_id="transaction-1",
        specialist_run_id=None if role == "creator_agent" else "run-1",
        writer_lease_id="lease-1",
        observed_working_head=observed_head,
        target_ref=scope_target,
    )


def _state(
    *,
    branch_id: str = "branch-1",
    observed_head: str,
    scope: str,
    status: TransactionStatus = TransactionStatus.ACTIVE,
    lease_status: str = "ACTIVE",
    expires_at: datetime | None = None,
) -> RuntimeWriteState:
    return RuntimeWriteState(
        project_id="project-1",
        creator_session_id="session-1",
        transaction_id="transaction-1",
        working_branch_id=branch_id,
        transaction_status=status,
        lease_id="lease-1",
        lease_status=lease_status,
        lease_target_scope=scope,
        lease_specialist_run_id=(
            None if scope.startswith(("settings/", "strategy/")) else "run-1"
        ),
        lease_observed_working_head=observed_head,
        lease_expires_at=expires_at or datetime.now(timezone.utc) + timedelta(minutes=10),
    )


def _tools(workspace_stack, context, state, *, gateway=None):
    recorder = gateway or RecordingGateway(workspace_stack.text)
    return (
        WorkspaceFileTools(
            workspace_stack.text,
            context,
            write_state_provider=StateProvider(state),
            mutation_gateway=recorder,
        ),
        recorder,
    )


def test_reads_current_working_branch_or_immutable_revision_and_accumulates_versions(
    workspace_stack, branch
):
    revision, working = branch
    initial_entry = revision.entry_map()["strategy/creative-brief.md"]
    changed = workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=working.id,
        path="strategy/creative-brief.md",
        text="# Brief\n\nWorking value.",
        expected_blob_hash=initial_entry.blob_hash,
    )

    working_context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        working_branch_id=working.id,
    )
    working_tools = WorkspaceFileTools(workspace_stack.text, working_context)
    current = working_tools.read_file("strategy/creative-brief.md")
    assert current["content"].endswith("Working value.")
    assert current["blobHash"] == changed.after_entry.blob_hash
    assert working_context.read_set.snapshot()[0].object_version == current["objectVersion"]

    revision_context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        revision_id=revision.id,
    )
    historical = WorkspaceFileTools(workspace_stack.text, revision_context).read_file(
        "strategy/creative-brief.md"
    )
    assert historical["content"].endswith("A calm opening.\n")
    assert historical["blobHash"] == initial_entry.blob_hash
    observed = revision_context.read_set.snapshot()[0]
    assert observed.view_kind == "revision"
    assert observed.view_id == revision.id


def test_search_tools_record_every_scanned_or_returned_file_and_ast_is_text_native(
    workspace_stack, branch
):
    _, working = branch
    context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        working_branch_id=working.id,
    )
    tools = WorkspaceFileTools(workspace_stack.text, context)

    globbed = tools.glob_search("strategy/**/*.md")
    assert {item["path"] for item in globbed["files"]} == {
        "strategy/constraints.md",
        "strategy/creative-brief.md",
    }
    grep = tools.grep_search("opening", path="strategy", case_sensitive=False)
    assert grep["matches"][0]["path"] == "strategy/creative-brief.md"
    ast = tools.ast_search("brief", path="strategy")
    assert ast["matches"][0]["kind"] == "markdown_heading"
    observed = context.read_set.snapshot()
    assert {item.path for item in observed} == {
        "strategy/constraints.md",
        "strategy/creative-brief.md",
    }
    assert all(item.blob_hash and item.object_version for item in observed)


def test_truncated_glob_still_records_every_enumerated_file_version(workspace_stack, branch):
    _, working = branch
    context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        working_branch_id=working.id,
    )
    result = WorkspaceFileTools(workspace_stack.text, context).glob_search(
        "strategy/**/*.md", max_results=1
    )
    assert result["truncated"] is True
    assert len(result["files"]) == 1
    assert {entry.path for entry in context.read_set.snapshot()} == {
        "strategy/constraints.md",
        "strategy/creative-brief.md",
    }


def test_read_scope_filters_search_and_direct_reads_are_denied(workspace_stack, branch):
    _, working = branch
    context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role=SpecialistRole.R2V_GENERATION_DIRECTOR,
        working_branch_id=working.id,
    )
    tools = WorkspaceFileTools(workspace_stack.text, context)
    paths = {item["path"] for item in tools.glob_search("**")["files"]}
    assert "strategy/creative-brief.md" in paths
    assert "story/outline.md" not in paths
    with pytest.raises(Exception) as denied:
        tools.read_file("story/outline.md")
    assert getattr(denied.value, "code", None) == "PERMISSION_DENIED"


def test_public_tool_map_is_role_filtered(workspace_stack, branch):
    _, working = branch
    creator = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        working_branch_id=working.id,
    )
    review = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role=SpecialistRole.REVIEW_CONSISTENCY,
        working_branch_id=working.id,
    )
    ai_edit = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role=SpecialistRole.AI_EDITING_DIRECTOR,
        working_branch_id=working.id,
    )
    assert set(WorkspaceFileTools(workspace_stack.text, creator).public_tools()) == {
        "read_file",
        "write_file",
        "edit_file",
        "append_file",
        "grep_search",
        "glob_search",
        "ast_search",
    }
    assert set(WorkspaceFileTools(workspace_stack.text, review).public_tools()) == {
        "read_file",
        "grep_search",
        "glob_search",
        "ast_search",
    }
    assert WorkspaceFileTools(workspace_stack.text, ai_edit).public_tools() == {}


def test_write_edit_append_use_cas_readset_and_atomic_gateway_evidence(workspace_stack, branch):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
    )

    first = tools.edit_file(
        path,
        "calm",
        "bold",
        expected_blob_hash=before.blob_hash,
        expected_object_version=before.object_version,
    )
    assert first["mutationId"] == "mutation-1"
    assert first["eventSeq"] == 1
    assert gateway.requests[0].read_set[0].path == path

    second = tools.append_file(
        path,
        "\nEnd.",
        expected_blob_hash=first["blobHash"],
        expected_object_version=first["objectVersion"],
    )
    assert second["mutationId"] == "mutation-2"
    assert workspace_stack.text.read_text(
        "project-1", path, branch_id=working.id
    ).endswith("End.")
    assert context.read_set.snapshot()[0].object_version == second["objectVersion"]


def test_write_file_creates_sibling_leaf_when_virtual_parent_exists(
    workspace_stack,
    branch,
):
    _, working = branch
    path = "story/sections/sec-1/units/unit-1/continuity.md"
    context = _context(
        SpecialistRole.UNIT_PLANNING_ROUTING,
        observed_head=working.head,
        scope_target="unit:unit-1",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(
            observed_head=working.head,
            scope="story/sections/sec-1/units/unit-1/**",
        ),
    )

    result = tools.write_file(
        path,
        "保持角色与场景连续。",
        expected_blob_hash=None,
        expected_object_version=None,
    )

    assert result["changed"] is True
    assert gateway.requests[0].expected_blob_hash is None
    assert workspace_stack.text.read_text(
        "project-1",
        path,
        branch_id=working.id,
    ) == "保持角色与场景连续。"


def test_unrelated_working_head_change_does_not_invalidate_scoped_writer(workspace_stack, branch):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, _ = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
    )
    tools.read_file(path)
    visual = working.entry_map()["visual/style.md"]
    workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=working.id,
        path="visual/style.md",
        text="# Style\n\nInk.",
        expected_blob_hash=visual.blob_hash,
    )

    result = tools.write_file(
        path,
        "# Brief\n\nStill valid.",
        expected_blob_hash=before.blob_hash,
        expected_object_version=before.object_version,
    )
    assert result["changed"] is True


def test_changed_readset_file_rejects_write_even_when_target_is_unchanged(workspace_stack, branch):
    _, working = branch
    target = "strategy/creative-brief.md"
    dependency = "strategy/constraints.md"
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, _ = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
    )
    tools.read_file(dependency)
    dependency_entry = working.entry_map()[dependency]
    workspace_stack.text.write_text(
        project_id="project-1",
        branch_id=working.id,
        path=dependency,
        text="# Constraints\n\nChanged externally.",
        expected_blob_hash=dependency_entry.blob_hash,
    )
    target_entry = working.entry_map()[target]
    with pytest.raises(ConflictError) as stale:
        tools.write_file(
            target,
            "# Brief\n\nUnsafe output.",
            expected_blob_hash=target_entry.blob_hash,
            expected_object_version=target_entry.object_version,
        )
    assert stale.value.details["reason"] == "READ_SET_STALE"


def test_target_cas_blocks_stale_writer_and_gateway_race(workspace_stack, branch):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, _ = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
    )
    with pytest.raises(ConflictError) as stale:
        tools.write_file(
            path,
            "stale",
            expected_blob_hash="0" * 64,
            expected_object_version="0" * 64,
        )
    assert stale.value.details["reason"] == "TARGET_VERSION_STALE"

    race_gateway = RecordingGateway(workspace_stack.text, race_text="external winner")
    race_tools, _ = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
        gateway=race_gateway,
    )
    with pytest.raises(ConflictError):
        race_tools.write_file(
            path,
            "must lose",
            expected_blob_hash=before.blob_hash,
            expected_object_version=before.object_version,
        )


@pytest.mark.parametrize(
    "status",
    [
        TransactionStatus.COMPLETION_CHECK,
        TransactionStatus.SEALING,
        TransactionStatus.PENDING_REVIEW,
        TransactionStatus.COMMITTED,
    ],
)
def test_non_writable_transaction_phases_reject_immediately(workspace_stack, branch, status):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**", status=status),
    )
    with pytest.raises(PhaseConflictError):
        tools.write_file(
            path,
            "blocked",
            expected_blob_hash=before.blob_hash,
            expected_object_version=before.object_version,
        )
    assert gateway.requests == []


@pytest.mark.parametrize(
    ("state_changes", "error"),
    [
        ({"lease_status": "RELEASED"}, PhaseConflictError),
        (
            {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
            PhaseConflictError,
        ),
        ({"scope": "visual/**"}, PhaseConflictError),
    ],
)
def test_invalid_expired_or_out_of_scope_lease_is_rejected(
    workspace_stack, branch, state_changes, error
):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    state = _state(
        observed_head=working.head,
        scope=state_changes.get("scope", "strategy/**"),
        lease_status=state_changes.get("lease_status", "ACTIVE"),
        expires_at=state_changes.get("expires_at"),
    )
    tools, gateway = _tools(workspace_stack, context, state)
    with pytest.raises(error):
        tools.write_file(
            path,
            "blocked",
            expected_blob_hash=before.blob_hash,
            expected_object_version=before.object_version,
        )
    assert gateway.requests == []


@pytest.mark.parametrize("mismatch", ["run", "branch", "head"])
def test_forged_lease_identity_or_issued_head_is_rejected(
    workspace_stack, branch, mismatch
):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    state = _state(observed_head=working.head, scope="strategy/**")
    if mismatch == "run":
        state = replace(state, lease_specialist_run_id="run-other")
    elif mismatch == "branch":
        state = replace(state, working_branch_id="branch-other")
    else:
        state = replace(state, lease_observed_working_head="head-other")
    tools, gateway = _tools(workspace_stack, context, state)
    with pytest.raises((PhaseConflictError, ConflictError)):
        tools.write_file(
            path,
            "blocked",
            expected_blob_hash=before.blob_hash,
            expected_object_version=before.object_version,
        )
    assert gateway.requests == []


def test_owner_review_ai_edit_and_creator_write_boundaries_are_hard(workspace_stack, branch):
    _, working = branch
    path = "strategy/creative-brief.md"
    before = working.entry_map()[path]
    for role in (
        SpecialistRole.STORY_PLANNING,
        SpecialistRole.REVIEW_CONSISTENCY,
        SpecialistRole.AI_EDITING_DIRECTOR,
    ):
        context = _context(role, observed_head=working.head, scope_target="project:project-1")
        tools, gateway = _tools(
            workspace_stack,
            context,
            _state(observed_head=working.head, scope="strategy/**"),
        )
        with pytest.raises(Exception) as denied:
            tools.write_file(
                path,
                "forbidden",
                expected_blob_hash=before.blob_hash,
                expected_object_version=before.object_version,
            )
        assert getattr(denied.value, "code", None) == "PERMISSION_DENIED"
        assert gateway.requests == []


def test_source_intelligence_has_no_model_visible_file_write_surface(
    workspace_stack, branch
):
    _, working = branch
    context = _context(
        SpecialistRole.SOURCE_INTELLIGENCE,
        observed_head=working.head,
        scope_target="asset:asset-1",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="sources/asset-1/understanding/**"),
    )
    assert not {
        "write_file",
        "edit_file",
        "append_file",
    }.intersection(tools.public_tools())
    assert gateway.requests == []
    assert not hasattr(tools, "move_file")
    assert not hasattr(tools, "delete_file")


def test_immutable_revision_cannot_be_written(workspace_stack, branch):
    revision, _ = branch
    context = WorkspaceToolContext(
        project_id="project-1",
        creator_session_id="session-1",
        role="creator_agent",
        revision_id=revision.id,
        transaction_id="transaction-1",
        writer_lease_id="lease-1",
        observed_working_head="head-1",
        target_ref="project:project-1",
    )
    tools = WorkspaceFileTools(
        workspace_stack.text,
        context,
        write_state_provider=StateProvider(None),
        mutation_gateway=RecordingGateway(workspace_stack.text),
    )
    before = revision.entry_map()["strategy/creative-brief.md"]
    with pytest.raises(PhaseConflictError):
        tools.write_file(
            "strategy/creative-brief.md",
            "no",
            expected_blob_hash=before.blob_hash,
            expected_object_version=before.object_version,
        )


def test_unsafe_path_is_rejected_before_store_or_gateway_access(workspace_stack, branch):
    _, working = branch
    context = _context(
        "creator_agent",
        observed_head=working.head,
        scope_target="project:project-1",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(observed_head=working.head, scope="strategy/**"),
    )
    with pytest.raises(ValidationError):
        tools.write_file(
            "../../etc/passwd",
            "escape",
            expected_blob_hash=None,
            expected_object_version=None,
        )
    assert gateway.requests == []


def test_source_run_may_write_an_older_analysis_version_when_run_isolation_is_disabled(workspace_stack, branch):
    _, working = branch
    context = replace(
        _context(
            SpecialistRole.SOURCE_INTELLIGENCE,
            observed_head=working.head,
            scope_target="asset:asset-1",
        ),
        specialist_run_id="analysis-v2",
    )
    tools, gateway = _tools(
        workspace_stack,
        context,
        _state(
            observed_head=working.head,
            scope="sources/asset-1/understanding/**",
        ),
    )
    old_path = "sources/asset-1/understanding/versions/analysis-v1/summary.md"
    assert not {
        "write_file",
        "edit_file",
        "append_file",
    }.intersection(tools.public_tools())
    PermissionRegistry().ensure_run_write_path(
        SpecialistRole.SOURCE_INTELLIGENCE,
        old_path,
        specialist_run_id="analysis-v2",
        target_ref="asset:asset-1",
    )

    assert gateway.requests == []
