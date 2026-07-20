from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from schemas.projects import ProjectCreateRequest
from services.media.ai_edit import content_type_rules
from services.media.ai_edit import core as ai_edit_core
from services.media.ai_edit.audio_segments import find_enclosing_sentence_boundaries

pytestmark = pytest.mark.unit


def _segments() -> list[dict[str, object]]:
    return [
        {"start": 0.0, "end": 3.0, "text": "我从小在海边长大"},
        {"start": 3.0, "end": 6.5, "text": "每天清晨都去赶海"},
        {"start": 6.5, "end": 9.0, "text": "后来搬到了城市"},
        {"start": 9.0, "end": 14.0, "text": "最想念海浪的声音"},
        {"start": 14.0, "end": 16.5, "text": "它一直在我脑海里"},
        {"start": 16.5, "end": 22.0, "text": "我把这段记忆写进书里"},
        {"start": 22.0, "end": 24.5, "text": "希望更多人能听见"},
        {"start": 24.5, "end": 30.0, "text": "这是我最珍视的童年"},
        {"start": 30.0, "end": 35.0, "text": "采访者问到创作灵感"},
        {"start": 35.0, "end": 40.0, "text": "受访者谈到海边生活的细节"},
        {"start": 40.0, "end": 45.0, "text": "提到家人对他的影响"},
        {"start": 45.0, "end": 50.0, "text": "情绪变得激动起来"},
        {"start": 50.0, "end": 55.0, "text": "讲到最难忘的记忆"},
        {"start": 55.0, "end": 60.0, "text": "声音有些哽咽"},
        {"start": 60.0, "end": 65.0, "text": "最后总结了人生感悟"},
        {"start": 65.0, "end": 70.0, "text": "希望对观众有启发"},
    ]


def _interview_plan(source_url: str = "file:///tmp/interview.mp4") -> dict:
    return {
        "summary": "采访剪辑方案",
        "target_duration": 100.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": source_url,
                "start": 0.5,
                "end": 16.3,
                "duration": 15.8,
                "order": 1,
                "transition": "cut",
                "reason": "开场观点",
            },
            {
                "clip_id": "clip-02",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": source_url,
                "start": 18.4,
                "end": 34.2,
                "duration": 15.8,
                "order": 2,
                "transition": "cut",
                "reason": "核心金句",
            },
            {
                "clip_id": "clip-03",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": source_url,
                "start": 36.0,
                "end": 52.1,
                "duration": 16.1,
                "order": 3,
                "transition": "cut",
                "reason": "情绪高点",
            },
            {
                "clip_id": "clip-04",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": source_url,
                "start": 54.0,
                "end": 70.0,
                "duration": 16.0,
                "order": 4,
                "transition": "cut",
                "reason": "收尾",
            },
        ],
        "storyboard": [],
        "audio_plan": {},
    }


def test_interview_rules_and_project_contract_are_available() -> None:
    rules = content_type_rules.get_rules("interview")
    assert rules["label"] == "采访"
    assert "完整语句" in content_type_rules.build_criteria_block("interview")
    assert "60 秒" in rules["duration_constraint"]
    assert "120 秒" in rules["duration_constraint"]
    assert "60 秒" in content_type_rules.build_criteria_block("interview")
    request = ProjectCreateRequest.model_validate(
        {
            "clientRequestId": "interview-project",
            "name": "采访项目",
            "scenario": "video_edit",
            "contentType": "interview",
        }
    )
    assert request.content_type == "interview"


def test_interview_snaps_file_asset_boundaries_and_caps_whole_clips(monkeypatch,
) -> None:
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 70.0)
    asr_lookup = {"version-a": _segments()}

    result = ai_edit_core._snap_and_cap_for_interview(
        _interview_plan(),
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        asr_lookup,
    )

    assert sum(clip["duration"] for clip in result["timeline"]) <= 120.0
    assert len(result["timeline"]) <= 4
    assert [clip["order"] for clip in result["timeline"]] == list(
        range(1, len(result["timeline"]) + 1)
    )
    assert all(clip.get("transcript") for clip in result["timeline"])
    assert len(result["storyboard"]) == len(result["timeline"])
    assert {panel["clip_id"] for panel in result["storyboard"]} == {
        clip["clip_id"] for clip in result["timeline"]
    }


