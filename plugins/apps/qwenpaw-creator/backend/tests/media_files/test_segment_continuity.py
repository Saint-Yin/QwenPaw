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


def test_tail_clip_failure_degrades_to_last_frame_only(
    tmp_path,
    monkeypatch,
) -> None:
    """Regression for Major #3: a container-level tail-clip failure
    must not block an otherwise usable last-frame anchor, otherwise
    I2V chains lose the fallback the reviewer specifically asked us
    to protect."""

    from services.media_files import segment_continuity as sc

    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        # ffprobe path: emit a plausible duration.
        if "-show_entries" in cmd:

            class _Probe:
                returncode = 0
                stdout = "7.5"
                stderr = ""

            return _Probe()
        # ffmpeg path: land bytes at the requested output.
        output = Path(cmd[-1])
        output.write_bytes(b"fake-frame")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)

    def explode(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("container-level tail failure")

    monkeypatch.setattr(sc, "_extract_tail_clip_into", explode)

    entries = sc._cut_both(
        source=source,
        work_dir=work_dir,
        ffmpeg_path="/usr/bin/ffmpeg",
        ffprobe_path="/usr/bin/ffprobe",
        prev_version="prev-version-1",
        prev_element_id="e1",
        include_tail_clip=True,
    )
    kinds = {entry.kind for entry in entries}
    assert kinds == {"last_frame"}
    # last_frame materialized before the failed tail attempt.
    assert (work_dir / "last_frame.png").exists()


def test_tail_clip_seek_uses_duration_or_sseof(tmp_path, monkeypatch) -> None:
    """With a known duration the cut starts at total-tail; with an
    unknown duration it must seek from the container end (``-sseof``),
    never fall back to ``-ss 0`` which would capture the predecessor's
    OPENING frames and anchor the successor on the wrong end."""

    from services.media_files import segment_continuity as sc

    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    out = tmp_path / "tail.mp4"
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        commands.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"fake-clip")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)

    sc._extract_tail_clip(
        source,
        out,
        "/usr/bin/ffmpeg",
        tail_seconds=3.0,
        total_duration=7.5,
    )
    assert commands[0][commands[0].index("-ss") + 1] == "4.500000"
    assert "-sseof" not in commands[0]

    commands.clear()
    sc._extract_tail_clip(
        source,
        out,
        "/usr/bin/ffmpeg",
        tail_seconds=3.0,
        total_duration=0.0,
    )
    assert commands[0][commands[0].index("-sseof") + 1] == "-3.000000"
    assert "-ss" not in commands[0]


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
        "_cut_both",
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
            include_tail_clip=False,
        )

    bundle_v1 = extract()
    assert bundle_v1 is not None
    assert len(cuts) == 1
    key_v1 = ("v1", "/usr/bin/ffmpeg", False)
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
    assert ("v2", "/usr/bin/ffmpeg", False) in sc._continuity_extract_locks


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
            include_tail_clip=False,
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
            include_tail_clip=False,
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


def test_apply_continuity_traces_bundle_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    """m4: the submit-side no-op return must also be observable, and
    must leave every caller list untouched."""

    from models import config as model_config
    import services.observability as obs
    import services.media_files.r2v_execution as rx

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        obs,
        "trace_event",
        lambda name, **kw: events.append((name, kw)),
    )
    monkeypatch.setattr(
        rx,
        "trace_event",
        lambda name, **kw: events.append((name, kw)),
    )
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")

    lone = _element("e1", start=0)
    project, timeline = _project([lone])
    urls, checksums, provenance = ["u"], ["c"], ["p"]
    read_set: list[dict] = [{"ref": "p"}]
    ids, labels, suffix, voices = rx._apply_continuity_to_references(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=lone,
        version_ids=["ref-1"],
        urls=urls,
        checksums=checksums,
        provenance=provenance,
        read_set=read_set,
        voice_urls=[""],
        output_duration_seconds=4,
    )
    assert ids == ("ref-1",)
    assert labels == {}
    assert suffix == ""
    assert voices == ("",)
    assert (urls, checksums, provenance, read_set) == (
        ["u"],
        ["c"],
        ["p"],
        [{"ref": "p"}],
    )
    reasons = [
        kw["attributes"]["reason"]
        for name, kw in events
        if name == "creator.continuity.skipped"
    ]
    assert "bundle_unavailable" in reasons


