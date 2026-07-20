"""Characterization tests for current clip stitch and transition planning."""

from __future__ import annotations

import pytest

from services.media import ffmpeg
from services.media.ffmpeg import (
    REMOTE_PROTOCOL_WHITELIST,
    build_stitch_plan,
    build_xfade_filter_chain,
)


pytestmark = pytest.mark.unit


def test_stitch_plan_orders_clips_escapes_manifest_and_keeps_pair_transitions(monkeypatch):
    readiness = {
        "status": "ok",
        "path": "/opt/ffmpeg",
        "binary": "ffmpeg",
        "blockers": [],
    }
    monkeypatch.setattr(ffmpeg, "ffmpeg_readiness", lambda: readiness)
    clips = [
        {
            "id": "clip-2",
            "order": 2,
            "video_url": "https://cdn.example.com/clip-2.mp4",
            "transition": "dissolve",
        },
        {
            "id": "clip-1",
            "order": 1,
            "video_url": "/tmp/clip-1's.mp4",
            "transition": "fade",
        },
    ]

    plan = build_stitch_plan(clips, "exports/final.mp4")

    assert plan["can_stitch"] is True
    assert plan["ordered_clip_ids"] == ["clip-1", "clip-2"]
    assert plan["transition_pairs"] == ["cut", "dissolve"]
    assert plan["strategy"] == "ffmpeg_xfade_acrossfade"
    assert plan["manifest"] == (
        "ffconcat version 1.0\n"
        "file '/tmp/clip-1\\'s.mp4'\n"
        "file 'https://cdn.example.com/clip-2.mp4'\n"
    )
    assert plan["uses_remote_sources"] is True
    assert plan["protocol_whitelist"] == REMOTE_PROTOCOL_WHITELIST
    assert plan["command"] == [
        "/opt/ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-protocol_whitelist",
        REMOTE_PROTOCOL_WHITELIST,
        "-i",
        "concat.txt",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "final.mp4",
    ]
    assert [item["key"] for item in plan["quality_checks"]] == [
        "stream_compatibility",
        "audio_continuity",
        "color_consistency",
        "transition_review",
    ]
    assert [item["key"] for item in plan["agent_review_notes"]] == [
        "transition_pairs",
        "color_sampling",
        "remote_cache",
        "semantic_bridge",
    ]


def test_xfade_chain_normalizes_video_and_synthesizes_missing_audio():
    chain = build_xfade_filter_chain(
        [5.0, 6.0],
        ["cut", "match_cut"],
        transition_duration=0.4,
        has_audio=[False, True],
        target_width=1280,
        target_height=720,
        target_fps=24,
        xfade_type="dissolve",
    )

    assert (
        "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24.0,"
        "format=yuv420p,setpts=PTS-STARTPTS[v0]"
    ) in chain
    assert (
        "[0:a]anullsrc=channel_layout=stereo:sample_rate=44100:d=5.000[a0]"
    ) in chain
    assert (
        "[v0][v1]xfade=transition=dissolve:duration=0.400:offset=4.600[vchain1]"
    ) in chain
    assert "[ai0][ai1]acrossfade=d=0.400:c1=tri:c2=tri[achain1]" in chain
    assert chain.endswith(
        "[vchain1]format=yuv420p[vout];"
        "[achain1]aresample=async=1[aout]"
    )


def test_xfade_chain_rejects_mismatched_duration_and_transition_counts():
    with pytest.raises(
        ValueError,
        match=r"durations/transitions length mismatch: 2 vs 1",
    ):
        build_xfade_filter_chain([5.0, 6.0], ["cut"])