def test_interview_remote_source_keeps_original_timestamps_without_asr() -> None:
    plan = _interview_plan("https://media.example/interview.mp4")
    for clip in plan["timeline"]:
        clip.pop("asset_version_id", None)
    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
    )
    assert result["timeline"][0]["start"] == 0.5
    assert result["timeline"][0]["end"] == 16.3


def test_interview_panel_keeps_original_clip_identity_after_reorder(monkeypatch,
) -> None:
    plan = _interview_plan()
    late, early = plan["timeline"][:2]
    late.update({"clip_id": "clip-late", "start": 10.0, "end": 14.0, "duration": 4.0})
    early.update({"clip_id": "clip-early", "start": 0.0, "end": 4.0, "duration": 4.0})
    plan["timeline"] = [late, early]
    plan["storyboard"] = [
        {
            "panel_id": "panel-late",
            "clip_id": "clip-late",
            "order": 1,
            "title": "后段观点",
            "description": "后段",
            "source_asset_id": "video-a",
            "timestamp": 12.0,
        },
        {
            "panel_id": "panel-early",
            "clip_id": "clip-early",
            "order": 2,
            "title": "开场观点",
            "description": "开场",
            "source_asset_id": "video-a",
            "timestamp": 2.0,
        },
    ]

    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
    )

    clips = {clip["clip_id"]: clip for clip in result["timeline"]}
    panels = {panel["panel_id"]: panel for panel in result["storyboard"]}
    assert clips[panels["panel-late"]["clip_id"]]["start"] == 10.0
    assert clips[panels["panel-early"]["clip_id"]]["start"] == 0.0


def test_normalize_synthesizes_panels_from_the_normalized_timeline(monkeypatch) -> None:
    fallback = {
        "summary": "fallback",
        "target_duration": 4.0,
        "timeline": [],
        "storyboard": [{"clip_id": "heuristic-only"}],
        "audio_plan": {},
    }
    monkeypatch.setattr(ai_edit_core, "_heuristic_plan", lambda *_args: deepcopy(fallback))
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 30.0)
    result = ai_edit_core._normalize_plan(
        {
            "summary": "model",
            "timeline": [
                {
                    "clip_id": "vlm-clip",
                    "asset_id": "video-a",
                    "start": 2.0,
                    "end": 6.0,
                    "duration": 4.0,
                    "order": 1,
                    "reason": "完整观点",
                }
            ],
            "storyboard": [],
            "audio_plan": {},
        },
        {"id": "project-general", "contentType": "general"},
        {"duration": 10.0},
        [{"id": "video-a", "name": "a.mp4", "url": "file:///tmp/a.mp4"}],
        "保留观点",
    )
    assert result["storyboard"][0]["clip_id"] == result["timeline"][0]["clip_id"]
    assert result["storyboard"][0]["clip_id"] != "heuristic-only"
    assert result["storyboard"][0]["timestamp"] == 4.0


