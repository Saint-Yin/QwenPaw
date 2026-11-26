# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=protected-access
# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument
"""Unit coverage for the segment-continuity injection layer.

Pure helpers (predecessor lookup, capability split, prompt formatting,
fingerprint stability, budget accounting) sit alongside mocked ffmpeg
cases that exercise the atomic write and tail-clip soft-failure paths
without invoking a real provider. All cases are unit-level and never
reach out to a live video model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from models.video_capabilities import supports_video_continuation
from services.media_files.segment_continuity import (
    continuity_prompt_suffix,
    continuity_reference_ids,
    find_predecessor_video_element,
    resolve_predecessor_video_version,
)
from services.project_files.models import (
    ArtifactSlot,
    ElementLocation,
    I2VCreation,
    Project,
    R2VCreation,
    T2VCreation,
    Timeline,
    TimelineElement,
    TimelineSpan,
)

pytestmark = pytest.mark.unit


def _element(
    element_id: str,
    *,
    start: int,
    duration: int = 4000,
    enabled: bool = True,
    creation_type: str = "r2v",
) -> TimelineElement:
    if creation_type == "i2v":
        creation = I2VCreation(video_prompt="续写")
    elif creation_type == "t2v":
        creation = T2VCreation(video_prompt="纯文本")
    else:
        creation = R2VCreation(
            narrative="动作",
            storyboard_prompt="分镜",
            video_prompt="视频",
        )
    return TimelineElement(
        element_id=element_id,
        label=element_id,
        span=TimelineSpan(start_tick=start, duration_tick=duration),
        location=ElementLocation(),
        creation=creation,
        enabled=enabled,
    )


def _project(elements: list[TimelineElement]) -> tuple[Project, Timeline]:
    project = Project.new(project_id="p-continuity", name="Continuity")
    timeline = Timeline(timeline_id="timeline:main", ticks_per_second=1000)
    timeline = timeline.model_copy(
        update={
            "elements_by_id": {item.element_id: item for item in elements},
        },
    )
    project.timelines.items["timeline:main"] = timeline
    project.timelines.order = ["timeline:main"]
    return project, timeline


def test_find_predecessor_returns_earliest_strictly_before_target() -> None:
    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    third = _element("e3", start=8000)
    _proj, timeline = _project([first, second, third])

    assert find_predecessor_video_element(timeline, third) is second
    assert find_predecessor_video_element(timeline, second) is first
    assert find_predecessor_video_element(timeline, first) is None


def test_find_predecessor_treats_same_tick_as_parallel_siblings() -> None:
    """Two elements starting at the same tick are siblings, not chained.

    This aligns the submit-side lookup with work_graph's own
    predecessor check so we never mark one STALE purely because a
    sibling shares its start tick.
    """

    left = _element("e-a", start=4000)
    right = _element("e-b", start=4000)
    _proj, timeline = _project([left, right])
    assert find_predecessor_video_element(timeline, left) is None
    assert find_predecessor_video_element(timeline, right) is None


def test_find_predecessor_skips_disabled_and_non_video_creations() -> None:
    first = _element("e1", start=0)
    t2v_gap = _element("e2", start=4000, creation_type="t2v")
    disabled = _element("e3", start=8000, enabled=False)
    target = _element("e4", start=12000)
    _proj, timeline = _project([first, t2v_gap, disabled, target])

    # T2V and disabled Elements are filtered out; the nearest R2V/I2V
    # predecessor wins.
    assert find_predecessor_video_element(timeline, target) is first


def test_continuity_reference_ids_is_empty_for_first_segment() -> None:
    first = _element("e1", start=0)
    project, timeline = _project([first])

    assert continuity_reference_ids(project, timeline, first) == ()


def test_continuity_reference_ids_empty_until_prev_video_selected() -> None:
    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])

    # Predecessor exists but its main slot has no selected version yet:
    # the successor cannot pull anchors, so we keep the reference plan
    # identical to the pre-continuity behavior.
    assert continuity_reference_ids(project, timeline, second) == ()


def test_continuity_reference_ids_uses_prev_selected_version() -> None:
    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    project.assets.artifact_slots_by_id["element:e1:main"] = ArtifactSlot(
        slot_id="element:e1:main",
        owner_ref="element:e1",
        kind="element_video",
        version_ids=["prev-version-1"],
        selected_version_id="prev-version-1",
    )

    ids = continuity_reference_ids(project, timeline, second)
    assert ids == (
        "continuity:last_frame:prev-version-1",
        "continuity:tail_clip:prev-version-1",
    )
    assert (
        resolve_predecessor_video_version(project, first) == "prev-version-1"
    )


def test_supports_video_continuation_only_fires_for_wan3_family() -> None:
    assert supports_video_continuation("wan3.0-video") is True
    assert supports_video_continuation("wan3.0-video-prime") is True
    # Wan2.7 documents first_clip on i2v only, not on the r2v request
    # shape this executor uses; happyhorse/veo/kling carry no video refs.
    assert supports_video_continuation("wan2.7-r2v") is False
    assert supports_video_continuation("happyhorse-1.1-r2v") is False
    assert supports_video_continuation("veo-3.1-fast") is False
    assert supports_video_continuation("") is False


def test_continuity_prompt_suffix_wan3_shape() -> None:
    suffix = continuity_prompt_suffix(
        last_frame_index=4,
        tail_clip_index=1,
    )
    assert "[Image 4]" in suffix
    assert "视频1" in suffix
    assert "向后延长" in suffix
    assert "上一段末帧" in suffix
    # N-6: guidance stays firm but not absolute — an over-hard "必须/严格"
    # contract makes the model freeze on the anchor instead of continuing.
    assert "严格对齐" not in suffix


def test_continuity_prompt_suffix_uses_computed_video_index() -> None:
    """Regression for #7: the caller's computed ``tail_clip_index`` must
    actually reach the wire prompt (previous builds fell through to a
    ``tail_clip_label="1"`` default, silently keeping the hard-coded
    ordinal even after project video refs grew past one).
    """

    suffix = continuity_prompt_suffix(
        last_frame_index=6,
        tail_clip_index=3,
    )
    assert "将视频3向后延长" in suffix
    assert "[Image 6]" in suffix
    assert "视频1" not in suffix


def test_continuity_prompt_suffix_fallback_shape() -> None:
    suffix = continuity_prompt_suffix(
        last_frame_index=3,
        tail_clip_index=None,
    )
    assert "[Image 3]" in suffix
    assert "视频" not in suffix
    assert "起始状态" in suffix
    assert "必须" not in suffix


def test_i2v_explicit_first_frame_unlocks_via_public_work_graph() -> None:
    """Explicit user input always unlocks readiness regardless of prev;
    asserted through ``derive_work_graph`` so the gate helper stays a
    private implementation detail (Nit #9)."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        derive_work_graph,
    )

    explicit = _element("e1", start=0, creation_type="i2v")
    explicit.creation.first_frame_version_id = "user-chosen-frame"
    project, _timeline = _project([explicit])

    graph = derive_work_graph(project)
    node = graph.by_id["video:e1"]
    assert node.status is WorkNodeStatus.READY
    assert "first_frame" not in " ".join(node.missing)


def test_fingerprint_unchanged_when_no_predecessor_present() -> None:
    """Regression for B1: pre-continuity FAILED nodes must not silently
    re-qualify for a paid reroll when the fingerprint picks up a new
    empty tail element. Compared against the literal tuple shape the
    function produced before segment-continuity landed, not against
    another call to the current code, so a future regression that
    re-introduces ``(prev_slot_part,)`` without ``*`` still fails here.
    White-box by necessity: the public ``dispatch_fingerprint`` is a
    hash, and a hash cannot distinguish a nested ``()`` from a flat
    tuple — only the raw parts expose the exact shape B1 broke.
    """

    from services.file_agent_runtime.work_graph import _video_fingerprint_parts

    # ---- R2V ---------------------------------------------------------
    r2v_creation = R2VCreation(
        narrative="动作",
        storyboard_prompt="分镜",
        video_prompt="视频",
    )
    legacy_r2v = (
        "video:elem",
        "视频",
        "storyboard-slot-1",
        [],
    )
    assert (
        _video_fingerprint_parts(
            "r2v",
            r2v_creation,
            "video:elem",
            "storyboard-slot-1",
        )
        == legacy_r2v
    )
    assert (
        _video_fingerprint_parts(
            "r2v",
            r2v_creation,
            "video:elem",
            "storyboard-slot-1",
            prev_video_slot=None,
        )
        == legacy_r2v
    )
    assert (
        _video_fingerprint_parts(
            "r2v",
            r2v_creation,
            "video:elem",
            "storyboard-slot-1",
            prev_video_slot="",
        )
        == legacy_r2v
    )
    with_prev_r2v = _video_fingerprint_parts(
        "r2v",
        r2v_creation,
        "video:elem",
        "storyboard-slot-1",
        prev_video_slot="prev-video-slot-1",
    )
    assert with_prev_r2v != legacy_r2v
    # The marker must actually flatten into the tuple, not nest as a
    # single ``()`` entry that ``str()`` renders as an empty pair of
    # parentheses and silently drifts the fingerprint hash.
    assert with_prev_r2v[-2:] == ("prev_video_slot", "prev-video-slot-1")
    assert all(isinstance(item, (str, list, tuple)) for item in with_prev_r2v)
    assert () not in with_prev_r2v

    # ---- I2V ---------------------------------------------------------
    i2v_creation = I2VCreation(video_prompt="续写")
    legacy_i2v = (
        "video:elem",
        "续写",
        None,
    )
    assert (
        _video_fingerprint_parts(
            "i2v",
            i2v_creation,
            "video:elem",
            None,
        )
        == legacy_i2v
    )
    assert (
        _video_fingerprint_parts(
            "i2v",
            i2v_creation,
            "video:elem",
            None,
            prev_video_slot=None,
        )
        == legacy_i2v
    )
    with_prev_i2v = _video_fingerprint_parts(
        "i2v",
        i2v_creation,
        "video:elem",
        None,
        prev_video_slot="prev-video-slot-1",
    )
    assert with_prev_i2v[-2:] == ("prev_video_slot", "prev-video-slot-1")
    assert () not in with_prev_i2v


def test_budget_function_counts_continuity_media(monkeypatch) -> None:
    """Regression for Blocker #1: ``_assert_r2v_reference_budget`` must
    reject a Wan3.0 request whose tail clip pushes the video reference
    count past the family cap, even though synthetic ``continuity:*``
    IDs never resolve through the Asset Index."""

    from models import config as model_config
    from services.media_files.r2v_execution import (
        VideoReferenceBudgetError,
        _assert_r2v_reference_budget,
    )

    # Force Wan3.0 (max_reference_videos=5) so six declared clips fail.
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")

    project = Project.new(project_id="p-budget", name="Budget")
    fake_ids = tuple(f"continuity:tail_clip:v{index}" for index in range(6))
    fake_media = [("video", 1.0) for _ in fake_ids]
    with pytest.raises(VideoReferenceBudgetError):
        _assert_r2v_reference_budget(
            project,
            fake_ids,
            output_duration_seconds=4,
            continuity_media=fake_media,
        )
    # Five clips (matching Wan3.0 max_reference_videos) must pass when
    # the caller declares them via ``continuity_media``, proving the
    # synthetic IDs reach the same cap the Asset Index entries face.
    ok_media = [("video", 1.0) for _ in range(5)]
    ok_ids = tuple(f"continuity:tail_clip:v{index}" for index in range(5))
    _assert_r2v_reference_budget(
        project,
        ok_ids,
        output_duration_seconds=4,
        continuity_media=ok_media,
    )


