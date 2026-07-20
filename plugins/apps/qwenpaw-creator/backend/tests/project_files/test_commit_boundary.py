# -*- coding: utf-8 -*-
# pylint: disable=protected-access,use-implicit-booleaness-not-comparison
from __future__ import annotations

import threading

import pytest

from domain.enums import TransactionStatus
from services.project_files.commit import (
    ActiveReviewConflictError,
    ProjectCommitBoundary,
    ProjectCommitError,
    ProtectedFieldError,
)
from services.project_files.json_pointer import JsonCasConflict
from services.project_files.models import Project
from services.project_files.recovery import ProjectCommitRecoveryCoordinator
from services.project_files.store import ProjectStore
from services.runtime_files.atomic_store import AtomicJsonRecordStore
from services.runtime_files.errors import FieldBlockConflictError
from services.runtime_files.field_blocks import FieldBlockStore
from services.runtime_files.models import (
    ChangeRoundRecord,
    ReviewBoundary,
    ReviewRecord,
    RuntimeChangeSet,
    RuntimeProjectState,
)


def _store(tmp_path) -> tuple[ProjectStore, object]:
    store = ProjectStore(tmp_path.resolve())
    return store, store.create(
        Project.new(project_id="project-1", name="Initial"),
    )


def test_commit_publishes_project_changeset_and_accepted_state(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Updated"

    result = ProjectCommitBoundary(store).commit(
        base=base,
        candidate=candidate,
        origin="frontend_edit",
    )

    assert result.snapshot.generation == 1
    assert store.read("project-1").project.name == "Updated"
    assert [change.json_pointer for change in result.changeset.changes] == [
        "/name",
    ]
    state = AtomicJsonRecordStore(
        tmp_path / "project-1" / "runtime" / "state.json",
        RuntimeProjectState,
    ).read()
    assert state.accepted_generation == 1
    assert state.accepted_etag == result.snapshot.etag
    assert result.review is None


def test_disjoint_commits_from_one_base_merge(tmp_path) -> None:
    store, base = _store(tmp_path)
    first = base.project.model_dump(mode="json")
    first["name"] = "Name A"
    ProjectCommitBoundary(store).commit(
        base=base,
        candidate=first,
        origin="frontend_edit",
    )

    second = base.project.model_dump(mode="json")
    second["description"] = "Description B"
    result = ProjectCommitBoundary(store).commit(
        base=base,
        candidate=second,
        origin="runtime_task",
    )

    assert result.snapshot.generation == 2
    assert result.snapshot.project.name == "Name A"
    assert result.snapshot.project.description == "Description B"


def test_runtime_finalization_is_serialized_in_project_generation_order(
    tmp_path,
    monkeypatch,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    first_candidate = base.project.model_dump(mode="json")
    first_candidate["name"] = "First"
    second_candidate = base.project.model_dump(mode="json")
    second_candidate["description"] = "Second"
    first_finalizing = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    errors: list[BaseException] = []
    original_record_review = boundary._record_review

    def delayed_record_review(**kwargs):
        if kwargs["snapshot"].generation == 1:
            first_finalizing.set()
            assert release_first.wait(timeout=2)
        return original_record_review(**kwargs)

    monkeypatch.setattr(boundary, "_record_review", delayed_record_review)

    def commit_first() -> None:
        try:
            boundary.commit(
                base=base,
                candidate=first_candidate,
                origin="runtime_task",
            )
        except BaseException as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    def commit_second() -> None:
        try:
            boundary.commit(
                base=base,
                candidate=second_candidate,
                origin="frontend_edit",
            )
        except BaseException as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)
        finally:
            second_done.set()

    first_thread = threading.Thread(target=commit_first)
    second_thread = threading.Thread(target=commit_second)
    first_thread.start()
    assert first_finalizing.wait(timeout=2)
    second_thread.start()
    assert not second_done.wait(timeout=0.1)
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not errors
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    current = store.read("project-1")
    state = AtomicJsonRecordStore(
        tmp_path / "project-1" / "runtime" / "state.json",
        RuntimeProjectState,
    ).read()
    assert current.generation == 2
    assert current.project.name == "First"
    assert current.project.description == "Second"
    assert state.last_project_generation == 2
    assert state.accepted_generation == 2


def test_same_field_commits_from_one_base_conflict(tmp_path) -> None:
    store, base = _store(tmp_path)
    first = base.project.model_dump(mode="json")
    first["name"] = "Name A"
    ProjectCommitBoundary(store).commit(
        base=base,
        candidate=first,
        origin="frontend_edit",
    )
    second = base.project.model_dump(mode="json")
    second["name"] = "Name B"

    try:
        ProjectCommitBoundary(store).commit(
            base=base,
            candidate=second,
            origin="runtime_task",
        )
    except JsonCasConflict as exc:
        assert exc.conflicts[0]["pointer"] == "/name"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("same-field stale commit unexpectedly succeeded")


def test_same_round_keeps_immutable_changeset_per_transaction(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    first_candidate = base.project.model_dump(mode="json")
    first_candidate["name"] = "First"
    first = boundary.commit(
        base=base,
        candidate=first_candidate,
        origin="runtime_task",
        round_id="same-round",
        transaction_id="same-round-tx-1",
    )
    second_candidate = first.snapshot.project.model_dump(mode="json")
    second_candidate["description"] = "Second"
    boundary.commit(
        base=first.snapshot,
        candidate=second_candidate,
        origin="runtime_task",
        round_id="same-round",
        transaction_id="same-round-tx-2",
    )

    runtime_root = tmp_path / "project-1" / "runtime"
    first_changeset = AtomicJsonRecordStore(
        runtime_root / "transactions" / "same-round-tx-1" / "changeset.json",
        RuntimeChangeSet,
    ).read()
    second_changeset = AtomicJsonRecordStore(
        runtime_root / "transactions" / "same-round-tx-2" / "changeset.json",
        RuntimeChangeSet,
    ).read()
    assert [change.json_pointer for change in first_changeset.changes] == [
        "/name",
    ]
    assert [change.json_pointer for change in second_changeset.changes] == [
        "/description",
    ]
    report = ProjectCommitRecoveryCoordinator(store).recover_project(
        "project-1",
    )
    assert report.ok


def test_failed_same_round_attempt_does_not_roll_aggregate_back_to_active(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    first_candidate = base.project.model_dump(mode="json")
    first_candidate["name"] = "First"
    boundary.commit(
        base=base,
        candidate=first_candidate,
        origin="runtime_task",
        round_id="same-round",
        transaction_id="same-round-success",
    )
    stale_candidate = base.project.model_dump(mode="json")
    stale_candidate["name"] = "Stale"

    with pytest.raises(JsonCasConflict):
        boundary.commit(
            base=base,
            candidate=stale_candidate,
            origin="runtime_task",
            round_id="same-round",
            transaction_id="same-round-conflict",
        )

    runtime_root = tmp_path / "project-1" / "runtime"
    aggregate = AtomicJsonRecordStore(
        runtime_root / "change-rounds" / "same-round" / "round.json",
        ChangeRoundRecord,
    ).read()
    failed_attempt = AtomicJsonRecordStore(
        runtime_root / "transactions" / "same-round-conflict" / "round.json",
        ChangeRoundRecord,
    ).read()
    assert aggregate.status is TransactionStatus.COMMITTED
    assert failed_attempt.status is TransactionStatus.ABORTED


def test_transaction_is_published_only_after_initial_journal_is_durable(
    tmp_path,
    monkeypatch,
) -> None:
    store, base = _store(tmp_path)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Published only after journal"
    transaction_id = "initial-journal-fault"
    round_id = "initial-journal-round"
    runtime_root = store.project_root("project-1") / "runtime"
    staging_root = runtime_root / "temp" / "transactions"
    transaction_root = runtime_root / "transactions" / transaction_id
    aggregate_round_path = (
        runtime_root / "change-rounds" / round_id / "round.json"
    )
    original_write = AtomicJsonRecordStore.write

    def fail_initial_journal(self, value):
        if (
            self.path.name == "journal.json"
            and self.path.parent.parent == staging_root
        ):
            raise RuntimeError("injected initial journal failure")
        return original_write(self, value)

    with monkeypatch.context() as patch:
        patch.setattr(AtomicJsonRecordStore, "write", fail_initial_journal)
        with pytest.raises(RuntimeError, match="initial journal failure"):
            ProjectCommitBoundary(store).commit(
                base=base,
                candidate=candidate,
                origin="runtime_task",
                round_id=round_id,
                transaction_id=transaction_id,
            )

    assert not transaction_root.exists()
    assert not aggregate_round_path.exists()
    assert list(staging_root.iterdir()) == []

    # A real process death can leave an incomplete temp entry. It is outside
    # both transaction admission and recovery discovery, so a retry proceeds.
    (staging_root / "orphaned-process-death").mkdir()
    result = ProjectCommitBoundary(store).commit(
        base=base,
        candidate=candidate,
        origin="runtime_task",
        round_id=round_id,
        transaction_id=transaction_id,
    )

    assert result.snapshot.project.name == "Published only after journal"
    assert (
        ProjectCommitRecoveryCoordinator(store).recover_project("project-1").ok
    )


def test_no_change_promotes_aborted_same_round_projection(
    tmp_path,
    monkeypatch,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Never published"

    with monkeypatch.context() as patch:
        patch.setattr(
            store,
            "replace",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("injected pre-publish failure"),
            ),
        )
        with pytest.raises(RuntimeError, match="pre-publish failure"):
            boundary.commit(
                base=base,
                candidate=candidate,
                origin="runtime_task",
                round_id="aborted-then-no-change",
                transaction_id="aborted-attempt",
            )

    runtime_root = store.project_root("project-1") / "runtime"
    aggregate_store = AtomicJsonRecordStore(
        runtime_root
        / "change-rounds"
        / "aborted-then-no-change"
        / "round.json",
        ChangeRoundRecord,
    )
    assert aggregate_store.read().status is TransactionStatus.ABORTED

    result = boundary.commit(
        base=base,
        candidate=base.project.model_dump(mode="json"),
        origin="runtime_task",
        round_id="aborted-then-no-change",
        transaction_id="no-change-attempt",
    )

    assert result.round.status is TransactionStatus.NO_CHANGE
    assert aggregate_store.read().status is TransactionStatus.NO_CHANGE


def test_no_change_does_not_downgrade_committed_same_round_projection(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Committed"
    first = boundary.commit(
        base=base,
        candidate=candidate,
        origin="runtime_task",
        round_id="committed-then-no-change",
        transaction_id="committed-attempt",
    )

    second = boundary.commit(
        base=first.snapshot,
        candidate=first.snapshot.project.model_dump(mode="json"),
        origin="runtime_task",
        round_id="committed-then-no-change",
        transaction_id="committed-no-change-attempt",
    )
    aggregate = AtomicJsonRecordStore(
        store.project_root("project-1")
        / "runtime"
        / "change-rounds"
        / "committed-then-no-change"
        / "round.json",
        ChangeRoundRecord,
    ).read()

    assert second.round.status is TransactionStatus.NO_CHANGE
    assert aggregate.status is TransactionStatus.COMMITTED


def test_no_change_does_not_downgrade_pending_review_projection(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Needs review"
    review_boundary = ReviewBoundary(
        request_message_seq=1,
        request_id="request-pending",
        interrupted_run_id="run-pending",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )
    metadata = {
        "origin": "agentdock_interrupt",
        "review_policy": "require_review",
        "review_boundary": review_boundary,
        "round_id": "pending-then-no-change",
    }
    first = boundary.commit(
        base=base,
        candidate=candidate,
        transaction_id="pending-attempt",
        **metadata,
    )

    second = boundary.commit(
        base=first.snapshot,
        candidate=first.snapshot.project.model_dump(mode="json"),
        transaction_id="pending-no-change-attempt",
        **metadata,
    )
    aggregate = AtomicJsonRecordStore(
        store.project_root("project-1")
        / "runtime"
        / "change-rounds"
        / "pending-then-no-change"
        / "round.json",
        ChangeRoundRecord,
    ).read()

    assert second.round.status is TransactionStatus.NO_CHANGE
    assert aggregate.status is TransactionStatus.PENDING_REVIEW


def test_identical_retry_archives_safe_aborted_transaction(
    tmp_path,
    monkeypatch,
) -> None:
    store, base = _store(tmp_path)
    boundary = ProjectCommitBoundary(store)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Retried"
    original_replace = store.replace

    def fail_before_publish(*args, **kwargs):
        raise RuntimeError("injected pre-publish failure")

    monkeypatch.setattr(store, "replace", fail_before_publish)
    with pytest.raises(RuntimeError, match="pre-publish"):
        boundary.commit(
            base=base,
            candidate=candidate,
            origin="runtime_task",
            round_id="retry-round",
            transaction_id="retry-transaction",
        )
    monkeypatch.setattr(store, "replace", original_replace)

    result = boundary.commit(
        base=base,
        candidate=candidate,
        origin="runtime_task",
        round_id="retry-round",
        transaction_id="retry-transaction",
    )

    assert result.snapshot.project.name == "Retried"
    assert result.snapshot.generation == 1
    history = (
        tmp_path / "project-1" / "runtime" / "transaction-history" / "aborted"
    )
    archived = list(history.iterdir())
    assert len(archived) == 1
    assert archived[0].name.startswith("retry-transaction.")


def test_commit_boundary_enforces_field_block_at_publish_time(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    blocks = FieldBlockStore(
        store.project_root("project-1") / "runtime" / "locks" / "fields",
    )
    block = blocks.acquire(
        project_id="project-1",
        json_pointer="/name",
        owner_kind="user",
        owner_id="browser-1",
        base_field_hash="sha256:before",
        ttl_seconds=30,
    )
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Blocked"

    with pytest.raises(FieldBlockConflictError):
        ProjectCommitBoundary(store).commit(
            base=base,
            candidate=candidate,
            origin="runtime_task",
        )
    assert store.read("project-1") == base

    result = ProjectCommitBoundary(store).commit(
        base=base,
        candidate=candidate,
        origin="frontend_edit",
        block_token=block.token,
    )
    assert result.snapshot.project.name == "Blocked"


def test_candidate_cannot_change_runtime_metadata(tmp_path) -> None:
    store, base = _store(tmp_path)
    candidate = base.project.model_dump(mode="json")
    candidate["generation"] = 99

    try:
        ProjectCommitBoundary(store).commit(
            base=base,
            candidate=candidate,
            origin="runtime_task",
        )
    except ProtectedFieldError as exc:
        assert exc.pointers == ["/generation"]
    else:  # pragma: no cover - assertion guard
        raise AssertionError(
            "protected metadata change unexpectedly succeeded",
        )


def test_commit_ids_cannot_escape_runtime_directories(tmp_path) -> None:
    store, base = _store(tmp_path)
    candidate = base.project.model_dump(mode="json")
    candidate["name"] = "Unsafe"
    outside = tmp_path / "escaped"

    for arguments in (
        {"transaction_id": "../escaped"},
        {"transaction_id": "safe", "round_id": "x/../../escaped"},
        {"transaction_id": "safe", "round_id": "bad\\segment"},
        {"transaction_id": "safe", "round_id": "bad\x00segment"},
    ):
        with pytest.raises(ProjectCommitError, match="unsafe Runtime path"):
            ProjectCommitBoundary(store).commit(
                base=base,
                candidate=candidate,
                origin="runtime_task",
                **arguments,
            )

    assert not outside.exists()


def test_only_agentdock_active_interrupt_creates_review(tmp_path) -> None:
    store, base = _store(tmp_path)
    candidate = base.project.model_dump(mode="json")
    candidate["description"] = "AgentDock requested change"
    boundary = ReviewBoundary(
        request_message_seq=2,
        request_id="request-2",
        interrupted_run_id="run-1",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )

    result = ProjectCommitBoundary(store).commit(
        base=base,
        candidate=candidate,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="round-2",
    )

    assert result.review is not None
    assert [
        operation.json_pointer for operation in result.review.operations
    ] == [
        "/description",
    ]
    persisted = AtomicJsonRecordStore(
        tmp_path
        / "project-1"
        / "runtime"
        / "reviews"
        / "review-round-2"
        / "review.json",
        ReviewRecord,
    ).read()
    assert persisted.request_id == "request-2"
    state = AtomicJsonRecordStore(
        tmp_path / "project-1" / "runtime" / "state.json",
        RuntimeProjectState,
    ).read()
    assert state.accepted_generation == 0
    assert state.last_project_generation == 1


def test_second_review_round_cannot_overtake_active_review(tmp_path) -> None:
    store, base = _store(tmp_path)
    commit = ProjectCommitBoundary(store)
    first_candidate = base.project.model_dump(mode="json")
    first_candidate["description"] = "Needs review"
    first_boundary = ReviewBoundary(
        request_message_seq=2,
        request_id="request-2",
        interrupted_run_id="run-1",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )
    first = commit.commit(
        base=base,
        candidate=first_candidate,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=first_boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="review-round-1",
    )
    second_candidate = first.snapshot.project.model_dump(mode="json")
    second_candidate["name"] = "Cannot overtake"
    second_boundary = ReviewBoundary(
        request_message_seq=3,
        request_id="request-3",
        interrupted_run_id="run-2",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )

    with pytest.raises(ActiveReviewConflictError, match="still pending"):
        commit.commit(
            base=first.snapshot,
            candidate=second_candidate,
            origin="agentdock_interrupt",
            review_policy="require_review",
            review_boundary=second_boundary,
            caused_by_request_id="request-3",
            caused_by_message_seq=3,
            round_id="review-round-2",
        )

    current = store.read("project-1")
    state = AtomicJsonRecordStore(
        tmp_path / "project-1" / "runtime" / "state.json",
        RuntimeProjectState,
    ).read()
    assert current.generation == 1
    assert current.project.name == "Initial"
    assert state.active_round_id == "review-round-1"
    assert state.accepted_generation == 0


def test_one_review_round_accumulates_multiple_transactions_safely(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    commit = ProjectCommitBoundary(store)
    review_boundary = ReviewBoundary(
        request_message_seq=2,
        request_id="request-2",
        interrupted_run_id="run-1",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )
    first_candidate = base.project.model_dump(mode="json")
    first_candidate["name"] = "First reviewed change"
    first = commit.commit(
        base=base,
        candidate=first_candidate,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=review_boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="one-review-round",
        transaction_id="review-transaction-1",
    )
    second_candidate = first.snapshot.project.model_dump(mode="json")
    second_candidate["description"] = "Second reviewed change"
    second = commit.commit(
        base=first.snapshot,
        candidate=second_candidate,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=review_boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="one-review-round",
        transaction_id="review-transaction-2",
    )

    assert second.review is not None
    assert {item.json_pointer for item in second.review.operations} == {
        "/name",
        "/description",
    }
    operation_ids = [item.operation_id for item in second.review.operations]
    assert len(operation_ids) == len(set(operation_ids))
    assert (
        ProjectCommitRecoveryCoordinator(store).recover_project("project-1").ok
    )


def test_review_round_net_zero_clears_review_and_recovers_cleanly(
    tmp_path,
) -> None:
    store, base = _store(tmp_path)
    commit = ProjectCommitBoundary(store)
    review_boundary = ReviewBoundary(
        request_message_seq=2,
        request_id="request-2",
        interrupted_run_id="run-1",
        accepted_generation=base.generation,
        accepted_etag=base.etag,
    )
    changed = base.project.model_dump(mode="json")
    changed["name"] = "Temporary"
    first = commit.commit(
        base=base,
        candidate=changed,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=review_boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="net-zero-round",
        transaction_id="net-zero-1",
    )
    restored = first.snapshot.project.model_dump(mode="json")
    restored["name"] = base.project.name
    second = commit.commit(
        base=first.snapshot,
        candidate=restored,
        origin="agentdock_interrupt",
        review_policy="require_review",
        review_boundary=review_boundary,
        caused_by_request_id="request-2",
        caused_by_message_seq=2,
        round_id="net-zero-round",
        transaction_id="net-zero-2",
    )

    state = AtomicJsonRecordStore(
        tmp_path / "project-1" / "runtime" / "state.json",
        RuntimeProjectState,
    ).read()
    assert second.review is None
    assert second.round.status is TransactionStatus.COMMITTED
    assert state.active_round_id is None
    assert state.accepted_generation == second.snapshot.generation
    assert (
        ProjectCommitRecoveryCoordinator(store).recover_project("project-1").ok
    )