def test_interview_director_generates_overlay_during_semantic_selection(monkeypatch) -> None:
    project = {
        "id": "project-interview",
        "contentType": "interview",
        "plan": {
            "sections": [
                {
                    "units": [
                        {
                            "id": "edit-1",
                            "duration": 60,
                            "materialVersionRefs": ["asset-version-interview"],
                            "analysisRefs": [
                                "analysis://asset-version-interview@analysis-interview"
                            ],
                        }
                    ]
                }
            ]
        },
        "assets": [
            {
                "id": "interview-video",
                "versionId": "asset-version-interview",
                "name": "采访.mp4",
                "mediaType": "video",
                "url": "file:///tmp/interview.mp4",
            }
        ],
        "sourceIntelligence": [
            {
                "analysisRef": "analysis://asset-version-interview@analysis-interview",
                "assetVersionId": "asset-version-interview",
                "summary": "受访者坐在室内讲述成长经历。",
                "semanticEntries": [
                    {
                        "id": "interview-opening",
                        "startMs": 0,
                        "endMs": 60000,
                        "confidence": 0.9,
                        "text": "受访者面对镜头平静讲述海边成长经历",
                        "tags": ["受访者", "室内", "讲述"],
                    }
                ],
            }
        ],
    }
    calls = 0

    async def director(prompt, **_kwargs):
        nonlocal calls
        calls += 1
        assert '"kind": "interview_summary"' in prompt
        return json.dumps(
            {
                "summary": "以成长经历作为采访开场",
                "clips": [
                    {
                        "candidateId": "candidate-001",
                        "start": 0,
                        "end": 60,
                        "reason": "建立人物背景",
                        "editorialRole": "opening",
                        "transition": "cut",
                        "overlayCopy": {
                            "kind": "interview_summary",
                            "text": "讲述海边成长的经历",
                            "appearAt": 0,
                            "duration": 60,
                        },
                    }
                ],
                "audio_plan": {},
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai_edit_core.model_config, "get_text_api_key", lambda: "key")
    monkeypatch.setattr(ai_edit_core.text_model, "chat_completion", director)
    monkeypatch.setattr(
        ai_edit_core,
        "_write_storyboard_sheet_with_retry",
        lambda *_args, **_kwargs: "/generated/storyboard.svg",
    )

    envelope = asyncio.run(ai_edit_core.build_ai_edit_plan(project, "edit-1"))

    assert calls == 1
    assert envelope["plan"]["timeline"][0]["overlay_copy"] == {
        "kind": "interview_summary",
        "text": "讲述海边成长的经历",
        "appear_at": 0.0,
        "duration": 60.0,
    }


def test_execute_interview_adds_summary_title_card(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    readiness = {"status": "ok", "path": "/usr/bin/ffmpeg", "blockers": []}
    monkeypatch.setattr(ai_edit_core, "ffmpeg_readiness", lambda: readiness)
    monkeypatch.setattr(ai_edit_core, "ensure_task_work_subdir", lambda *_parts: tmp_path)
    monkeypatch.setattr(ai_edit_core, "_source_local_path", lambda *_args: source)
    monkeypatch.setattr(ai_edit_core, "_probe_video_size", lambda _path: (640, 360))
    monkeypatch.setattr(
        ai_edit_core,
        "media_url_for",
        lambda path: f"/generated/task-work/interview/{path.name}",
    )
    monkeypatch.setattr(
        ai_edit_core.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="1234567890abcdef"),
    )

    rendered: list[dict[str, object]] = []

    def render_summary(**kwargs):
        rendered.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"rendered")
        return SimpleNamespace(success=True, error="")

    async def unexpected_model_call(*_args, **_kwargs):
        raise AssertionError("execution must not generate interview copy")

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"media")
        return Result()

    monkeypatch.setattr(ai_edit_core, "render_interview_summary_overlay", render_summary)
    monkeypatch.setattr(ai_edit_core.text_model, "chat_completion", unexpected_model_call)
    monkeypatch.setattr(ai_edit_core.subprocess, "run", run)
    project = {
        "id": "project-interview",
        "contentType": "interview",
        "plan": {
            "sections": [
                {"units": [{"id": "edit-1", "taskType": "edit", "duration": 60.0}]}
            ]
        },
    }
    plan = {
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "source_url": "file:///tmp/source.mp4",
                "start": 0.0,
                "end": 4.0,
                "duration": 4.0,
                "order": 1,
                "transition": "cut",
                "reason": "成长回忆",
                "overlay_copy": {
                    "kind": "interview_summary",
                    "text": "讲述海边成长的记忆",
                    "appear_at": 0.0,
                    "duration": 4.0,
                },
            }
        ]
    }
    result = asyncio.run(ai_edit_core.execute_ai_edit_plan(project, "edit-1", plan))
    assert result["success"] is True
    assert result["updated_timeline"][0]["overlay_copy"]["text"] == "讲述海边成长的记忆"
    assert len(rendered) == 1
    assert rendered[0]["text"] == "讲述海边成长的记忆"
    assert rendered[0]["appear_at"] == 0.0
    assert rendered[0]["duration"] == 4.0