def _select_prev_video(
    project: Project,
    prev_element_id: str,
    version: str,
) -> None:
    project.assets.artifact_slots_by_id[
        f"element:{prev_element_id}:main"
    ] = ArtifactSlot(
        slot_id=f"element:{prev_element_id}:main",
        owner_ref=f"element:{prev_element_id}",
        kind="element_video",
        version_ids=[version],
        selected_version_id=version,
    )


def test_submission_reference_ids_include_i2v_continuity_fallback() -> None:
    """Regression for M1: I2V without an authored first_frame picks up
    the predecessor's synthetic ``continuity:last_frame:*`` ID in the
    submission fingerprint, so a prev segment regenerated between
    ADMIT and SUBMIT invalidates the claim instead of paying out on a
    stale anchor."""

    from services.media_files.r2v_execution import (
        _reference_ids_with_continuity,
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000, creation_type="i2v")
    project, timeline = _project([first, second])

    # Prev video not yet published: I2V fingerprint keeps its pre-PR
    # shape (empty refs) so historical FAILED nodes do not drift.
    assert _reference_ids_with_continuity(project, timeline, second) == ()

    # Prev video selected: last-frame ID flows into the fingerprint.
    _select_prev_video(project, "e1", "prev-version-1")
    refs = _reference_ids_with_continuity(project, timeline, second)
    assert refs == ("continuity:last_frame:prev-version-1",)


def test_submission_reference_ids_unchanged_for_i2v_explicit_frame() -> None:
    from services.media_files.r2v_execution import (
        _reference_ids_with_continuity,
    )

    first = _element("e1", start=0)
    explicit = _element("e2", start=4000, creation_type="i2v")
    explicit.creation.first_frame_version_id = "user-authored-frame"
    project, timeline = _project([first, explicit])
    _select_prev_video(project, "e1", "prev-version-1")

    # Explicit user input lives in ``creation`` inside the fingerprint
    # payload; the reference list must stay empty for backward
    # compatibility with pre-PR tasks.
    assert _reference_ids_with_continuity(project, timeline, explicit) == ()


def test_atomic_run_writes_tmp_then_replaces_final(
    tmp_path,
    monkeypatch,
) -> None:
    """Regression for Minor #4: the atomic rename guard mustn't leave
    concurrent writers half-written on the final path — a fake
    ffmpeg that populates only the tmp target proves ``os.replace``
    moves the completed bytes and no residue lingers afterwards."""

    from services.media_files import segment_continuity as sc

    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    final = tmp_path / "last_frame.png"

    def fake_run(cmd, **kwargs):  # noqa: ARG001 - mirrors subprocess.run
        output = Path(cmd[-1])
        output.write_bytes(b"fake-png")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)

    sc._atomic_run(
        lambda tmp, ff: sc._extract_last_frame_into(source, ff, tmp),
        final,
        "/usr/bin/ffmpeg",
    )

    assert final.exists()
    assert final.read_bytes() == b"fake-png"
    # No residue under the tmp suffix: either os.replace moved it or
    # finally cleaned up. Both together guarantee the sha256 path
    # never observes a partial file.
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_atomic_run_temp_keeps_real_extension(tmp_path) -> None:
    """Regression for the shipped-anchor bug: ffmpeg picks its output muxer
    from the filename extension, so the private temp name must end in the
    *real* suffix. The old ``with_suffix('.png.tmp.<pid>.<tid>')`` left a
    ``.tid`` extension, and every last-frame / tail-clip cut failed with
    'Unable to find a suitable output format' — silently dropping all
    continuity anchors. Capture the tmp path handed to the extractor and
    assert the extension survives for both image and video outputs."""

    from services.media_files import segment_continuity as sc

    seen: list[Path] = []

    def record(tmp: Path, _ff: str) -> None:
        seen.append(tmp)
        tmp.write_bytes(b"bytes")

    sc._atomic_run(record, tmp_path / "last_frame.png", "/usr/bin/ffmpeg")
    sc._atomic_run(record, tmp_path / "tail_clip.mp4", "/usr/bin/ffmpeg")

    assert [p.suffix for p in seen] == [".png", ".mp4"]
    # Uniqueness markers still precede the extension (collision-free).
    assert ".tmp." in seen[0].name
    assert (tmp_path / "last_frame.png").exists()
    assert (tmp_path / "tail_clip.mp4").exists()


def test_i2v_gate_opens_via_public_work_graph() -> None:
    """Nit #9 follow-up: exercise the readiness transition through
    ``derive_work_graph`` rather than poking the private gate helper,
    so a signature refactor that keeps the public API stable cannot
    silently bypass this behaviour."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        derive_work_graph,
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000, creation_type="i2v")
    project, _timeline = _project([first, second])

    # No prev video: I2V node stays GATED with a first_frame reason.
    graph = derive_work_graph(project)
    node = graph.by_id["video:e2"]
    assert node.status is WorkNodeStatus.GATED
    assert any("first_frame" in reason for reason in node.missing)

    # Prev video selected (I2V needs only the last frame, so we do
    # not have to fake an ffmpeg run: the graph only checks slot
    # selection to lift the gate).
    _select_prev_video(project, "e1", "prev-version-1")
    graph = derive_work_graph(project)
    node = graph.by_id["video:e2"]
    assert "first_frame" not in " ".join(node.missing)


def _frame_entry(tmp_path: Path, prev_version: str = "prev-version-1"):
    from services.media_files import segment_continuity as sc

    png = tmp_path / "last_frame.png"
    png.write_bytes(b"fake-png")
    return sc._build_entry(
        "last_frame",
        path=png,
        prev_version=prev_version,
        prev_element_id="e1",
        media_type="image/png",
        role_label="上一段末帧",
    )


def test_entry_identifiers_share_underscore_naming(tmp_path) -> None:
    """m2: reference_id and provenance_ref must spell the kind the same
    way (both underscore), so grep/trace filters on ``continuity:``
    prefixes do not split across two naming conventions."""

    from services.media_files import segment_continuity as sc

    frame = _frame_entry(tmp_path)
    assert frame.reference_id == "continuity:last_frame:prev-version-1"
    assert frame.provenance_ref == "continuity:last_frame:e1"

    clip_path = tmp_path / "tail_clip.mp4"
    clip_path.write_bytes(b"fake-clip")
    tail = sc._build_entry(
        "tail_clip",
        path=clip_path,
        prev_version="prev-version-1",
        prev_element_id="e1",
        media_type="video/mp4",
        role_label="上一段尾段",
        duration_seconds=3.0,
    )
    assert tail.reference_id == "continuity:tail_clip:prev-version-1"
    assert tail.provenance_ref == "continuity:tail_clip:e1"


def test_read_entry_matches_non_indexed_reference_shape(tmp_path) -> None:
    """m3: the continuity read entry follows the same non-indexed
    convention as remote-URL references (``fileId=None`` paired with a
    ``sourceUrl``), not a divergent third shape."""

    entry = _frame_entry(tmp_path)
    read = entry.as_read_entry()
    assert set(read) == {"ref", "versionId", "fileId", "checksum", "sourceUrl"}
    assert read["fileId"] is None
    assert read["sourceUrl"] == entry.url
    assert read["versionId"] == entry.reference_id
    assert read["ref"] == entry.provenance_ref
    assert read["checksum"] == entry.checksum


def test_lru_eviction_retires_extract_locks(tmp_path, monkeypatch) -> None:
    """m1: evicting a cache entry must also retire its per-key extract
    lock under ``_continuity_locks_guard``, and a cache hit must not
    re-cut. The ffmpeg/asset-index layers are mocked so the test
    exercises only the cache/lock machinery."""

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc
    import services.runtime_files.runtime_dependencies as rd

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    _select_prev_video(project, "e1", "v1")

    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    entry = _frame_entry(tmp_path, prev_version="v1")
    cuts: list[dict] = []

    monkeypatch.setattr(rd, "resolve_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        rd,
        "resolve_ffprobe",
        lambda ffmpeg_path: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        sc,
        "_resolve_prev_video_path",
        lambda *a, **k: source,
    )
    monkeypatch.setattr(
        sc,
        "_cut_last_frame",
        lambda **kwargs: cuts.append(kwargs) or (entry,),
    )
    monkeypatch.setattr(sc, "_CACHE_MAX_ITEMS", 1)
    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    monkeypatch.setattr(sc, "_continuity_extract_locks", {})

    def extract():
        return sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=second,
        )

    bundle_v1 = extract()
    assert bundle_v1 is not None
    assert len(cuts) == 1
    key_v1 = ("v1", "/usr/bin/ffmpeg")
    assert key_v1 in sc._continuity_extract_locks

    # Same predecessor version: double-check cache hit, no re-cut.
    assert extract() is bundle_v1
    assert len(cuts) == 1

    # New selected version evicts v1 from BOTH the cache and the lock
    # map (max items = 1).
    _select_prev_video(project, "e1", "v2")
    bundle_v2 = extract()
    assert bundle_v2 is not None
    assert bundle_v2.predecessor_video_version_id == "v2"
    assert len(cuts) == 2
    assert key_v1 not in sc._continuity_cache
    assert key_v1 not in sc._continuity_extract_locks
    assert ("v2", "/usr/bin/ffmpeg") in sc._continuity_extract_locks


def test_design_skips_emit_trace(tmp_path, monkeypatch) -> None:
    """m4: the silent ``return None`` branches (first segment, prev not
    published) must leave a trace explaining why no anchor was cut."""

    import services.observability as obs
    from services.media_files import segment_continuity as sc

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        obs,
        "trace_event",
        lambda name, **kw: events.append((name, kw)),
    )

    # First segment: no predecessor at all.
    lone = _element("e2", start=4000)
    project, timeline = _project([lone])
    assert (
        sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=lone,
        )
        is None
    )

    # Predecessor exists but its video is not published yet.
    first = _element("e1", start=0)
    project, timeline = _project([first, lone])
    assert (
        sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=lone,
        )
        is None
    )

    reasons = [
        kw["attributes"]["reason"]
        for name, kw in events
        if name == "creator.continuity.skipped"
    ]
    assert reasons == ["no_predecessor", "predecessor_unpublished"]
    assert all(kw["component"] == "continuity" for _n, kw in events)
    assert events[1][1]["prev_element_id"] == "e1"


def test_tail_clip_enabled_env_switch(monkeypatch) -> None:
    """The operator dial is pure-env: on by default, off on 0/false/no/off
    (case/whitespace insensitive), so linkage can be demoted to image-only
    without a code change."""

    from services.media_files.segment_continuity import tail_clip_enabled

    monkeypatch.delenv("CREATOR_CONTINUITY_TAIL_CLIP", raising=False)
    assert tail_clip_enabled() is True
    monkeypatch.setenv("CREATOR_CONTINUITY_TAIL_CLIP", "1")
    assert tail_clip_enabled() is True
    for off in ("0", "false", "off", "NO", " Off "):
        monkeypatch.setenv("CREATOR_CONTINUITY_TAIL_CLIP", off)
        assert tail_clip_enabled() is False


def test_i2v_auto_first_frame_adopts_prev_last_frame(
    tmp_path,
    monkeypatch,
) -> None:
    """The extracted I2V fallback helper: design skips return None
    without touching ffmpeg; a published prev yields the last frame."""

    import services.media_files.r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityBundle

    calls: list[dict] = []
    entry = _frame_entry(tmp_path)

    def fake_extract(**kwargs):
        calls.append(kwargs)
        return ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(entry,),
        )

    monkeypatch.setattr(rx, "extract_continuity_artifacts", fake_extract)

    # Lone I2V element: no predecessor, no extract attempt.
    lone = _element("e2", start=4000, creation_type="i2v")
    project, timeline = _project([lone])
    assert (
        rx._i2v_auto_first_frame_entry(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=lone,
        )
        is None
    )
    assert calls == []

    # Predecessor present but unpublished: still no extract attempt.
    first = _element("e1", start=0)
    project, timeline = _project([first, lone])
    assert (
        rx._i2v_auto_first_frame_entry(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=lone,
        )
        is None
    )
    assert calls == []

    # Published prev: the last frame becomes the first-frame input,
    # and I2V never asks for a tail clip.
    _select_prev_video(project, "e1", "prev-version-1")
    adopted = rx._i2v_auto_first_frame_entry(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=lone,
    )
    assert adopted is entry
    assert len(calls) == 1


def test_i2v_auto_first_frame_reports_failure_and_invariant(
    tmp_path,
    monkeypatch,
) -> None:
    """m4: extraction failure and a last-frame-less bundle both report
    through i2v.continuity instead of disappearing into the fallback."""

    import services.media_files.r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityBundle

    reports: list[dict] = []
    monkeypatch.setattr(rx, "report_error", lambda **kw: reports.append(kw))

    first = _element("e1", start=0)
    second = _element("e2", start=4000, creation_type="i2v")
    project, timeline = _project([first, second])
    _select_prev_video(project, "e1", "prev-version-1")

    def run_helper():
        return rx._i2v_auto_first_frame_entry(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=second,
        )

    def boom(**kwargs):
        raise RuntimeError("ffmpeg 不可用")

    monkeypatch.setattr(rx, "extract_continuity_artifacts", boom)
    assert run_helper() is None
    assert reports[-1]["code"] == "CONTINUITY_EXTRACTION_FAILED"
    assert reports[-1]["component"] == "i2v.continuity"

    monkeypatch.setattr(
        rx,
        "extract_continuity_artifacts",
        lambda **kw: ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(),
        ),
    )
    assert run_helper() is None
    assert reports[-1]["code"] == "CONTINUITY_LAST_FRAME_MISSING"
    assert reports[-1]["component"] == "i2v.continuity"
    assert reports[-1]["prev_element_id"] == "e1"


def _publish_artifact(
    project: Project,
    element_id: str,
    version_id: str,
    *,
    stale: bool = False,
    media_type: str = "video/mp4",
) -> None:
    """Select a published artifact version on one element's main slot."""

    from services.project_files.models import ArtifactVersion, IndexedFile

    slot_id = f"element:{element_id}:main"
    project.assets.artifact_slots_by_id[slot_id] = ArtifactSlot(
        slot_id=slot_id,
        owner_ref=f"element:{element_id}",
        kind="element_video",
        version_ids=[version_id],
        selected_version_id=version_id,
    )
    project.assets.files_by_id[f"file-{version_id}"] = IndexedFile(
        file_id=f"file-{version_id}",
        kind="artifact_payload",
        media_type=media_type,
        relative_uri=f"assets/artifacts/file-{version_id}",
        sha256="0" * 64,
        size_bytes=1,
        created_at="2026-08-05T00:00:00Z",
    )
    project.assets.artifact_versions_by_id[version_id] = ArtifactVersion(
        version_id=version_id,
        name=version_id,
        slot_id=slot_id,
        kind="element_video",
        owner_ref=f"element:{element_id}",
        file_id=f"file-{version_id}",
        checksum="0" * 64,
        based_on_generation=1,
        provenance_refs=[],
        stale=stale,
        created_at="2026-08-05T00:00:00Z",
    )