def test_apply_continuity_reports_missing_last_frame(
    tmp_path,
    monkeypatch,
) -> None:
    """m4: a bundle without a last frame violates the extraction
    invariant and must report, not silently no-op."""

    from models import config as model_config
    import services.media_files.r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityBundle

    reports: list[dict] = []
    monkeypatch.setattr(rx, "report_error", lambda **kw: reports.append(kw))
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")
    monkeypatch.setattr(
        rx,
        "extract_continuity_artifacts",
        lambda **kw: ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(),
        ),
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    ids, labels, suffix, voices = rx._apply_continuity_to_references(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
        version_ids=[],
        urls=[],
        checksums=[],
        provenance=[],
        read_set=[],
        voice_urls=[],
        output_duration_seconds=4,
    )
    assert ids == ()
    assert labels == {}
    assert suffix == ""
    assert voices == ()
    assert len(reports) == 1
    assert reports[0]["code"] == "CONTINUITY_LAST_FRAME_MISSING"
    assert reports[0]["component"] == "r2v.continuity"


def test_apply_continuity_traces_tail_degradation(
    tmp_path,
    monkeypatch,
) -> None:
    """m4: on a continuation-capable model, a soft-degraded bundle
    (last frame only) must trace the submit-side consequence while
    still injecting the image anchor."""

    from models import config as model_config
    import services.media_files.r2v_execution as rx
    from services.media_files.segment_continuity import ContinuityBundle

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        rx,
        "trace_event",
        lambda name, **kw: events.append((name, kw)),
    )
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")
    monkeypatch.setattr(
        rx,
        "_assert_r2v_reference_budget",
        lambda *a, **k: None,
    )
    entry = _frame_entry(tmp_path)
    monkeypatch.setattr(
        rx,
        "extract_continuity_artifacts",
        lambda **kw: ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(entry,),
        ),
    )

    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    urls: list[str] = []
    checksums: list[str] = []
    provenance: list[str] = []
    read_set: list[dict] = []
    # Non-empty plan so ``last_frame_index`` is exercised end to end:
    # the suffix must cite ``[Image len(plan)+1]`` — the same mixed
    # send-order ordinal the role mapping assigns the appended frame.
    ids, labels, suffix, voices = rx._apply_continuity_to_references(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
        version_ids=["ref-a", "ref-b"],
        urls=urls,
        checksums=checksums,
        provenance=provenance,
        read_set=read_set,
        voice_urls=[],
        output_duration_seconds=4,
    )
    assert ids == ("ref-a", "ref-b", entry.reference_id)
    assert labels == {entry.reference_id: entry.role_label}
    assert "[Image 3]" in suffix
    assert "视频" not in suffix
    assert voices == ("",)
    assert urls == [entry.url]
    assert checksums == [entry.checksum]
    assert provenance == [entry.provenance_ref]
    assert read_set == [entry.as_read_entry()]
    reasons = [
        kw["attributes"]["reason"]
        for name, kw in events
        if name == "creator.continuity.skipped"
    ]
    assert reasons == ["tail_clip_degraded"]


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
    assert calls[0]["include_tail_clip"] is False


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

    monkeypatch.setattr(sc, "_cut_both", boom)
    with pytest.raises(RuntimeError, match="no space"):
        sc.extract_continuity_artifacts(
            project=project,
            project_root=tmp_path,
            timeline=timeline,
            element=second,
            include_tail_clip=False,
        )


