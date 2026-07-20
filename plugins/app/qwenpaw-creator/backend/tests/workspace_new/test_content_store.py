from __future__ import annotations

import hashlib
import io

import pytest

from domain.errors import StorageIntegrityError, ValidationError
from services.workspace.content_store import ContentStore


pytestmark = pytest.mark.unit


def test_blob_and_artifact_are_content_addressed_and_deduplicated(tmp_path):
    store = ContentStore(tmp_path / "creator-data")
    payload = b"immutable creator bytes"
    digest = hashlib.sha256(payload).hexdigest()

    blob = store.put_bytes(payload)
    duplicate = store.put_stream(io.BytesIO(payload))
    artifact = store.put_bytes(payload, namespace="artifact")

    assert blob.sha256 == duplicate.sha256 == artifact.sha256 == digest
    assert blob.path == duplicate.path
    assert blob.path == store.root / "blobs" / "sha256" / digest[:2] / digest
    assert artifact.path == store.root / "artifacts" / "sha256" / digest[:2] / digest
    assert blob.path != artifact.path
    assert store.read_bytes(digest) == payload
    assert store.read_bytes(digest, namespace="artifact") == payload
    assert list(store.iter_digests()) == [digest]
    assert list(store.iter_digests(namespace="artifact")) == [digest]


def test_content_publish_order_is_temp_fsync_hash_rename_directory_fsync(tmp_path):
    payload = b"crash-safe payload"
    digest = hashlib.sha256(payload).hexdigest()
    events: list[str] = []
    target_holder = {}

    def hook(stage, path):
        events.append(stage)
        if stage in {"temp_created", "temp_fsynced", "hash_verified"}:
            target = target_holder.get("target")
            if target is not None:
                assert not target.exists()
        if stage == "renamed":
            assert path.read_bytes() == payload

    store = ContentStore(tmp_path / "creator-data", stage_hook=hook)
    target_holder["target"] = store.path_for(digest)
    stored = store.put_bytes(payload, expected_sha256=digest)

    assert stored.path == target_holder["target"]
    assert events == [
        "temp_created",
        "temp_fsynced",
        "hash_verified",
        "renamed",
        "directory_fsynced",
    ]
    assert not any(store._temp_root.iterdir())


def test_failure_before_atomic_rename_never_publishes_target(tmp_path):
    payload = b"must never become visible"
    digest = hashlib.sha256(payload).hexdigest()

    def crash_after_hash(stage, path):
        del path
        if stage == "hash_verified":
            raise RuntimeError("simulated process failure before rename")

    store = ContentStore(tmp_path / "creator-data", stage_hook=crash_after_hash)
    target = store.path_for(digest)

    with pytest.raises(RuntimeError, match="before rename"):
        store.put_bytes(payload)

    assert not target.exists()
    assert not any(store._temp_root.iterdir())


def test_expected_hash_mismatch_leaves_no_published_blob(tmp_path):
    store = ContentStore(tmp_path / "creator-data")
    payload = b"actual"
    wrong_digest = hashlib.sha256(b"expected-other").hexdigest()

    with pytest.raises(StorageIntegrityError, match="hash 不匹配"):
        store.put_bytes(payload, expected_sha256=wrong_digest)

    actual_digest = hashlib.sha256(payload).hexdigest()
    assert not store.exists(actual_digest)
    assert not any(store._temp_root.iterdir())


def test_existing_corrupt_blob_is_detected_not_silently_replaced(tmp_path):
    store = ContentStore(tmp_path / "creator-data")
    stored = store.put_bytes(b"original")
    stored.path.write_bytes(b"corrupt")

    with pytest.raises(StorageIntegrityError, match="文件损坏"):
        store.put_bytes(b"original")
    with pytest.raises(StorageIntegrityError, match="文件损坏"):
        store.read_bytes(stored.sha256)


@pytest.mark.parametrize(
    "digest",
    ["", "abc", "g" * 64, "0" * 63, "0" * 65, "../" + "0" * 64],
)
def test_digest_path_cannot_escape_content_store(tmp_path, digest):
    store = ContentStore(tmp_path / "creator-data")
    with pytest.raises(ValidationError, match="SHA-256"):
        store.path_for(digest)