def _mock_ffmpeg_paths(monkeypatch) -> None:
    import services.runtime_files.runtime_dependencies as rd

    monkeypatch.setattr(rd, "resolve_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        rd,
        "resolve_ffprobe",
        lambda ffmpeg_path: "/usr/bin/ffprobe",
    )


def _two_segment_project(prev_version: str | None = None):
    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    if prev_version:
        _select_prev_video(project, "e1", prev_version)
    return project, timeline, first, second


def test_run_converts_subprocess_and_os_errors(monkeypatch) -> None:
    """N-1: TimeoutExpired / OSError from subprocess.run must converge
    into RuntimeError, otherwise a hung or unrunnable ffmpeg escapes
    every best-effort catch and hard-fails the paid render."""

    import subprocess as sp

    from services.media_files import segment_continuity as sc

    def raise_timeout(cmd, **kwargs):  # noqa: ARG001
        raise sp.TimeoutExpired(cmd=cmd, timeout=1)

    monkeypatch.setattr(sc.subprocess, "run", raise_timeout)
    with pytest.raises(RuntimeError):
        sc._run(["ffmpeg"], timeout=1)

    def raise_oserror(cmd, **kwargs):  # noqa: ARG001
        raise PermissionError(13, "denied")

    monkeypatch.setattr(sc.subprocess, "run", raise_oserror)
    with pytest.raises(RuntimeError):
        sc._run(["ffmpeg"], timeout=1)


def test_extract_converts_disk_oserror_to_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    """N-1: disk failures under the extraction lock (full disk, bad
    permissions) must surface as RuntimeError so callers keep their
    skip-and-generate fallback."""

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    project, timeline, _first, second = _two_segment_project("v1")
    _mock_ffmpeg_paths(monkeypatch)
    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    monkeypatch.setattr(sc, "_continuity_extract_locks", {})
    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    monkeypatch.setattr(
        sc,
        "_resolve_prev_video_path",
        lambda *a, **k: source,
    )

    def boom(**kwargs):  # noqa: ARG001
        raise PermissionError(28, "no space left on device")

    monkeypatch.setattr(sc, "_cut_last_frame", boom)
    with pytest.raises(RuntimeError, match="no space"):
        sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=second,
        )


def test_prune_removes_old_unreferenced_dirs(tmp_path, monkeypatch) -> None:
    """N-2: extract directories no cache entry references anymore are
    collected once quiet for the grace window; fresh directories and
    the extract in flight stay."""

    import os
    import time

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    root = tmp_path / "runtime" / "continuity"
    stale_dir = root / ("a" * 16)
    fresh_dir = root / ("b" * 16)
    current_dir = root / ("c" * 16)
    for directory in (stale_dir, fresh_dir, current_dir):
        directory.mkdir(parents=True)
        (directory / "tail_clip.mp4").write_bytes(b"x" * 10)
    old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
    os.utime(stale_dir, (old, old))
    os.utime(current_dir, (old, old))

    removed = sc._prune_continuity_dirs(tmp_path, current_digest="c" * 16)
    assert removed == 1
    assert not stale_dir.exists()
    assert fresh_dir.exists()
    assert current_dir.exists()


def test_predecessor_skips_overlapping_candidate() -> None:
    """N-6: a candidate still playing when the target starts cannot
    anchor it — its last frame happens after this segment opens, so
    the seam would point at a frame that has not occurred yet."""

    early = _element("e0", start=0, duration=2000)
    overlap = _element("e1", start=1000, duration=6000)
    target = _element("e2", start=4000)
    _proj, timeline = _project([early, overlap, target])
    assert find_predecessor_video_element(timeline, target) is early


def test_video_edit_fingerprint_ignores_continuity() -> None:
    """N-3②: video_edit consumes one videoRef, never the continuity
    anchors; counting them in its frozen fingerprint would fail the
    claim on every prev reroll and re-queue a paid render."""

    from services.media_files.r2v_execution import (
        _reference_ids_with_continuity,
        _submission_input_fingerprint,
    )
    from services.media_files.visual_reference_resolution import (
        video_reference_plan,
    )

    project, timeline, _first, second = _two_segment_project("prev-version-1")
    r2v_ids = _reference_ids_with_continuity(project, timeline, second)
    edit_ids = _reference_ids_with_continuity(
        project,
        timeline,
        second,
        mode="video_edit",
    )
    # Strong-continuity r2v now DOES lead the stack with the promoted
    # anchor id (the planner routes this same-scene pair onto it), while
    # video_edit still never sees a continuity input.
    assert r2v_ids and r2v_ids[0].startswith("continuity:")
    assert not any(item.startswith("continuity:") for item in edit_ids)
    assert edit_ids == video_reference_plan(project, second)

    before = _submission_input_fingerprint(project, "e2", mode="video_edit")
    _select_prev_video(project, "e1", "prev-version-2")
    after = _submission_input_fingerprint(project, "e2", mode="video_edit")
    assert before == after
    # Control: the first-class extend mode DOES track the prev version
    # (its only continuity input is the predecessor's real artifact),
    # while strong-continuity r2v now leads its own promoted anchor id —
    # a shape distinct from both video_edit and extend.
    assert (
        _submission_input_fingerprint(
            project,
            "e2",
            mode="video_extend",
        )
        != before
    )
    assert _submission_input_fingerprint(project, "e2") != before


def test_explicit_frame_i2v_skips_prev_chain() -> None:
    """N-3①③: an I2V Element with an authored first frame never reads
    the predecessor — it must not be gated behind the prev video, and
    publishing/rerolling prev must not shift its dispatch fingerprint
    (which would re-qualify parked FAILED nodes for a paid rerun)."""

    from services.file_agent_runtime.work_graph import derive_work_graph

    first = _element("e1", start=0)
    explicit = _element("e2", start=4000, creation_type="i2v")
    explicit.creation.first_frame_version_id = "frame-e2"
    project, _timeline = _project([first, explicit])

    before = derive_work_graph(project).by_id["video:e2"]
    _select_prev_video(project, "e1", "prev-version-1")
    after = derive_work_graph(project).by_id["video:e2"]
    assert "video:e1" not in before.deps
    assert "video:e1" not in after.deps
    assert before.dispatch_fingerprint == after.dispatch_fingerprint

    # Control: the auto-frame sibling does chain and does shift.
    auto = _element("e3", start=8000, creation_type="i2v")
    project2, _t2 = _project([_element("e1", start=0), auto])
    before2 = derive_work_graph(project2).by_id["video:e3"]
    _select_prev_video(project2, "e1", "prev-version-1")
    after2 = derive_work_graph(project2).by_id["video:e3"]
    assert "video:e1" in after2.deps
    assert before2.dispatch_fingerprint != after2.dispatch_fingerprint