def test_interview_duration_is_clamped_to_60_120_range(monkeypatch) -> None:
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 200.0)

    plan_below = _interview_plan()
    result_below = ai_edit_core._snap_and_cap_for_interview(
        plan_below,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 30.0},
    )
    total_below = sum(clip["duration"] for clip in result_below["timeline"])
    assert 60.0 <= total_below <= 120.0

    plan_above = _interview_plan()
    result_above = ai_edit_core._snap_and_cap_for_interview(
        plan_above,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 180.0},
    )
    assert sum(clip["duration"] for clip in result_above["timeline"]) <= 120.0


def test_find_enclosing_sentence_boundaries_returns_outermost_sentence() -> None:
    segments = _segments()
    snap_start, snap_end = find_enclosing_sentence_boundaries(4.0, 8.0, segments)
    assert snap_start == 3.0
    assert snap_end == 9.0


def test_find_enclosing_sentence_boundaries_empty_segments() -> None:
    assert find_enclosing_sentence_boundaries(1.0, 5.0, []) == (None, None)


def test_find_enclosing_sentence_boundaries_no_match() -> None:
    segments = [{"start": 5.0, "end": 10.0, "text": "only sentence"}]
    snap_start, snap_end = find_enclosing_sentence_boundaries(1.0, 3.0, segments)
    assert snap_start is None
    assert snap_end == 10.0


def test_interview_snap_falls_back_to_enclosing_boundaries(monkeypatch) -> None:
    segments = [
        {"start": 0.0, "end": 3.0, "text": "第一句"},
        {"start": 3.0, "end": 6.0, "text": "第二句"},
        {"start": 10.0, "end": 14.0, "text": "第三句"},
        {"start": 14.0, "end": 18.0, "text": "第四句"},
    ]
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 14.0)

    plan = {
        "summary": "采访",
        "target_duration": 10.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": "file:///tmp/interview.mp4",
                "start": 4.0,
                "end": 12.0,
                "duration": 8.0,
                "order": 1,
                "transition": "cut",
                "reason": "中间片段",
            },
        ],
        "storyboard": [],
        "audio_plan": {},
    }
    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        {"version-a": segments},
    )
    clip = result["timeline"][0]
    # start=4.0 (round) → tolerance=3.0 → nearest sentence START >= 4.0-3.0=1.0
    # → 3.0 (distance 1.0) → snaps to 3.0
    assert clip["start"] == 3.0
    # end=12.0 (round) → tolerance=3.0 → nearest sentence END <= 12.0+3.0=15.0
    # → 14.0 (distance 2.0) → snaps to 14.0
    assert clip["end"] == 14.0


def test_snap_to_asr_boundary_snaps_round_to_nearest_sentence() -> None:
    from services.media.ai_edit.core import _snap_to_asr_boundary
    segments = [
        {"start": 0.0, "end": 3.2, "text": "第一句话"},
        {"start": 3.2, "end": 7.8, "text": "第二句话"},
        {"start": 7.8, "end": 12.4, "text": "第三句话"},
    ]
    # prefer_end=False (clip start): within tolerance → nearest start
    # 4.0 → nearest start >= 2.0 → 3.2 (distance 0.8)
    assert _snap_to_asr_boundary(4.0, segments, tolerance=2.0, prefer_end=False) == 3.2
    # 9.0 → nearest start >= 7.0 → 7.8 (distance 1.2)
    assert _snap_to_asr_boundary(9.0, segments, tolerance=2.0, prefer_end=False) == 7.8
    # 11.0 → no start >= 9.0 → fallback: current sentence start (largest <= 11.0) → 7.8
    assert _snap_to_asr_boundary(11.0, segments, tolerance=2.0, prefer_end=False) == 7.8

    # prefer_end=True (clip end): within tolerance → nearest end >= timestamp
    # 4.0 → nearest end >= 4.0 within 2.0 → none (7.8 is 3.8 away) → fallback: earliest end >= 4.0 → 7.8
    assert _snap_to_asr_boundary(4.0, segments, tolerance=2.0, prefer_end=True) == 7.8
    # 9.0 → nearest end >= 9.0 within 2.0 → none (12.4 is 3.4 away) → fallback: earliest end >= 9.0 → 12.4
    assert _snap_to_asr_boundary(9.0, segments, tolerance=2.0, prefer_end=True) == 12.4
    # 11.0 → nearest end >= 11.0 within 2.0 → 12.4 (distance 1.4)
    assert _snap_to_asr_boundary(11.0, segments, tolerance=2.0, prefer_end=True) == 12.4


