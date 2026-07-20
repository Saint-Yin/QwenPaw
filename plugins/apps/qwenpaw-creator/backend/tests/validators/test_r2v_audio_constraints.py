# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Audio-aware R2V Unit splitting stays deterministic across the cutover."""

from services.validators.unit_segments import (
    normalize_storyboard_segments,
    parse_action_time,
    split_long_shot,
)


def _shot(duration: int, dialogue: str = "", action_timeline=None):
    return {
        "title": "shot",
        "duration": duration,
        "dialogue": dialogue,
        "action_timeline": action_timeline or [],
    }


def test_split_long_shot_prefers_action_timeline_boundary() -> None:
    shot = _shot(
        duration=30,
        dialogue="一句完整对白",
        action_timeline=[
            {"time": "0-5s", "action": "走向门口"},
            {"time": "5-12s", "action": "推门"},
            {"time": "12-30s", "action": "走远"},
        ],
    )
    chunks = split_long_shot(shot)
    assert len(chunks) >= 2
    assert chunks[0]["duration"] == 12
    assert chunks[0]["split_reason"] == "r2v_15s_at_action_boundary"
    assert chunks[0]["dialogue"] == "一句完整对白"
    assert all(chunk["dialogue"] == "" for chunk in chunks[1:])
    assert all("-" in beat["time"] for beat in chunks[1]["action_timeline"])


def test_split_long_shot_falls_back_to_equal_split_without_action_timeline() -> (
    None
):
    chunks = split_long_shot(_shot(duration=30, dialogue="对白"))
    assert [chunk["duration"] for chunk in chunks] == [15, 15]
    assert [chunk["dialogue"] for chunk in chunks] == ["对白", ""]


def test_normalize_pushes_dialogue_shot_whole_to_next_unit() -> None:
    segment = {
        "segment_number": 1,
        "title": "段",
        "story_text": "故事",
        "shots": [
            _shot(duration=10, dialogue="前半句"),
            _shot(duration=8, dialogue="完整一句对白"),
        ],
    }
    normalized = normalize_storyboard_segments([segment])

    assert [item["duration"] for item in normalized] == [10, 8]
    assert [item["shots"][0]["dialogue"] for item in normalized] == [
        "前半句",
        "完整一句对白",
    ]
    assert all(item["duration"] <= 15 for item in normalized)


def test_short_segment_passes_through_without_losing_dialogue() -> None:
    segment = {
        "segment_number": 1,
        "title": "段",
        "story_text": "故事",
        "shots": [_shot(duration=5, dialogue="对白")],
    }
    normalized = normalize_storyboard_segments([segment])
    assert len(normalized) == 1
    assert normalized[0]["shots"][0]["duration"] == 5
    assert normalized[0]["shots"][0]["dialogue"] == "对白"


def test_parse_action_time_handles_strings_numbers_and_invalid_ranges() -> (
    None
):
    assert parse_action_time("2-5s") == (2.0, 5.0)
    assert parse_action_time("2-5") == (2.0, 5.0)
    assert parse_action_time(7) == (0.0, 7.0)
    assert parse_action_time("5-2s") is None
    assert parse_action_time("invalid") is None