def _failed_video_task(
    target: str,
    key: str,
    message: str = "provider rejected",
):
    from types import SimpleNamespace

    from domain.enums import TaskStatus

    return SimpleNamespace(
        task_id=f"task-{target}",
        kind="r2v_generation",
        status=TaskStatus.FAILED,
        input_refs=[target],
        metadata={"targetRef": target},
        progress=None,
        error={"message": message},
        updated_at="2026-08-05T00:00:00Z",
        idempotency_key=key,
    )


def test_parked_failure_survives_continuity_upgrade() -> None:
    """N-4 + N-8: a FAILED node parked before segment continuity landed
    carries a digest without the prev_video_slot marker. After the
    upgrade it must stay FAILED (the legacy digest is still accepted,
    so the rollout is not re-billed as an input edit) and keep showing
    its own error even while the predecessor is unpublished mid-reroll
    (own failure outranks the continuity GATED)."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        _fingerprint,
        _video_fingerprint_parts,
        derive_work_graph,
        dispatch_ledger_fingerprint,
        dispatch_slot,
    )

    project, _timeline = _project(
        [
            _element("e1", start=0),
            _element("e2", start=4000, creation_type="i2v"),
        ],
    )
    second = project.timelines.items["timeline:main"].elements_by_id["e2"]
    _select_prev_video(project, "e1", "prev-version-1")
    media_models = ("image-model", "video-model")
    legacy = _fingerprint(
        *_video_fingerprint_parts("i2v", second.creation, "video:e2", None),
    )
    ledger = dispatch_ledger_fingerprint(legacy, media_models)
    task = _failed_video_task(
        "element:e2",
        f"dag-video:e2-{dispatch_slot(ledger)}",
    )

    graph = derive_work_graph(project, tasks=[task], media_models=media_models)
    node = graph.by_id["video:e2"]
    assert node.status is WorkNodeStatus.FAILED
    assert "provider rejected" in (node.error or "")

    # A real input change re-opens the node even with the legacy
    # fallback: neither digest family matches the parked key any more.
    second.creation.video_prompt = "rewritten continuation"
    graph = derive_work_graph(project, tasks=[task], media_models=media_models)
    assert graph.by_id["video:e2"].status is not WorkNodeStatus.FAILED


def test_ffmpeg_unavailable_gates_i2v_auto_frame() -> None:
    """N-7: with the environment probed and ffmpeg missing, the auto
    first-frame path cannot run; the node must say so instead of
    dispatching into a misleading submit-time failure."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        derive_work_graph,
    )

    first = _element("e1", start=0, creation_type="i2v")
    first.creation.first_frame_version_id = "frame-e1"
    second = _element("e2", start=4000, creation_type="i2v")
    project, _timeline = _project([first, second])
    _publish_artifact(project, "e1", "prev-version-1")

    optimistic = derive_work_graph(project).by_id["video:e2"]
    assert optimistic.status is WorkNodeStatus.READY

    gated = derive_work_graph(project, ffmpeg_ready=False).by_id["video:e2"]
    assert gated.status is WorkNodeStatus.GATED
    assert any("ffmpeg" in reason for reason in gated.missing)


def test_ffmpeg_probe_never_regates_done_i2v() -> None:
    """N-7 guard: the environment probe may only steer nodes that still
    need dispatching. An i2v auto-frame node whose clip is already
    published stays DONE even when ffmpeg is currently unavailable —
    gating it would hide a finished artifact behind an env warning."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        derive_work_graph,
    )

    first = _element("e1", start=0, creation_type="i2v")
    first.creation.first_frame_version_id = "frame-e1"
    second = _element("e2", start=4000, creation_type="i2v")
    project, _timeline = _project([first, second])
    _publish_artifact(project, "e1", "prev-version-1")
    # e2 has its own published clip already (auto-framed in a prior run).
    _publish_artifact(project, "e2", "self-version-1")

    done = derive_work_graph(project, ffmpeg_ready=False).by_id["video:e2"]
    assert done.status is WorkNodeStatus.DONE


def test_stale_missing_excludes_foreign_deps() -> None:
    """N-9: the STALE branch lists only this node's own dependency
    families. ``deps`` is built in the r2v branch alone; reading it
    for a later i2v element used to leak the previous iteration's
    lineup dependency into this node's missing list."""

    from services.file_agent_runtime.work_graph import (
        WorkNodeStatus,
        derive_work_graph,
    )

    first = _element("e1", start=0)
    first.creation.cast_lineup_refs = ["lineup:x"]
    second = _element("e2", start=4000, creation_type="i2v")
    second.creation.first_frame_version_id = "frame-e2"
    project, _timeline = _project([first, second])
    _publish_artifact(project, "e2", "art-e2", stale=True)

    graph = derive_work_graph(project)
    node = graph.by_id["video:e2"]
    assert node.status is WorkNodeStatus.STALE
    assert node.missing == ()


def test_atomic_run_failure_leaves_no_final_or_residue(tmp_path) -> None:
    """N-10: a failing extract must leave neither a half-written final
    nor tmp residue — the success-path test alone cannot tell the
    atomic dance apart from a plain write."""

    from services.media_files import segment_continuity as sc

    final = tmp_path / "last_frame.png"

    def extract(tmp, ff):  # noqa: ARG001
        Path(tmp).write_bytes(b"partial")
        raise RuntimeError("ffmpeg died mid-frame")

    with pytest.raises(RuntimeError):
        sc._atomic_run(extract, final, "/usr/bin/ffmpeg")
    assert not final.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_number_references_by_media_counts_per_type() -> None:
    """The shared numbering tallies images and videos in independent
    sequences, dedupes like the submit resolver, and honours
    force_video for synthetic anchors the Asset Index cannot see."""

    from services.media_files.visual_reference_resolution import (
        number_references_by_media,
    )

    project = Project.new(project_id="p-num", name="Num")
    _publish_artifact(project, "a", "img-1", media_type="image/png")
    _publish_artifact(project, "b", "vid-1", media_type="video/mp4")
    _publish_artifact(project, "c", "vid-2", media_type="video/mp4")
    assert number_references_by_media(
        project,
        ["img-1", "vid-1", "img-1", "unknown", "vid-2"],
    ) == [
        ("img-1", "image", 1),
        ("vid-1", "video", 1),
        # deduped: the repeated img-1 does not re-tally, and unknown
        # ids fall back to the image sequence
        ("unknown", "image", 2),
        ("vid-2", "video", 2),
    ]
    assert number_references_by_media(
        project,
        ["continuity:last_frame:v1", "continuity:tail_clip:v1"],
        force_video={"continuity:tail_clip:v1"},
    ) == [
        ("continuity:last_frame:v1", "image", 1),
        ("continuity:tail_clip:v1", "video", 1),
    ]


def test_cache_hit_refreshes_lru_order(tmp_path, monkeypatch) -> None:
    """N-13: hits must refresh recency; otherwise the cache is a FIFO
    and a hot predecessor gets evicted while idle entries survive."""

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    project, timeline, _first, second = _two_segment_project()
    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    entry = _frame_entry(tmp_path)
    _mock_ffmpeg_paths(monkeypatch)
    monkeypatch.setattr(
        sc,
        "_resolve_prev_video_path",
        lambda *a, **k: source,
    )
    monkeypatch.setattr(sc, "_cut_last_frame", lambda **kw: (entry,))
    monkeypatch.setattr(sc, "_CACHE_MAX_ITEMS", 2)
    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    monkeypatch.setattr(sc, "_continuity_extract_locks", {})

    def extract(version: str):
        _select_prev_video(project, "e1", version)
        return sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=second,
        )

    extract("v1")
    extract("v2")
    extract("v1")  # cache hit refreshes v1's recency
    extract("v3")  # evicts the true LRU entry: v2
    assert {key[0] for key in sc._continuity_cache} == {"v1", "v3"}


def test_prune_keeps_cached_dir_past_grace(tmp_path, monkeypatch) -> None:
    """Nit: the ``_cached_digests()`` guard must protect a directory the
    in-memory cache still references even once its mtime is past the
    grace window — otherwise GC could delete an anchor a live submit is
    about to read. This is the branch the basic prune test (which clears
    the cache first) never exercises."""

    import os
    import time

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    cached_version = "vCached"
    digest = sc._digest_for(cached_version)
    monkeypatch.setattr(
        sc,
        "_continuity_cache",
        OrderedDict({(cached_version, "/usr/bin/ffmpeg", False): object()}),
    )
    root = tmp_path / "runtime" / "continuity"
    cached_dir = root / digest
    cached_dir.mkdir(parents=True)
    (cached_dir / "last_frame.png").write_bytes(b"x")
    old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
    os.utime(cached_dir, (old, old))

    removed = sc._prune_continuity_dirs(tmp_path, current_digest="other")
    assert removed == 0
    assert cached_dir.exists()


def test_sweep_orphaned_continuity_collects_idle_projects(
    tmp_path,
    monkeypatch,
) -> None:
    """Minor-1: the maintenance sweep reclaims continuity residue for
    Projects that stopped generating and so never run the event-driven
    prune again. Mirrors release_orphaned_scratch for the continuity root."""

    import os
    import time

    from collections import OrderedDict
    from types import SimpleNamespace

    from services.media_files import segment_continuity as sc
    import services.runtime_files.execution_store as es

    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())

    class _EmptyStore:
        def __init__(self, root):  # noqa: ARG002
            pass

        def list_tasks(self, project_id):  # noqa: ARG002
            return []

    monkeypatch.setattr(es, "ProjectExecutionStore", _EmptyStore)
    roots = [tmp_path / "projA", tmp_path / "projB"]
    for root in roots:
        digest_dir = root / "runtime" / "continuity" / ("d" * 16)
        digest_dir.mkdir(parents=True)
        (digest_dir / "tail_clip.mp4").write_bytes(b"x" * 10)
        old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
        os.utime(digest_dir, (old, old))

    services = SimpleNamespace(
        root=tmp_path,
        projects=SimpleNamespace(
            discover_project_ids=lambda: ["projA", "projB"],
            project_root=lambda pid: tmp_path / pid,
        ),
    )
    removed = sc.sweep_orphaned_continuity(services)
    assert removed == 2
    for root in roots:
        assert not (root / "runtime" / "continuity" / ("d" * 16)).exists()