def test_snap_to_asr_boundary_returns_original_when_no_match() -> None:
    from services.media.ai_edit.core import _snap_to_asr_boundary
    segments = [{"start": 0.0, "end": 3.0, "text": "only"}]
    # 20.0 past all segments → fallback: current sentence start (largest <= 20.0) → 0.0
    assert _snap_to_asr_boundary(20.0, segments, tolerance=2.0, prefer_end=False) == 0.0
    # Empty segments → always returns original
    assert _snap_to_asr_boundary(20.0, [], tolerance=2.0, prefer_end=True) == 20.0


def test_semantic_agent_auto_corrects_round_timestamps_for_interview() -> None:
    candidate = {
        "candidateId": "candidate-001",
        "assetId": "video-a",
        "assetVersionId": "ver-1",
        "assetName": "interview.mp4",
        "asset": {"url": "file:///tmp/interview.mp4"},
        "start": 0.0,
        "end": 20.0,
        "transcriptSegments": [
            {"start": 0.0, "end": 3.2, "text": "我从小在海边长大"},
            {"start": 3.2, "end": 7.8, "text": "每天清晨都去赶海"},
            {"start": 7.8, "end": 12.4, "text": "后来搬到了城市"},
            {"start": 12.4, "end": 18.6, "text": "最想念海浪的声音"},
        ],
        "description": "受访者讲述成长经历",
        "analysisRef": "analysis-1",
        "semanticEntryId": "se-1",
    }
    candidates_by_id = {"candidate-001": candidate}
    payload = {
        "summary": "采访方案",
        "clips": [
            {
                "candidateId": "candidate-001",
                "start": 0,
                "end": 9,
                "reason": "开场",
                "editorialRole": "opening",
                "transition": "cut",
                "overlayCopy": {
                    "kind": "interview_summary",
                    "text": "海边成长故事",
                    "appearAt": 0,
                    "duration": 7,
                },
            }
        ],
        "audio_plan": {},
    }
    project = {"id": "p1", "contentType": "interview"}
    unit = {"duration": 60}

    plan = ai_edit_core._semantic_agent_plan_from_payload(
        payload,
        project=project,
        unit=unit,
        analyses=[],
        candidates_by_id=candidates_by_id,
    )
    clip = plan["timeline"][0]
    # start=0 → 0.0 (exact ASR sentence start match)
    assert clip["start"] == 0.0
    # end=9 → 12.4 (earliest sentence end >= 9, extends to include complete speech)
    assert clip["end"] == 12.4


def test_semantic_agent_snaps_to_asr_when_close() -> None:
    candidate = {
        "candidateId": "candidate-001",
        "assetId": "video-a",
        "assetVersionId": "ver-1",
        "assetName": "interview.mp4",
        "asset": {"url": "file:///tmp/interview.mp4"},
        "start": 0.0,
        "end": 20.0,
        "transcriptSegments": [
            {"start": 0.0, "end": 3.2, "text": "我从小在海边长大"},
            {"start": 3.2, "end": 7.8, "text": "每天清晨都去赶海"},
            {"start": 7.8, "end": 12.4, "text": "后来搬到了城市"},
            {"start": 12.4, "end": 18.6, "text": "最想念海浪的声音"},
        ],
        "description": "受访者讲述成长经历",
        "analysisRef": "analysis-1",
        "semanticEntryId": "se-1",
    }
    candidates_by_id = {"candidate-001": candidate}
    payload = {
        "summary": "采访方案",
        "clips": [
            {
                "candidateId": "candidate-001",
                "start": 1,
                "end": 9,
                "reason": "开场",
                "editorialRole": "opening",
                "transition": "cut",
                "overlayCopy": {
                    "kind": "interview_summary",
                    "text": "海边成长故事",
                    "appearAt": 0,
                    "duration": 7,
                },
            }
        ],
        "audio_plan": {},
    }
    project = {"id": "p1", "contentType": "interview"}
    unit = {"duration": 60}

    plan = ai_edit_core._semantic_agent_plan_from_payload(
        payload,
        project=project,
        unit=unit,
        analyses=[],
        candidates_by_id=candidates_by_id,
    )
    clip = plan["timeline"][0]
    # start=1 → nearest ASR start within 2.0: 0.0 (distance 1.0) → snaps to 0.0
    assert clip["start"] == 0.0
    # end=9 → 12.4 (earliest sentence end >= 9, extends to include complete speech)
    assert clip["end"] == 12.4


