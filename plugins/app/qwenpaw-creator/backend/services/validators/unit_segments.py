"""Audio-aware normalization of planned shots into <=15s R2V Units."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


MAX_R2V_UNIT_DURATION_SECONDS = 15

_TIME_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s?", re.IGNORECASE
)


def positive_duration(value: Any, fallback: int = 1) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, duration)


def parse_action_time(value: Any) -> tuple[float, float] | None:
    """Parse an action beat such as ``2-5s`` into a half-open range."""

    if isinstance(value, (int, float)):
        end = float(value)
        return (0.0, end)
    if not isinstance(value, str):
        return None
    match = _TIME_RANGE_RE.search(value)
    if not match:
        return None
    try:
        start = float(match.group(1))
        end = float(match.group(2))
    except ValueError:
        return None
    if end <= start:
        return None
    return (start, end)


def action_boundaries(shot: dict[str, Any]) -> list[float]:
    boundaries: list[float] = []
    for beat in shot.get("action_timeline") or []:
        parsed = parse_action_time(beat.get("time"))
        if parsed:
            boundaries.append(parsed[1])
    return sorted(boundaries)


def rewrite_action_timeline(
    action_timeline: list[dict[str, Any]],
    offset: float,
) -> list[dict[str, Any]]:
    rewritten: list[dict[str, Any]] = []
    for beat in action_timeline or []:
        parsed = parse_action_time(beat.get("time"))
        if not parsed:
            rewritten.append(deepcopy(beat))
            continue
        new_start = max(0.0, parsed[0] - offset)
        new_end = max(0.0, parsed[1] - offset)
        new_beat = deepcopy(beat)
        new_beat["time"] = f"{new_start:g}-{new_end:g}s"
        rewritten.append(new_beat)
    return rewritten


def split_long_shot(shot: dict[str, Any]) -> list[dict[str, Any]]:
    """Split only an individually overlong shot, preserving dialogue once."""

    duration = positive_duration(shot.get("duration"))
    if duration <= MAX_R2V_UNIT_DURATION_SECONDS:
        next_shot = deepcopy(shot)
        next_shot["duration"] = duration
        return [next_shot]

    boundaries = action_boundaries(shot)
    anchor = None
    for boundary in reversed(boundaries):
        if boundary <= MAX_R2V_UNIT_DURATION_SECONDS and boundary >= 1.0:
            anchor = boundary
            break
    if anchor is None:
        anchor = float(MAX_R2V_UNIT_DURATION_SECONDS)

    chunks: list[dict[str, Any]] = []
    remaining = float(duration)
    cursor = 0.0
    part = 1
    dialogue_kept = False
    while remaining > 0:
        if remaining <= MAX_R2V_UNIT_DURATION_SECONDS:
            chunk_duration = float(remaining)
        else:
            chunk_duration = float(
                anchor if part == 1 else min(MAX_R2V_UNIT_DURATION_SECONDS, remaining)
            )
        next_shot = deepcopy(shot)
        next_shot["duration"] = (
            int(round(chunk_duration))
            if chunk_duration.is_integer()
            else round(chunk_duration, 2)
        )
        next_shot["title"] = f"{shot.get('title', 'shot')} part {part}"
        next_shot["split_from_duration"] = duration
        next_shot["split_reason"] = "r2v_15s_at_action_boundary"
        if part == 1:
            dialogue_kept = True
        else:
            next_shot["dialogue"] = ""
        next_shot["action_timeline"] = rewrite_action_timeline(
            shot.get("action_timeline") or [],
            cursor,
        )
        chunks.append(next_shot)
        cursor += chunk_duration
        remaining -= chunk_duration
        part += 1

    if not dialogue_kept and shot.get("dialogue"):
        chunks[0]["dialogue"] = shot.get("dialogue")
    return chunks


def normalize_storyboard_segments(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize planned segments into audio-aware, production-safe R2V Units.

    A dialogue-bearing shot that would overflow the current Unit moves intact to
    the next Unit.  Only a shot that is itself longer than 15 seconds is split,
    preferring a visible action boundary at or before 15 seconds.
    """

    normalized: list[dict[str, Any]] = []

    for source_segment in segments:
        current_shots: list[dict[str, Any]] = []
        current_duration = 0
        source_shots = source_segment.get("shots") or []
        source_was_split = False

        for source_shot in source_shots:
            shots_to_add = split_long_shot(source_shot)
            for shot in shots_to_add:
                shot_duration = positive_duration(shot.get("duration"))
                if (
                    current_shots
                    and current_duration + shot_duration > MAX_R2V_UNIT_DURATION_SECONDS
                ):
                    source_was_split = True
                    next_segment = deepcopy(source_segment)
                    next_segment["shots"] = current_shots
                    next_segment["duration"] = current_duration
                    next_segment["split_reason"] = "r2v_15_second_limit"
                    normalized.append(next_segment)
                    current_shots = []
                    current_duration = 0

                current_shots.append(shot)
                current_duration += shot_duration

        next_segment = deepcopy(source_segment)
        next_segment["shots"] = current_shots
        next_segment["duration"] = current_duration
        if source_was_split:
            next_segment["split_reason"] = "r2v_15_second_limit"
        normalized.append(next_segment)

    for index, segment in enumerate(normalized, start=1):
        segment["segment_number"] = index
        for shot_index, shot in enumerate(segment.get("shots") or [], start=1):
            shot["shot_number"] = shot_index

    return normalized


def summarize_storyboard_normalization(
    source_segments: list[dict[str, Any]],
    normalized_segments: list[dict[str, Any]],
) -> dict[str, int | bool]:
    split_segment_count = sum(
        1
        for segment in source_segments
        if sum(
            positive_duration(shot.get("duration"))
            for shot in segment.get("shots") or []
        )
        > MAX_R2V_UNIT_DURATION_SECONDS
    )
    split_shot_count = sum(
        1
        for segment in source_segments
        for shot in segment.get("shots") or []
        if positive_duration(shot.get("duration")) > MAX_R2V_UNIT_DURATION_SECONDS
    )

    return {
        "input_segment_count": len(source_segments),
        "output_clip_count": len(normalized_segments),
        "split_segment_count": split_segment_count,
        "split_shot_count": split_shot_count,
        "max_clip_duration_seconds": MAX_R2V_UNIT_DURATION_SECONDS,
        "fits_r2v_limit": storyboard_segments_fit_r2v_limit(normalized_segments),
    }


def storyboard_segments_fit_r2v_limit(segments: list[dict[str, Any]]) -> bool:
    for segment in segments:
        shots = segment.get("shots") or []
        duration = sum(positive_duration(shot.get("duration")) for shot in shots)
        if duration > MAX_R2V_UNIT_DURATION_SECONDS:
            return False
        if any(
            positive_duration(shot.get("duration")) > MAX_R2V_UNIT_DURATION_SECONDS
            for shot in shots
        ):
            return False
    return True


__all__ = [
    "MAX_R2V_UNIT_DURATION_SECONDS",
    "action_boundaries",
    "normalize_storyboard_segments",
    "parse_action_time",
    "positive_duration",
    "rewrite_action_timeline",
    "split_long_shot",
    "storyboard_segments_fit_r2v_limit",
    "summarize_storyboard_normalization",
]