def test_frozen_continuity_digests_extracts_prev_versions() -> None:
    """Minor-1: the keep-set builder maps a frozen payload's synthetic
    ``continuity:*:<prev>`` ids (r2v refs and i2v first frame) back to
    their digest dirs, ignoring non-continuity ids."""

    from types import SimpleNamespace

    from services.media_files import segment_continuity as sc

    task = SimpleNamespace(
        metadata={
            "requestSnapshot": {
                "referenceVersionIds": [
                    "sb-v1",
                    "continuity:last_frame:prevV1",
                    "continuity:tail_clip:prevV1",
                ],
                "firstFrameVersionId": "continuity:last_frame:prevV9",
            },
        },
    )
    assert sc._frozen_continuity_digests(task) == {
        sc._digest_for("prevV1"),
        sc._digest_for("prevV9"),
    }
    assert sc._frozen_continuity_digests(SimpleNamespace(metadata={})) == set()


def test_prune_keeps_extra_keep_past_grace(tmp_path, monkeypatch) -> None:
    """Minor-1: ``extra_keep`` (frozen anchors of in-flight tasks)
    survives the grace window even with a cold cache — the startup sweep
    must not delete what a queued render still points at."""

    import os
    import time

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    root = tmp_path / "runtime" / "continuity"
    protected = root / ("e" * 16)
    collectable = root / ("f" * 16)
    for directory in (protected, collectable):
        directory.mkdir(parents=True)
        (directory / "tail_clip.mp4").write_bytes(b"x")
        old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
        os.utime(directory, (old, old))

    removed = sc._prune_continuity_dirs(
        tmp_path,
        current_digest="",
        extra_keep={"e" * 16},
    )
    assert removed == 1
    assert protected.exists()
    assert not collectable.exists()


def test_sweep_orphaned_continuity_protects_inflight_task(
    tmp_path,
    monkeypatch,
) -> None:
    """Policy (2026-11-25): a cold-cache startup sweep keeps EVERY
    digest any task froze — queued, quarantined AND succeeded. Used
    anchors are evidence of what was actually sent (the wire-preview
    view reads them); only unreferenced digests are reclaimable."""

    import os
    import time

    from collections import OrderedDict
    from types import SimpleNamespace

    from domain.enums import TaskStatus
    from services.media_files import segment_continuity as sc
    import services.runtime_files.execution_store as es

    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    root = tmp_path / "projA"
    inflight_prev, done_prev = "prevInflight", "prevDone"
    inflight_dir = (
        root / "runtime" / "continuity" / sc._digest_for(inflight_prev)
    )
    done_dir = root / "runtime" / "continuity" / sc._digest_for(done_prev)
    for directory in (inflight_dir, done_dir):
        directory.mkdir(parents=True)
        (directory / "last_frame.png").write_bytes(b"x")
        old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
        os.utime(directory, (old, old))

    inflight_task = SimpleNamespace(
        status=TaskStatus.QUEUED,
        metadata={
            "requestSnapshot": {
                "referenceVersionIds": [
                    f"continuity:last_frame:{inflight_prev}",
                ],
            },
        },
    )
    # Minor-1: QUARANTINED is terminal but preserved evidence (same
    # convention as is_releasable_terminal_task) — its anchors must stay.
    quarantined_prev = "prevQuarantined"
    quarantined_dir = (
        root / "runtime" / "continuity" / sc._digest_for(quarantined_prev)
    )
    quarantined_dir.mkdir(parents=True)
    (quarantined_dir / "tail_clip.mp4").write_bytes(b"x")
    old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
    os.utime(quarantined_dir, (old, old))
    inflight_task2 = SimpleNamespace(
        status=TaskStatus.QUARANTINED,
        metadata={
            "requestSnapshot": {
                "referenceVersionIds": [
                    "sb-v1",
                    f"continuity:last_frame:{quarantined_prev}",
                    f"continuity:tail_clip:{quarantined_prev}",
                ],
            },
        },
    )
    done_task = SimpleNamespace(
        status=TaskStatus.SUCCEEDED,
        metadata={
            "requestSnapshot": {
                "referenceVersionIds": [f"continuity:last_frame:{done_prev}"],
            },
        },
    )

    class _Store:
        def __init__(self, _root):
            pass

        def list_tasks(self, _project_id):
            return [inflight_task, inflight_task2, done_task]

    monkeypatch.setattr(es, "ProjectExecutionStore", _Store)
    services = SimpleNamespace(
        root=tmp_path,
        projects=SimpleNamespace(
            discover_project_ids=lambda: ["projA"],
            project_root=lambda pid: root,
        ),
    )
    removed = sc.sweep_orphaned_continuity(services)
    assert removed == 0
    assert inflight_dir.exists()
    assert quarantined_dir.exists()
    assert done_dir.exists()
    # Survivors are registered, so later event-driven prunes keep them.
    assert sc._digest_for(inflight_prev) in sc._continuity_inflight
    assert sc._digest_for(quarantined_prev) in sc._continuity_inflight


def _frozen_task(snapshot: dict):
    from types import SimpleNamespace

    return SimpleNamespace(
        task_id="task-inflight",
        project_id="p-continuity",
        kind="r2v_generation",
        status="RUNNING",
        input_refs=["element:e2"],
        metadata={"requestSnapshot": snapshot},
    )


def test_frozen_r2v_publishes_after_prev_reroll() -> None:
    """Major-1: a prev-segment reroll while the successor render is
    in flight (already paid) must not quarantine the finished clip.
    The Project references are unchanged; only the synthetic
    ``continuity:*:prevV`` IDs shifted, and those were the submit
    path's anchors, not a re-billable input edit."""

    from services.media_files.r2v_execution import (
        FileR2VExecutionService,
    )
    from services.project_files.models import ElementOutput

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, _timeline = _project([first, second])
    # Storyboard selected on e2 so the r2v branch can resolve its plan.
    second.outputs["storyboard"] = ElementOutput(
        slot_id="element:e2:storyboard",
    )
    project.assets.artifact_slots_by_id[
        "element:e2:storyboard"
    ] = ArtifactSlot(
        slot_id="element:e2:storyboard",
        owner_ref="element:e2",
        kind="r2v_storyboard_image",
        version_ids=["sb-v1"],
        selected_version_id="sb-v1",
    )
    # Prev published as V1 when the task was admitted.
    _select_prev_video(project, "e1", "prevV1")
    frozen = _frozen_task(
        {
            "elementId": "e2",
            "mode": "r2v",
            "referenceVersionIds": [
                "sb-v1",
                "continuity:last_frame:prevV1",
                "continuity:tail_clip:prevV1",
            ],
        },
    )
    # Predecessor rerolled to V2 mid-render.
    _select_prev_video(project, "e1", "prevV2")

    assert FileR2VExecutionService._frozen_inputs_still_current(
        project,
        frozen,
    )


def test_frozen_r2v_quarantines_when_storyboard_changes() -> None:
    """Major-1 control: the publish tolerance is scoped to the prev
    reroll. A genuine Project-input change (storyboard reselected)
    still quarantines, so the fix did not widen into a blanket pass."""

    from services.media_files.r2v_execution import (
        FileR2VExecutionService,
    )
    from services.project_files.models import ElementOutput

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, _timeline = _project([first, second])
    second.outputs["storyboard"] = ElementOutput(
        slot_id="element:e2:storyboard",
    )
    project.assets.artifact_slots_by_id[
        "element:e2:storyboard"
    ] = ArtifactSlot(
        slot_id="element:e2:storyboard",
        owner_ref="element:e2",
        kind="r2v_storyboard_image",
        version_ids=["sb-v2"],
        selected_version_id="sb-v2",
    )
    _select_prev_video(project, "e1", "prevV1")
    frozen = _frozen_task(
        {
            "elementId": "e2",
            "mode": "r2v",
            "referenceVersionIds": [
                "sb-v1",
                "continuity:last_frame:prevV1",
                "continuity:tail_clip:prevV1",
            ],
        },
    )
    # Storyboard moved sb-v1 -> sb-v2: a real input change.
    assert not FileR2VExecutionService._frozen_inputs_still_current(
        project,
        frozen,
    )


def test_frozen_i2v_publishes_after_prev_reroll() -> None:
    """Major-1 (i2v): an auto-framed i2v render paid against the prev
    last frame publishes across a prev reroll, but quarantines once an
    explicit first frame is authored (a genuine input change)."""

    from services.media_files.r2v_execution import (
        FileR2VExecutionService,
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000, creation_type="i2v")
    project, _timeline = _project([first, second])
    _select_prev_video(project, "e1", "prevV1")
    frozen = _frozen_task(
        {
            "elementId": "e2",
            "mode": "i2v",
            "referenceVersionIds": ["continuity:last_frame:prevV1"],
            "firstFrameVersionId": "continuity:last_frame:prevV1",
        },
    )
    _select_prev_video(project, "e1", "prevV2")

    assert FileR2VExecutionService._frozen_inputs_still_current(
        project,
        frozen,
    )

    # Authoring an explicit first frame mid-render is a real change.
    second.creation.first_frame_version_id = "user-frame"
    assert not FileR2VExecutionService._frozen_inputs_still_current(
        project,
        frozen,
    )


def test_marker_bounds_follow_image_sequence() -> None:
    """Major-1: the bounds check caps authored [Image N] at the plan's
    IMAGE count, so a positional ordinal that would collide with the
    injected last frame is rejected before the provider call. All-image
    plans behave exactly like the old mixed bound."""

    from domain.errors import ValidationError
    from services.media_files.r2v_execution import (
        _validate_authored_marker_bounds,
    )

    project = Project.new(project_id="p-bounds", name="Bounds")
    _publish_artifact(project, "aa", "img-1", media_type="image/png")
    _publish_artifact(project, "bb", "vid-1", media_type="video/mp4")
    _publish_artifact(project, "cc", "img-2", media_type="image/png")
    plan = ["img-1", "vid-1", "img-2"]
    _validate_authored_marker_bounds("参考 [Image 2] 的动作。", project, plan)
    with pytest.raises(ValidationError):
        _validate_authored_marker_bounds("参考 [Image 3] 的动作。", project, plan)
    all_images = ["img-1", "img-2"]
    _validate_authored_marker_bounds("参考 [Image 2]。", project, all_images)
    with pytest.raises(ValidationError):
        _validate_authored_marker_bounds("参考 [Image 3]。", project, all_images)


def test_extract_registers_inflight_anchor(tmp_path, monkeypatch) -> None:
    """Major-2: a successful extract registers the predecessor digest,
    so event-driven prunes in the same process treat the anchors a
    queued payload froze as in flight."""

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    project, timeline, _f, second = _two_segment_project("v1")
    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    entry = _frame_entry(tmp_path)
    _mock_ffmpeg_paths(monkeypatch)
    monkeypatch.setattr(
        sc,
        "_resolve_prev_video_path",
        lambda *a, **k: source,
    )
    monkeypatch.setattr(sc, "_cut_last_frame", lambda **kw: (entry,))
    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    monkeypatch.setattr(sc, "_continuity_extract_locks", {})
    inflight: dict = {}
    monkeypatch.setattr(sc, "_continuity_inflight", inflight)

    sc.extract_continuity_artifacts(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
    )
    assert sc._digest_for("v1") in inflight