def test_find_nearest_boundary_prefers_later_end_for_clip_end() -> None:
    """Clip end should snap to a LATER sentence end, not an earlier one,
    even when the earlier end is closer by absolute distance."""
    from services.media.ai_edit.audio_segments import find_nearest_sentence_boundary

    segments = [
        {"start": 0.0, "end": 51.0, "text": "前半句"},
        {"start": 51.0, "end": 53.5, "text": "后半句"},
    ]
    # timestamp=52.1: earlier end 51.0 (dist 1.1) vs later end 53.5 (dist 1.4)
    # Safe direction (later end) should win to avoid truncating speech
    result = find_nearest_sentence_boundary(52.1, segments, tolerance=2.0, prefer_end=True)
    assert result == 53.5


def test_find_nearest_boundary_prefers_earlier_start_for_clip_start() -> None:
    """Clip start should snap to an EARLIER sentence start, not a later one,
    even when the later start is closer by absolute distance."""
    from services.media.ai_edit.audio_segments import find_nearest_sentence_boundary

    segments = [
        {"start": 4.5, "end": 8.0, "text": "前一句"},
        {"start": 5.5, "end": 10.0, "text": "后一句"},
    ]
    # timestamp=5.0: earlier start 4.5 (dist 0.5) vs later start 5.5 (dist 0.5)
    # Safe direction (earlier start) should win to avoid skipping speech
    result = find_nearest_sentence_boundary(5.0, segments, tolerance=1.0, prefer_end=False)
    assert result == 4.5


def test_find_nearest_boundary_returns_none_when_no_safe_match() -> None:
    """When no safe-direction boundary exists within tolerance, return None
    rather than a wrong-direction value that would truncate speech."""
    from services.media.ai_edit.audio_segments import find_nearest_sentence_boundary

    segments = [
        {"start": 0.0, "end": 3.0, "text": "第一句"},
        {"start": 10.0, "end": 15.0, "text": "第二句"},
    ]
    # timestamp=5.0, prefer_end=True: no end >= 5.0 within tolerance 2.0
    # Must return None (not 3.0 which would truncate speech)
    result = find_nearest_sentence_boundary(5.0, segments, tolerance=2.0, prefer_end=True)
    assert result is None

    # timestamp=8.0, prefer_end=False: no start <= 8.0 within tolerance 2.0
    # Must return None (not 10.0 which would skip speech)
    result = find_nearest_sentence_boundary(8.0, segments, tolerance=2.0, prefer_end=False)
    assert result is None


def test_snap_to_asr_prefers_later_end_for_clip_end() -> None:
    """_snap_to_asr_boundary should prefer later sentence ends for clip end."""
    from services.media.ai_edit.core import _snap_to_asr_boundary

    segments = [
        {"start": 0.0, "end": 51.0, "text": "前半句"},
        {"start": 51.0, "end": 53.5, "text": "后半句"},
    ]
    # timestamp=52.1: earlier end 51.0 (dist 1.1) vs later end 53.5 (dist 1.4)
    # Safe direction (later end) should win
    result = _snap_to_asr_boundary(52.1, segments, tolerance=2.0, prefer_end=True)
    assert result == 53.5


def test_snap_to_asr_prefers_earlier_start_for_clip_start() -> None:
    """_snap_to_asr_boundary should prefer earlier sentence starts for clip start."""
    from services.media.ai_edit.core import _snap_to_asr_boundary

    segments = [
        {"start": 4.5, "end": 8.0, "text": "前一句"},
        {"start": 5.5, "end": 10.0, "text": "后一句"},
    ]
    # timestamp=5.0: earlier start 4.5 (dist 0.5) vs later start 5.5 (dist 0.5)
    # Safe direction (earlier start) should win
    result = _snap_to_asr_boundary(5.0, segments, tolerance=1.0, prefer_end=False)
    assert result == 4.5