def test_probe_failure_falls_back_to_sseof_tail(tmp_path, monkeypatch) -> None:
    """N-1: an ffprobe timeout must degrade to container-relative
    seeking, not lose the tail clip (and never cut the head)."""

    import subprocess as sp

    from services.media_files import segment_continuity as sc

    source = tmp_path / "prev.mp4"
    source.write_bytes(b"fake-video")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        commands.append(list(cmd))
        if "-show_entries" in cmd:
            raise sp.TimeoutExpired(cmd=cmd, timeout=1)
        Path(cmd[-1]).write_bytes(b"fake-bytes")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    entries = sc._cut_both(
        source=source,
        work_dir=work_dir,
        ffmpeg_path="/usr/bin/ffmpeg",
        ffprobe_path="/usr/bin/ffprobe",
        prev_version="prev-version-1",
        prev_element_id="e1",
        include_tail_clip=True,
    )
    assert {entry.kind for entry in entries} == {"last_frame", "tail_clip"}
    tail_cmd = next(c for c in commands if "-sseof" in c and "-t" in c)
    assert tail_cmd[tail_cmd.index("-sseof") + 1] == "-3.000000"
    tail_entry = next(e for e in entries if e.kind == "tail_clip")
    assert tail_entry.duration_seconds == 3.0


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
    assert any(item.startswith("continuity:") for item in r2v_ids)
    assert not any(item.startswith("continuity:") for item in edit_ids)
    assert edit_ids == video_reference_plan(project, second)

    before = _submission_input_fingerprint(project, "e2", mode="video_edit")
    _select_prev_video(project, "e1", "prev-version-2")
    after = _submission_input_fingerprint(project, "e2", mode="video_edit")
    assert before == after
    # Control: the r2v-mode fingerprint does track the prev version.
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


def test_apply_budget_failure_rolls_back_injection(
    tmp_path,
    monkeypatch,
) -> None:
    """N-10: the budget rollback branch must pop exactly what it
    appended and hand the caller back its untouched paid render."""

    from models import config as model_config
    import services.media_files.r2v_execution as rx
    from services.media_files.r2v_execution import VideoReferenceBudgetError
    from services.media_files.segment_continuity import ContinuityBundle

    reports: list[dict] = []
    monkeypatch.setattr(rx, "report_error", lambda **kw: reports.append(kw))
    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")
    entry = _frame_entry(tmp_path)

    def deny_budget(*args, **kwargs):  # noqa: ARG001
        raise VideoReferenceBudgetError(
            "VIDEO_REFERENCE_BUDGET_EXCEEDED: test",
        )

    monkeypatch.setattr(rx, "_assert_r2v_reference_budget", deny_budget)
    monkeypatch.setattr(
        rx,
        "extract_continuity_artifacts",
        lambda **kw: ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(entry,),
        ),
    )

    project, timeline, _first, second = _two_segment_project()
    urls, checksums, provenance = ["u"], ["c"], ["p"]
    read_set = [{"ref": "p"}]
    ids, labels, suffix, voices = rx._apply_continuity_to_references(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
        version_ids=["ref-1"],
        urls=urls,
        checksums=checksums,
        provenance=provenance,
        read_set=read_set,
        voice_urls=[""],
        output_duration_seconds=4,
    )
    assert ids == ("ref-1",)
    assert (urls, checksums, provenance, read_set) == (
        ["u"],
        ["c"],
        ["p"],
        [{"ref": "p"}],
    )
    assert labels == {}
    assert suffix == ""
    assert voices == ("",)
    assert reports[-1]["code"] == "CONTINUITY_SKIPPED_BUDGET"


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
    monkeypatch.setattr(sc, "_cut_both", lambda **kw: (entry,))
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
            include_tail_clip=False,
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
    """Minor-1 (end to end): a cold-cache startup sweep keeps the anchor
    a QUEUED task froze and reclaims a SUCCEEDED task's anchor."""

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
    assert removed == 1
    assert inflight_dir.exists()
    assert quarantined_dir.exists()
    assert not done_dir.exists()
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