def test_prune_protects_inflight_registry_entries(
    tmp_path,
    monkeypatch,
) -> None:
    """Major-2: registered digests survive the event-driven prune even
    past the grace window with a cold cache; expired entries do not."""

    import os
    import time

    from collections import OrderedDict

    from services.media_files import segment_continuity as sc

    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    root = tmp_path / "runtime" / "continuity"
    live = root / ("1" * 16)
    expired = root / ("2" * 16)
    for directory in (live, expired):
        directory.mkdir(parents=True)
        (directory / "tail_clip.mp4").write_bytes(b"x")
        old = time.time() - sc._PRUNE_GRACE_SECONDS - 60
        os.utime(directory, (old, old))
    monkeypatch.setattr(
        sc,
        "_continuity_inflight",
        {"1" * 16: time.time() + 60, "2" * 16: time.time() - 1},
    )
    removed = sc._prune_continuity_dirs(tmp_path, current_digest="")
    assert removed == 1
    assert live.exists()
    assert not expired.exists()


def test_missing_ffmpeg_drops_prev_chain_from_r2v_nodes() -> None:
    """Minor-2 (graph side): when ffmpeg cannot run, anchors never
    ship — r2v nodes must not chain on prev, and their fingerprint must
    match the prev-less shape so a prev reroll cannot re-qualify parked
    FAILED nodes for an unchanged-wire paid rerun. The optimistic
    default still chains."""

    from services.file_agent_runtime.work_graph import derive_work_graph

    project, _timeline = _project(
        [_element("e1", start=0), _element("e2", start=4000)],
    )
    _select_prev_video(project, "e1", "prev-version-1")
    solo_project = _project(
        [_element("e1", start=0), _element("e2", start=4000)],
    )[0]

    missing = derive_work_graph(project, ffmpeg_ready=False).by_id["video:e2"]
    solo = derive_work_graph(solo_project, ffmpeg_ready=False).by_id[
        "video:e2"
    ]
    assert "video:e1" not in missing.deps
    assert missing.dispatch_fingerprint == solo.dispatch_fingerprint

    optimistic = derive_work_graph(project).by_id["video:e2"]
    assert "video:e1" in optimistic.deps


def test_resolve_extend_request_is_pure_reference_video(
    tmp_path,
    monkeypatch,
) -> None:
    """The first-class VIDEO_EXTEND submission carries ONLY the
    predecessor's real artifact as reference_video: no reference stack,
    no synthetic ids, no last-frame image; ratio follows the material
    and the provider duration/trim encode material+new semantics."""

    from models.video_task_plans import VideoTaskKind, VideoTaskPlan
    from services.media_files import r2v_execution as rx

    monkeypatch.setattr(
        rx,
        "_resolve_single_media_version",
        lambda **kw: (
            "file:///prev.mp4",
            "sha256:abc",
            "artifact-version:prev-v",
            {"ref": "artifact-version:prev-v"},
        ),
    )
    _project, _timeline, first, second = _two_segment_project("prev-v")
    plan = VideoTaskPlan(
        kind=VideoTaskKind.VIDEO_EXTEND,
        predecessor_version_id="prev-v",
        material_duration_seconds=8.0,
        ratio="adaptive",
        submit_duration_seconds=18,
        trim_offset_seconds=8.0,
    )
    resolved = rx._resolve_extend_request(
        project=_project,
        project_root=tmp_path,
        element=second,
        element_id=second.element_id,
        target_ref=f"element:{second.element_id}",
        plan=plan,
        prompt="本段新内容",
        resolution="720P",
        watermark=False,
        generate_audio=True,
        duration_seconds=10,
    )
    assert resolved.mode == "video_extend"
    assert resolved.reference_version_ids == ("prev-v",)
    assert resolved.reference_urls == ("file:///prev.mp4",)
    assert resolved.continuity_shape == "video_extend"
    assert resolved.continuity_trim_offset == 8.0
    assert resolved.provider_duration_seconds == 18
    assert resolved.ratio == "adaptive"
    assert "向后延长" in resolved.prompt
    assert "[Image" not in resolved.prompt
    assert first.element_id != second.element_id


def test_extend_provenance_records_storyboard_to_break_stale_loop(
    tmp_path,
    monkeypatch,
) -> None:
    """Regression for the V1..V24 regeneration loop: the r2v video node's
    staleness check requires the Element's storyboard selection in the
    artifact provenance. Extend does not send the storyboard, so without
    recording it every published extend artifact read as perpetually
    STALE and auto_approve re-rendered it forever. The provenance must
    carry both the predecessor material and the storyboard selection."""

    from models.video_task_plans import VideoTaskKind, VideoTaskPlan
    from services.media_files import r2v_execution as rx

    monkeypatch.setattr(
        rx,
        "_resolve_single_media_version",
        lambda **kw: (
            "file:///prev.mp4",
            "sha256:abc",
            "artifact-version:prev-v",
            {"ref": "artifact-version:prev-v"},
        ),
    )
    project, _timeline, _first, second = _two_segment_project("prev-v")
    slot_id = f"element:{second.element_id}:storyboard"
    project.assets.artifact_slots_by_id[slot_id] = ArtifactSlot(
        slot_id=slot_id,
        owner_ref=f"element:{second.element_id}",
        kind="element_storyboard",
        version_ids=["sb-v"],
        selected_version_id="sb-v",
    )
    plan = VideoTaskPlan(
        kind=VideoTaskKind.VIDEO_EXTEND,
        predecessor_version_id="prev-v",
        material_duration_seconds=8.0,
        ratio="adaptive",
        submit_duration_seconds=18,
        trim_offset_seconds=8.0,
    )
    resolved = rx._resolve_extend_request(
        project=project,
        project_root=tmp_path,
        element=second,
        element_id=second.element_id,
        target_ref=f"element:{second.element_id}",
        plan=plan,
        prompt="x",
        resolution="720P",
        watermark=False,
        generate_audio=True,
        duration_seconds=10,
    )
    assert "artifact-version:prev-v" in resolved.provenance_refs
    assert "artifact-version:sb-v" in resolved.provenance_refs


# ── author-intent routing signals (Transition / continuity text) ─────────────


def test_shift_authored_image_refs_moves_markers() -> None:
    from services.media_files.r2v_execution import _shift_authored_image_refs

    shifted = _shift_authored_image_refs(
        "[Image 1] 为分镜图；[Image 2] 提供角色身份",
        1,
    )
    assert "[Image 2] 为分镜图" in shifted
    assert "[Image 3] 提供角色身份" in shifted


def test_continuity_signals_reads_transition_and_keywords() -> None:
    from services.media_files.r2v_execution import _continuity_signals
    from services.project_files.models import (
        TransitionCreation,
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    transition = TimelineElement(
        element_id="t-1",
        label="t-1",
        span=TimelineSpan(start_tick=3800, duration_tick=400),
        creation=TransitionCreation(
            from_element_id="e1",
            to_element_id="e2",
            transition_kind="crossfade",
        ),
    )
    _proj, timeline = _project([first, second, transition])
    kind, intent, one_take = _continuity_signals(timeline, second, first)
    assert kind == "blend"
    assert intent == "neutral"
    assert one_take is False

    transition.creation = transition.creation.model_copy(
        update={"transition_kind": "cut"},
    )
    assert _continuity_signals(timeline, second, first)[0] == "cut"

    no_transition = _element("e2", start=4000)
    no_transition.creation = no_transition.creation.model_copy(
        update={"continuity": "承接上一段：七仙女落向山道，同一动作继续"},
    )
    _proj2, timeline2 = _project([first, no_transition])
    kind, intent, one_take = _continuity_signals(
        timeline2,
        no_transition,
        first,
    )
    assert kind == "none"
    assert intent == "continue"
    assert one_take is False

    one_take_el = _element("e3", start=4000)
    one_take_el.creation = one_take_el.creation.model_copy(
        update={"continuity": "一镜到底跟随俯冲，延续运镜"},
    )
    assert _continuity_signals(
        _project([first, one_take_el])[1],
        one_take_el,
        first,
    )[2]
    cut_el = _element("e4", start=4000)
    cut_el.creation = cut_el.creation.model_copy(
        update={"continuity": "切到另一机位，时间跳转三年后"},
    )
    assert (
        _continuity_signals(
            _project([first, cut_el])[1],
            cut_el,
            first,
        )[1]
        == "cut"
    )


def test_r2v_strong_continuity_matrix(monkeypatch) -> None:
    from models import config as model_config
    from services.file_agent_runtime import work_graph
    from services.media_files import r2v_execution as rx

    monkeypatch.setattr(work_graph, "probe_ffmpeg_ready", lambda: True)
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")
    project, timeline, first, second = _two_segment_project("prev-v")
    assert rx._r2v_strong_continuity(project, timeline, second)

    cut = _element("e2", start=4000)
    cut.creation = cut.creation.model_copy(
        update={"continuity": "切到另一机位"},
    )
    _p, tl = _project([first, cut])
    _select_prev_video(_p, "e1", "prev-v")
    assert not rx._r2v_strong_continuity(_p, tl, cut)

    one_take = _element("e2", start=4000)
    one_take.creation = one_take.creation.model_copy(
        update={"continuity": "一镜到底延续运镜"},
    )
    _p, tl = _project([first, one_take])
    _select_prev_video(_p, "e1", "prev-v")
    # wan3.0 can extend a one-take → the r2v strong path must NOT claim
    # the anchor (the dispatch would ship as VIDEO_EXTEND instead).
    assert not rx._r2v_strong_continuity(_p, tl, one_take)
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan2.6-r2v",
    )
    assert rx._r2v_strong_continuity(_p, tl, one_take)
    monkeypatch.setattr(work_graph, "probe_ffmpeg_ready", lambda: False)
    assert not rx._r2v_strong_continuity(_p, tl, one_take)