def test_interview_storyboard_timestamp_snapped_to_asr_boundary(monkeypatch) -> None:
    """Storyboard panel timestamp should snap to ASR sentence boundary, not stay as integer."""
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 70.0)
    asr_lookup = {"version-a": _segments()}

    plan = {
        "summary": "采访剪辑方案",
        "target_duration": 8.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": "file:///tmp/interview.mp4",
                "start": 14.0,
                "end": 22.0,
                "duration": 8.0,
                "order": 1,
                "transition": "cut",
                "reason": "情绪高点",
            },
        ],
        "storyboard": [
            {
                "panel_id": "panel-01",
                "clip_id": "clip-01",
                "timestamp": 18.0,
                "source_asset_id": "video-a",
            },
        ],
        "audio_plan": {},
    }

    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        asr_lookup,
    )

    panel = result["storyboard"][0]
    assert panel["timestamp"] == 16.5
    assert panel["timestamp"] != 18.0


def test_interview_extends_clips_when_below_60s_minimum(monkeypatch) -> None:
    """When total duration < 60s, clips should be extended toward source limits."""
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 80.0)
    segments = [
        {"start": 0.0, "end": 10.0, "text": "第一句"},
        {"start": 10.0, "end": 20.0, "text": "第二句"},
        {"start": 20.0, "end": 30.0, "text": "第三句"},
    ]

    plan = {
        "summary": "采访",
        "target_duration": 20.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": "file:///tmp/interview.mp4",
                "start": 0.0,
                "end": 10.0,
                "duration": 10.0,
                "order": 1,
                "transition": "cut",
                "reason": "开场",
            },
            {
                "clip_id": "clip-02",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": "file:///tmp/interview.mp4",
                "start": 10.0,
                "end": 20.0,
                "duration": 10.0,
                "order": 2,
                "transition": "cut",
                "reason": "展开",
            },
        ],
        "storyboard": [],
        "audio_plan": {},
    }

    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        {"version-a": segments},
    )

    total = sum(clip["duration"] for clip in result["timeline"])
    assert total >= 60.0

    last_clip = result["timeline"][-1]
    assert last_clip["end"] > 20.0


def test_interview_duration_extension_respects_source_limit(monkeypatch) -> None:
    """Extension should not exceed source asset duration."""
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 25.0)

    plan = {
        "summary": "采访",
        "target_duration": 10.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "short.mp4",
                "source_url": "file:///tmp/short.mp4",
                "start": 0.0,
                "end": 10.0,
                "duration": 10.0,
                "order": 1,
                "transition": "cut",
                "reason": "唯一片段",
            },
        ],
        "storyboard": [],
        "audio_plan": {},
    }

    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        {},
    )

    clip = result["timeline"][0]
    assert clip["end"] <= 25.0
    assert clip["duration"] <= 25.0


def test_interview_clip_end_extends_forward_not_backward(monkeypatch) -> None:
    """When clip end is past a sentence end beyond tolerance, extend to the
    NEXT sentence end (forward) instead of snapping back to the earlier one."""
    monkeypatch.setattr(ai_edit_core, "_media_duration_seconds", lambda *_args: 30.0)
    segments = [
        {"start": 0.0, "end": 10.0, "text": "第一句"},
        {"start": 10.0, "end": 20.0, "text": "第二句"},
        {"start": 20.0, "end": 30.0, "text": "第三句"},
        {"start": 30.0, "end": 40.0, "text": "第四句"},
    ]

    plan = {
        "summary": "采访",
        "target_duration": 60.0,
        "timeline": [
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "asset_version_id": "version-a",
                "asset_name": "interview.mp4",
                "source_url": "file:///tmp/interview.mp4",
                "start": 0.0,
                "end": 21.5,
                "duration": 21.5,
                "order": 1,
                "transition": "cut",
                "reason": "片段",
            },
        ],
        "storyboard": [],
        "audio_plan": {},
    }

    result = ai_edit_core._snap_and_cap_for_interview(
        plan,
        {"id": "project-interview", "contentType": "interview"},
        {"duration": 60.0},
        {"version-a": segments},
    )

    clip = result["timeline"][0]
    assert clip["end"] >= 21.5
    assert clip["end"] == 30.0