def test_per_type_ordinals_align_across_suffix_and_role_block(
    tmp_path,
    monkeypatch,
) -> None:
    """Major-1 (end to end): the suffix and the role block derive from
    the same per-type numbering — with a video in the plan the last
    frame lands on the next real image ordinal and the tail clip on the
    next video ordinal. This pins the PRODUCTION indices, not
    hand-fed markers, so a regression in either side turns red."""

    from models import config as model_config
    import services.media_files.r2v_execution as rx
    from services.media_files import segment_continuity as sc
    from services.media_files.segment_continuity import ContinuityBundle

    monkeypatch.setattr(
        model_config,
        "get_video_model_name",
        lambda: "wan3.0-video",
    )
    monkeypatch.setattr(model_config, "get_video_backend", lambda: "wan")
    monkeypatch.setattr(
        rx,
        "_assert_r2v_reference_budget",
        lambda *a, **k: None,
    )
    first = _element("e1", start=0)
    second = _element("e2", start=4000)
    project, timeline = _project([first, second])
    _publish_artifact(project, "aa", "img-1", media_type="image/png")
    _publish_artifact(project, "bb", "vid-1", media_type="video/mp4")
    _publish_artifact(project, "cc", "img-2", media_type="image/png")
    frame = _frame_entry(tmp_path)
    tail_path = tmp_path / "tail_clip.mp4"
    tail_path.write_bytes(b"fake-clip")
    tail = sc._build_entry(
        "tail_clip",
        path=tail_path,
        prev_version="prev-version-1",
        prev_element_id="e1",
        media_type="video/mp4",
        role_label="上一段尾段",
        duration_seconds=3.0,
    )
    monkeypatch.setattr(
        rx,
        "extract_continuity_artifacts",
        lambda **kw: ContinuityBundle(
            predecessor_element_id="e1",
            predecessor_video_version_id="prev-version-1",
            entries=(frame, tail),
        ),
    )

    ids, labels, suffix, _voices = rx._apply_continuity_to_references(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
        version_ids=["img-1", "vid-1", "img-2"],
        urls=[],
        checksums=[],
        provenance=[],
        read_set=[],
        voice_urls=[],
        output_duration_seconds=4,
    )
    # Two plan images -> last frame is 图3; one plan video -> tail 视频2.
    assert "[Image 3]" in suffix
    assert "将视频2向后延长" in suffix
    block = rx._append_reference_role_mapping(
        "镜头描述。",
        project,
        list(ids),
        storyboard_id="img-1",
        continuity_labels=labels,
    )
    assert "[Image 2] = img-2" in block
    assert "[Image 3] = 上一段末帧" in block
    assert "视频1 = vid-1" in block
    for n in (1, 2, 3):
        assert block.count(f"[Image {n}]") == 1


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
    monkeypatch.setattr(sc, "_cut_both", lambda **kw: (entry,))
    monkeypatch.setattr(sc, "_continuity_cache", OrderedDict())
    monkeypatch.setattr(sc, "_continuity_extract_locks", {})
    inflight: dict = {}
    monkeypatch.setattr(sc, "_continuity_inflight", inflight)

    sc.extract_continuity_artifacts(
        project=project,
        project_root=tmp_path,
        timeline=timeline,
        element=second,
        include_tail_clip=False,
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


def test_claim_fingerprint_ignores_never_shipped_anchors() -> None:
    """Minor-2: with no anchors in the frozen payload (budget skip,
    ffmpeg missing) a prev reroll must not drift the submission
    fingerprint; payloads that did ship anchors still track it."""

    from services.media_files.r2v_execution import (
        _submission_input_fingerprint,
    )

    project, _timeline, _f, _s = _two_segment_project("prevV1")
    no_anchor_before = _submission_input_fingerprint(
        project,
        "e2",
        payload_refs=["sb-v1"],
    )
    _select_prev_video(project, "e1", "prevV2")
    assert (
        _submission_input_fingerprint(
            project,
            "e2",
            payload_refs=["sb-v1"],
        )
        == no_anchor_before
    )
    shipped_a = _submission_input_fingerprint(
        project,
        "e2",
        payload_refs=["sb-v1", "continuity:last_frame:prevV2"],
    )
    _select_prev_video(project, "e1", "prevV3")
    shipped_b = _submission_input_fingerprint(
        project,
        "e2",
        payload_refs=["sb-v1", "continuity:last_frame:prevV2"],
    )
    assert shipped_a != shipped_b


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