def test_resolve_request_promotes_anchor_for_strong_continuity(
    tmp_path,
    monkeypatch,
) -> None:
    """The executor leads the stack with the predecessor's last frame,
    shifts the author's [Image N] sentences +1, labels 图1 and adds the
    first-frame imperative — the A/B-proven seam shape (0.79 vs 0.39)."""

    from services.media_files import r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityEntry
    from services.project_files.models import (
        ArtifactVersion,
        IndexedFile,
    )
    from services.project_files.store import ProjectSnapshot

    project, _tl, _first, second = _two_segment_project("prev-v")
    # Storyboard slot + version so the r2v branch resolves.
    project.assets.artifact_slots_by_id[
        "element:e2:storyboard"
    ] = ArtifactSlot(
        slot_id="element:e2:storyboard",
        owner_ref="element:e2",
        kind="r2v_storyboard_image",
        version_ids=["sb-v1"],
        selected_version_id="sb-v1",
    )
    project.assets.files_by_id["file-sb-v1"] = IndexedFile(
        file_id="file-sb-v1",
        kind="artifact_payload",
        media_type="image/png",
        relative_uri="assets/artifacts/file-sb-v1",
        sha256="1" * 64,
        size_bytes=1,
        created_at="2026-08-05T00:00:00Z",
    )
    project.assets.artifact_versions_by_id["sb-v1"] = ArtifactVersion(
        version_id="sb-v1",
        name="sb-v1",
        slot_id="element:e2:storyboard",
        kind="r2v_storyboard_image",
        owner_ref="element:e2",
        file_id="file-sb-v1",
        checksum="1" * 64,
        based_on_generation=1,
        provenance_refs=[],
        stale=False,
        created_at="2026-08-05T00:00:00Z",
    )
    from services.project_files.models import ElementOutput

    second.outputs["storyboard"] = ElementOutput(
        slot_id="element:e2:storyboard",
    )
    second.creation = second.creation.model_copy(
        update={
            "video_prompt": ("[Image 1] 为本镜头分镜图，只采用其构图与节奏；人物跃下。"),
            "video_reference_version_ids": [],
        },
    )

    import services.project_files.production_stage as ps

    monkeypatch.setattr(
        ps,
        "assert_media_production_allowed",
        lambda *_a, **_k: None,
    )
    import services.project_files.prompt_sync as psm

    monkeypatch.setattr(
        psm,
        "assert_r2v_prompt_sync",
        lambda *_a, **_k: None,
    )
    from models.video_task_plans import VideoTaskKind, VideoTaskPlan

    monkeypatch.setattr(
        rx,
        "_build_task_plan",
        lambda *_a, **_k: VideoTaskPlan(
            kind=VideoTaskKind.R2V,
            submit_duration_seconds=4,
            strong_continuity=True,
        ),
    )
    anchor = ContinuityEntry(
        kind="last_frame",
        reference_id="continuity:last_frame:prev-v",
        url="file:///anchor.png",
        checksum="sha256:aaa",
        path=Path("/anchor.png"),
        role_label="上一片段末帧（本段起始画面）",
        provenance_ref="artifact-version:prev-v",
        media_type="image/png",
    )
    monkeypatch.setattr(
        rx,
        "_i2v_auto_first_frame_entry",
        lambda **_kw: anchor,
    )
    monkeypatch.setattr(
        rx,
        "_assert_r2v_reference_budget",
        lambda *_a, **_k: None,
    )

    def fake_versions(**kw):
        ids = list(kw["version_ids"])
        return (
            [f"url::{item}" for item in ids],
            [f"sum::{item}" for item in ids],
            [f"ref::{item}" for item in ids],
            [{"ref": f"ref::{item}"} for item in ids],
        )

    monkeypatch.setattr(rx, "_resolve_reference_versions", fake_versions)
    monkeypatch.setattr(
        rx,
        "_resolve_reference_voices",
        lambda **_kw: ([], []),
    )
    monkeypatch.setattr(rx, "_resolve_bgm_reference", lambda *_a, **_k: "")
    from models import config as model_config

    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")

    snapshot = ProjectSnapshot(project=project, etag="e1", generation=1)
    resolved = rx._resolve_request(
        snapshot=snapshot,
        project_root=tmp_path,
        target_ref="element:e2",
        arguments={
            "prompt": "[Image 1] 为本镜头分镜图，只采用其构图与节奏；人物跃下。",
        },
    )
    assert resolved.reference_version_ids[0] == (
        "continuity:last_frame:prev-v"
    )
    # Plan shape: the storyboard clause was rewritable, so the
    # storyboard drops out and the anchor inherits its 图1 slot.
    assert "sb-v1" not in resolved.reference_version_ids
    # Staleness-gate regression: the dropped storyboard must still be
    # recorded in provenance, or published clips loop STALE forever
    # (auto_approve re-bills the render every ~3.5 minutes).
    assert "artifact-version:sb-v1" in resolved.provenance_refs
    assert resolved.reference_urls[0] == "file:///anchor.png"
    assert "上一片段末帧（本段起始画面）" in resolved.prompt
    # The action sentence survives the clause swap untouched.
    assert "人物跃下" in resolved.prompt
    # Spec §2: the first-frame imperative is the FIRST sentence.
    assert resolved.prompt.startswith("开场第一帧严格对齐图1")
    assert resolved.bgm_reference_url == ""


def test_resolve_request_falls_back_to_keep_and_shift(
    tmp_path,
    monkeypatch,
) -> None:
    """Without the template sentence the storyboard stays (no dangling
    author words) and every marker shifts +1 behind the anchor."""

    import services.project_files.production_stage as ps
    import services.project_files.prompt_sync as psm
    from models import config as model_config
    from models.video_task_plans import VideoTaskKind, VideoTaskPlan
    from services.media_files import r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityEntry
    from services.project_files.models import (
        ArtifactVersion,
        ElementOutput,
        IndexedFile,
    )
    from services.project_files.store import ProjectSnapshot

    project, _tl, _first, second = _two_segment_project("prev-v")
    project.assets.artifact_slots_by_id[
        "element:e2:storyboard"
    ] = ArtifactSlot(
        slot_id="element:e2:storyboard",
        owner_ref="element:e2",
        kind="r2v_storyboard_image",
        version_ids=["sb-v1"],
        selected_version_id="sb-v1",
    )
    project.assets.files_by_id["file-sb-v1"] = IndexedFile(
        file_id="file-sb-v1",
        kind="artifact_payload",
        media_type="image/png",
        relative_uri="assets/artifacts/file-sb-v1",
        sha256="1" * 64,
        size_bytes=1,
        created_at="2026-08-05T00:00:00Z",
    )
    project.assets.artifact_versions_by_id["sb-v1"] = ArtifactVersion(
        version_id="sb-v1",
        name="sb-v1",
        slot_id="element:e2:storyboard",
        kind="r2v_storyboard_image",
        owner_ref="element:e2",
        file_id="file-sb-v1",
        checksum="1" * 64,
        based_on_generation=1,
        provenance_refs=[],
        stale=False,
        created_at="2026-08-05T00:00:00Z",
    )
    second.outputs["storyboard"] = ElementOutput(
        slot_id="element:e2:storyboard",
    )
    second.creation = second.creation.model_copy(
        update={
            "video_prompt": "[Image 1] 是本镜头的草图风格，人物跃下。",
            "video_reference_version_ids": [],
        },
    )
    monkeypatch.setattr(
        ps,
        "assert_media_production_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        psm,
        "assert_r2v_prompt_sync",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        rx,
        "_build_task_plan",
        lambda *_a, **_k: VideoTaskPlan(
            kind=VideoTaskKind.R2V,
            submit_duration_seconds=4,
            strong_continuity=True,
        ),
    )
    anchor = ContinuityEntry(
        kind="last_frame",
        reference_id="continuity:last_frame:prev-v",
        url="file:///anchor.png",
        checksum="sha256:aaa",
        path=Path("/anchor.png"),
        role_label="上一片段末帧（本段起始画面）",
        provenance_ref="artifact-version:prev-v",
        media_type="image/png",
    )
    monkeypatch.setattr(
        rx,
        "_i2v_auto_first_frame_entry",
        lambda **_kw: anchor,
    )
    monkeypatch.setattr(
        rx,
        "_assert_r2v_reference_budget",
        lambda *_a, **_k: None,
    )

    def fake_versions(**kw):
        ids = list(kw["version_ids"])
        return (
            [f"url::{item}" for item in ids],
            [f"sum::{item}" for item in ids],
            [f"ref::{item}" for item in ids],
            [{"ref": f"ref::{item}"} for item in ids],
        )

    monkeypatch.setattr(rx, "_resolve_reference_versions", fake_versions)
    monkeypatch.setattr(
        rx,
        "_resolve_reference_voices",
        lambda **_kw: ([], []),
    )
    monkeypatch.setattr(rx, "_resolve_bgm_reference", lambda *_a, **_k: "")
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")

    snapshot = ProjectSnapshot(project=project, etag="e1", generation=1)
    resolved = rx._resolve_request(
        snapshot=snapshot,
        project_root=tmp_path,
        target_ref="element:e2",
        arguments={"prompt": "[Image 1] 是本镜头的草图风格，人物跃下。"},
    )
    assert resolved.reference_version_ids == (
        "continuity:last_frame:prev-v",
        "sb-v1",
    )
    # Author marker shifted to 图2 behind the anchor.
    assert "图2" in resolved.prompt or "[Image 2]" in resolved.prompt


# ── bgm reference_audio resolution (planning side) ───────────────────────────


