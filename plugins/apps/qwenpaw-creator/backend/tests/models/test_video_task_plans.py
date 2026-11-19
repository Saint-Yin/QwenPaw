# -*- coding: utf-8 -*-
"""Decision-matrix tests for the Wan3.0 task-shape planner.

Pure facts in, pure plan out — every rule branch of
``select_wan3_task_plan`` is pinned here, plus the unified continuity
dial (CREATOR_VIDEO_CONTINUITY with the legacy TAIL_CLIP alias).
"""

# pylint: disable=use-implicit-booleaness-not-comparison

from models.video_task_plans import (
    CONTINUITY_MODE_AUTO,
    CONTINUITY_MODE_OFF,
    CONTINUITY_MODE_WEAK,
    ContinuityFacts,
    VideoTaskShape,
    select_wan3_task_plan,
    video_continuity_mode,
)


def _facts(**overrides) -> ContinuityFacts:
    base = {
        "has_published_predecessor": True,
        "same_scene": True,
        "predecessor_duration_seconds": 8.0,
        "segment_duration_seconds": 10,
        "ffmpeg_ready": True,
        "video_extension_supported": True,
    }
    base.update(overrides)
    return ContinuityFacts(**base)


def test_off_mode_injects_nothing() -> None:
    plan = select_wan3_task_plan(_facts(), mode=CONTINUITY_MODE_OFF)
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is False
    assert plan.extension_material == ""


def test_no_predecessor_is_plain_omni() -> None:
    plan = select_wan3_task_plan(_facts(has_published_predecessor=False))
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is False


def test_missing_ffmpeg_drops_every_anchor() -> None:
    plan = select_wan3_task_plan(_facts(ffmpeg_ready=False))
    assert plan.last_frame_anchor is False
    assert plan.extension_material == ""


def test_non_continuation_model_falls_back_to_image_anchor() -> None:
    plan = select_wan3_task_plan(
        _facts(video_extension_supported=False),
    )
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is True
    assert plan.extension_material == ""
    assert plan.ratio == ""  # caller's project ratio wins


def test_scene_change_keeps_weak_anchor_not_extension() -> None:
    plan = select_wan3_task_plan(_facts(same_scene=False))
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is True
    assert plan.extension_material == ""


def test_weak_mode_never_ships_material() -> None:
    plan = select_wan3_task_plan(_facts(), mode=CONTINUITY_MODE_WEAK)
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is True
    assert plan.extension_material == ""


def test_same_scene_uses_whole_predecessor_video() -> None:
    plan = select_wan3_task_plan(_facts())
    assert plan.shape is VideoTaskShape.EXTEND
    assert plan.extension_material == "full"
    assert plan.material_duration_seconds == 8.0
    assert plan.ratio == "adaptive"
    # duration semantics: material + new (measured 2026-11-19).
    assert plan.submit_duration_seconds == 18
    assert plan.trim_offset_seconds == 8.0
    assert plan.last_frame_anchor is True


def test_long_predecessor_falls_back_to_trimmed_clip() -> None:
    plan = select_wan3_task_plan(
        _facts(predecessor_duration_seconds=20.0, segment_duration_seconds=10),
    )
    assert plan.shape is VideoTaskShape.EXTEND
    assert plan.extension_material == "clip"
    assert plan.material_duration_seconds == 5.0
    assert plan.submit_duration_seconds == 15
    assert plan.trim_offset_seconds == 5.0


def test_unmeasurable_predecessor_still_extends_with_clip() -> None:
    plan = select_wan3_task_plan(
        _facts(predecessor_duration_seconds=0.0),
    )
    # prev duration unknown: the full material cannot be budgeted, but
    # the 5s trimmed tail can.
    assert plan.extension_material == "clip"


def test_budget_exhaustion_degrades_to_image_anchor() -> None:
    plan = select_wan3_task_plan(
        _facts(
            predecessor_duration_seconds=20.0,
            segment_duration_seconds=25,
        ),
    )
    assert plan.shape is VideoTaskShape.OMNI_REFERENCE
    assert plan.last_frame_anchor is True
    assert plan.extension_material == ""


def test_full_material_budget_boundary_is_inclusive() -> None:
    # 15s material + 13s segment = 28 = 30 - headroom: still full.
    plan = select_wan3_task_plan(
        _facts(
            predecessor_duration_seconds=15.0,
            segment_duration_seconds=13,
        ),
    )
    assert plan.extension_material == "full"
    # one second more and the total passes the budget: clip fallback.
    plan = select_wan3_task_plan(
        _facts(
            predecessor_duration_seconds=15.0,
            segment_duration_seconds=14,
        ),
    )
    assert plan.extension_material == "clip"


def test_mode_dial_reads_unified_env_first(monkeypatch) -> None:
    monkeypatch.setenv("CREATOR_VIDEO_CONTINUITY", "weak")
    monkeypatch.setenv("CREATOR_CONTINUITY_TAIL_CLIP", "1")
    assert video_continuity_mode() == CONTINUITY_MODE_WEAK
    monkeypatch.setenv("CREATOR_VIDEO_CONTINUITY", "off")
    assert video_continuity_mode() == CONTINUITY_MODE_OFF
    monkeypatch.setenv("CREATOR_VIDEO_CONTINUITY", "AUTO")
    assert video_continuity_mode() == CONTINUITY_MODE_AUTO


def test_mode_dial_unknown_value_fails_toward_auto(monkeypatch) -> None:
    monkeypatch.setenv("CREATOR_VIDEO_CONTINUITY", "banana")
    assert video_continuity_mode() == CONTINUITY_MODE_AUTO


def test_mode_dial_legacy_alias(monkeypatch) -> None:
    monkeypatch.delenv("CREATOR_VIDEO_CONTINUITY", raising=False)
    monkeypatch.setenv("CREATOR_CONTINUITY_TAIL_CLIP", "0")
    assert video_continuity_mode() == CONTINUITY_MODE_WEAK
    monkeypatch.setenv("CREATOR_CONTINUITY_TAIL_CLIP", "1")
    assert video_continuity_mode() == CONTINUITY_MODE_AUTO
    monkeypatch.delenv("CREATOR_CONTINUITY_TAIL_CLIP", raising=False)
    assert video_continuity_mode() == CONTINUITY_MODE_AUTO