def _bgm_project(tmp_path, *, with_bgm: bool = True):
    from services.project_files.models import (
        AudioCreation,
        SourceAssetVersion,
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    if not with_bgm:
        return project, timeline, second
    music = tmp_path / "assets" / "sources" / "bed.mp3"
    music.parent.mkdir(parents=True, exist_ok=True)
    music.write_bytes(b"ID3" + b"\0" * 100)
    bgm_el = TimelineElement(
        element_id="bgm-1",
        label="bgm-1",
        span=TimelineSpan(start_tick=0, duration_tick=30000),
        creation=AudioCreation(
            source_asset_version_id="audio-v1",
            role="bgm",
        ),
    )
    timeline = timeline.model_copy(
        update={
            "elements_by_id": {
                **timeline.elements_by_id,
                "bgm-1": bgm_el,
            },
        },
    )
    project.timelines.items["timeline:main"] = timeline
    project.assets.source_versions_by_id["audio-v1"] = SourceAssetVersion(
        version_id="audio-v1",
        logical_asset_id="asset-a1",
        name="bed",
        file_id="file-audio-v1",
        checksum="2" * 64,
        media_kind="audio",
        media_type="audio/mpeg",
        created_at="2026-08-05T00:00:00Z",
    )
    from services.project_files.models import IndexedFile

    project.assets.files_by_id["file-audio-v1"] = IndexedFile(
        file_id="file-audio-v1",
        kind="source_original",
        media_type="audio/mpeg",
        relative_uri="assets/sources/bed.mp3",
        sha256="2" * 64,
        size_bytes=103,
        created_at="2026-08-05T00:00:00Z",
    )
    return project, timeline, second


def _bind_bgm_config(monkeypatch, model="wan3.0-video"):
    from models import config as model_config

    monkeypatch.setattr(model_config, "get_video_model_name", lambda: model)
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")


def test_bgm_reference_skips_without_bgm_element(
    tmp_path,
    monkeypatch,
) -> None:
    from services.media_files import r2v_execution as rx

    project, timeline, _second = _bgm_project(tmp_path, with_bgm=False)
    _bind_bgm_config(monkeypatch)
    assert (
        rx._resolve_bgm_reference(
            project,
            timeline,
            tmp_path,
            voice_count=0,
            element_id="e2",
        )
        == ""
    )


def test_bgm_reference_respects_voice_slot_budget(
    tmp_path,
    monkeypatch,
) -> None:
    from services.media_files import r2v_execution as rx

    project, timeline, _second = _bgm_project(tmp_path)
    _bind_bgm_config(monkeypatch)
    monkeypatch.setattr(
        rx,
        "_bgm_excerpt",
        lambda *_a, **_k: "file:///bed.mp3",
    )
    reported: list = []
    monkeypatch.setattr(
        rx,
        "report_error",
        lambda **kw: reported.append(kw),
    )
    assert (
        rx._resolve_bgm_reference(
            project,
            timeline,
            tmp_path,
            voice_count=4,
            element_id="e2",
        )
        == "file:///bed.mp3"
    )
    assert not reported
    # wan3.0 documents five audio slots; 5 voices + bgm does not fit.
    assert (
        rx._resolve_bgm_reference(
            project,
            timeline,
            tmp_path,
            voice_count=5,
            element_id="e2",
        )
        == ""
    )
    assert reported and reported[0]["code"] == "BGM_SKIPPED_BUDGET"


def test_bgm_reference_skips_for_models_without_standalone_audio(
    tmp_path,
    monkeypatch,
) -> None:
    from services.media_files import r2v_execution as rx

    project, timeline, _second = _bgm_project(tmp_path)
    # wan2.6 documents no audio reference input at all.
    _bind_bgm_config(monkeypatch, model="wan2.6-r2v")
    monkeypatch.setattr(
        rx,
        "report_error",
        lambda **kw: None,
    )
    assert (
        rx._resolve_bgm_reference(
            project,
            timeline,
            tmp_path,
            voice_count=0,
            element_id="e2",
        )
        == ""
    )


def test_ledger_continuity_digests_reads_frozen_task_snapshots(
    tmp_path,
) -> None:
    """A SUCCEEDED task's anchor is ledger evidence: the extract-side
    prune must keep it, and only unreferenced digests may go."""

    import hashlib as _hl
    import json as _json
    import os as _os
    import time as _time

    from services.media_files import segment_continuity as sc

    prev = "artifact-version-prev"
    used = _hl.sha256(prev.encode()).hexdigest()[:16]
    unused = "u" * 16
    tasks_root = tmp_path / "runtime" / "tasks" / "task-1"
    tasks_root.mkdir(parents=True)
    (tasks_root / "task.json").write_text(
        _json.dumps(
            {
                "metadata": {
                    "requestSnapshot": {
                        "referenceVersionIds": [
                            f"continuity:last_frame:{prev}",
                            "artifact-version-storyboard",
                        ],
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    assert sc._ledger_continuity_digests(tmp_path) == {used}

    root = tmp_path / "runtime" / "continuity"
    for digest in (used, unused):
        directory = root / digest
        directory.mkdir(parents=True)
        (directory / "last_frame.png").write_bytes(b"x")
        old = _time.time() - sc._PRUNE_GRACE_SECONDS - 60
        _os.utime(directory, (old, old))
    removed = sc._prune_continuity_dirs(
        tmp_path,
        current_digest="other",
        extra_keep=sc._ledger_continuity_digests(tmp_path),
    )
    assert removed == 1
    assert (root / used / "last_frame.png").exists()
    assert not (root / unused).exists()


def _patch_resolve_env(monkeypatch, rx, anchor) -> None:
    """Shared harness for _resolve_request tier tests."""

    from models import config as model_config

    import services.project_files.production_stage as ps
    import services.project_files.prompt_sync as psm

    from models.video_task_plans import VideoTaskKind, VideoTaskPlan

    monkeypatch.setattr(
        ps,
        "assert_media_production_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(psm, "assert_r2v_prompt_sync", lambda *_a, **_k: None)
    monkeypatch.setattr(
        rx,
        "_build_task_plan",
        lambda *_a, **_k: VideoTaskPlan(
            kind=VideoTaskKind.R2V,
            submit_duration_seconds=4,
            strong_continuity=True,
        ),
    )
    monkeypatch.setattr(
        rx,
        "_i2v_auto_first_frame_entry",
        lambda **_kw: anchor,
    )
    monkeypatch.setattr(
        rx,
        "_assert_r2v_reference_budget",
        lambda *_a, **_k: None,
    )

    def fake_versions(**kw):
        ids = list(kw["version_ids"])
        return (
            [f"url::{item}" for item in ids],
            [f"sum::{item}" for item in ids],
            [f"ref::{item}" for item in ids],
            [{"ref": f"ref::{item}"} for item in ids],
        )

    monkeypatch.setattr(rx, "_resolve_reference_versions", fake_versions)
    monkeypatch.setattr(
        rx,
        "_resolve_reference_voices",
        lambda **_kw: ([], []),
    )
    monkeypatch.setattr(rx, "_resolve_bgm_reference", lambda *_a, **_k: "")
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")


def _anchor_entry() -> object:
    from services.media_files.segment_continuity import ContinuityEntry

    return ContinuityEntry(
        kind="last_frame",
        reference_id="continuity:last_frame:prev-v",
        url="file:///anchor.png",
        checksum="sha256:aaa",
        path=Path("/anchor.png"),
        role_label="上一片段末帧（本段起始画面）",
        provenance_ref="artifact-version:prev-v",
        media_type="image/png",
    )


def test_resolve_request_none_tier_ships_without_storyboard(
    tmp_path,
    monkeypatch,
) -> None:
    """Simple anchored segments carry no storyboard at all: the classic
    "storyboard must be selected" requirement is lifted for the none
    tier, the authored 末帧 sentence is rewritten to the canonical
    anchor clause, and nothing storyboard-shaped enters provenance."""

    from services.media_files import r2v_execution as rx
    from services.project_files.store import ProjectSnapshot

    project, _tl, _first, second = _two_segment_project("prev-v")
    second.creation = second.creation.model_copy(
        update={
            "video_prompt": ("[Image 1] 为上一片段末帧（本段起始状态），开场对齐该图；" "男孩抬头望向雨幕。"),
            "video_reference_version_ids": [],
        },
    )
    _patch_resolve_env(monkeypatch, rx, _anchor_entry())

    resolved = rx._resolve_request(
        snapshot=ProjectSnapshot(project=project, etag="e1", generation=1),
        project_root=tmp_path,
        target_ref="element:e2",
        arguments={"prompt": None},
    )
    assert resolved.reference_version_ids[0] == (
        "continuity:last_frame:prev-v"
    )
    assert resolved.prompt.startswith("开场第一帧严格对齐图1")
    # Marker rendering turns [Image 1] into 图1 before submit.
    assert "图1 为上一片段末帧（本段起始画面），第一帧严格对齐该图；" in (resolved.prompt)
    assert "男孩抬头望向雨幕" in resolved.prompt
    assert not any("storyboard" in item for item in resolved.provenance_refs)


def test_resolve_request_combined_tier_keeps_storyboard_with_anchor(
    tmp_path,
    monkeypatch,
) -> None:
    """Complex anchored segments ship anchor AND storyboard together:
    even when the template sentence is rewritable, the combined tier
    must NOT swap the storyboard out — it rides as 图2 behind the
    anchor (+1 shift) so rhythm and composition survive."""

    from services.media_files import r2v_execution as rx
    from services.project_files.models import ElementOutput
    from services.project_files.store import ProjectSnapshot

    project, _tl, _first, second = _two_segment_project("prev-v")
    project.assets.artifact_slots_by_id[
        "element:e2:storyboard"
    ] = ArtifactSlot(
        slot_id="element:e2:storyboard",
        owner_ref="element:e2",
        kind="r2v_storyboard_image",
        version_ids=["sb-v1"],
        selected_version_id="sb-v1",
    )
    from services.project_files.models import ArtifactVersion, IndexedFile

    project.assets.files_by_id["file-sb-v1"] = IndexedFile(
        file_id="file-sb-v1",
        kind="artifact_payload",
        media_type="image/png",
        relative_uri="assets/artifacts/file-sb-v1",
        sha256="1" * 64,
        size_bytes=1,
        created_at="2026-08-05T00:00:00Z",
    )
    project.assets.artifact_versions_by_id["sb-v1"] = ArtifactVersion(
        version_id="sb-v1",
        name="sb-v1",
        slot_id="element:e2:storyboard",
        kind="r2v_storyboard_image",
        owner_ref="element:e2",
        file_id="file-sb-v1",
        checksum="1" * 64,
        based_on_generation=1,
        provenance_refs=[],
        stale=False,
        created_at="2026-08-05T00:00:00Z",
    )
    second.outputs["storyboard"] = ElementOutput(
        slot_id="element:e2:storyboard",
    )
    second.creation = second.creation.model_copy(
        update={
            "video_prompt": ("[Image 1] 为本镜头分镜图，只提供构图与节奏；" "镜头缓推向站台，男孩抬头。"),
            "video_reference_version_ids": [],
        },
    )
    _patch_resolve_env(monkeypatch, rx, _anchor_entry())

    resolved = rx._resolve_request(
        snapshot=ProjectSnapshot(project=project, etag="e1", generation=1),
        project_root=tmp_path,
        target_ref="element:e2",
        arguments={"prompt": None},
    )
    assert resolved.reference_version_ids[0] == (
        "continuity:last_frame:prev-v"
    )
    # The storyboard stays in the SENT stack (promoted to 图2).
    assert "sb-v1" in resolved.reference_version_ids
    # Authored ordinals shifted: the storyboard sentence now reads 图2.
    assert "图2 为本镜头分镜图" in resolved.prompt
    assert resolved.prompt.startswith("开场第一帧严格对齐图1")


def test_resolve_request_none_tier_strips_lingering_storyboard_clause(
    tmp_path,
    monkeypatch,
) -> None:
    """Fallback the spec names by hand: an agent that still writes the
    storyboard sentence on a none-tier segment (no artifact at all)
    gets the clause rewritten to the anchor sentence — no dangling
    "分镜图" words can reach the provider for a segment that ships
    without a storyboard."""

    from services.media_files import r2v_execution as rx
    from services.project_files.store import ProjectSnapshot

    project, _tl, _first, second = _two_segment_project("prev-v")
    second.creation = second.creation.model_copy(
        update={
            "video_prompt": ("[Image 1] 为本镜头分镜图，只提供构图与节奏；" "男孩抬头望向雨幕。"),
            "video_reference_version_ids": [],
        },
    )
    _patch_resolve_env(monkeypatch, rx, _anchor_entry())

    resolved = rx._resolve_request(
        snapshot=ProjectSnapshot(project=project, etag="e1", generation=1),
        project_root=tmp_path,
        target_ref="element:e2",
        arguments={"prompt": None},
    )
    # The storyboard sentence was swapped for the anchor clause...
    assert "分镜图" not in resolved.prompt.split("【")[0]
    assert "图1 为上一片段末帧（本段起始画面），第一帧严格对齐该图；" in (resolved.prompt)
    # ...and nothing storyboard-shaped entered the stack or provenance.
    assert resolved.reference_version_ids[0] == (
        "continuity:last_frame:prev-v"
    )
    assert not any("sb" in item for item in resolved.provenance_refs)
