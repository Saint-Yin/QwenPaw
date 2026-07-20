# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=chained-comparison,line-too-long,too-many-branches
# pylint: disable=too-many-nested-blocks,too-many-statements,unused-argument
"""AI editing plan and execution helpers."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote, urlparse

from models import config as model_config
from models import text_model
from services.media.ai_edit.audio_segments import (
    find_nearest_sentence_boundary,
)
from services.media.ai_edit.overlay_tools import (
    PET_OS_VIBES,
    render_interview_summary_overlay,
    render_pet_os_overlay,
)
from services.media.ffmpeg import ffmpeg_readiness
from services.observability import trace_event
from services.runtime_files.media_probe import MediaProbeError, probe_media
from services.runtime_files.runtime_dependencies import resolve_ffprobe
from services.validators.short_drama import duration_tolerance
from services.workspace.content_store import atomic_replace_bytes
from utils.logger import setup_logger
from utils.paths import (
    ensure_preview_subdir,
    ensure_task_work_subdir,
    media_path_from_url,
    media_url_for,
)
from utils.remote_download import download_remote_file
from utils.structured_output import extract_json_payload

logger = setup_logger("services.media.ai_edit.core")


def _find_unit(
    project: dict,
    unit_id: str,
) -> tuple[dict, dict] | tuple[None, None]:
    for section in project.get("plan", {}).get("sections", []) or []:
        for unit in section.get("units", []) or []:
            if unit.get("id") == unit_id:
                return section, unit
    return None, None


def _selected_video_assets(
    project: dict,
    unit: dict,
    material_asset_ids: list[str] | None = None,
) -> list[dict]:
    selected_ids = set(material_asset_ids or unit.get("materialRefs") or [])
    selected_version_ids = set(unit.get("materialVersionRefs") or [])
    assets = [
        asset
        for asset in project.get("assets", []) or []
        if asset.get("mediaType") == "video" and asset.get("url")
    ]
    if selected_version_ids:
        selected = [
            asset
            for asset in assets
            if str(asset.get("versionId") or "") in selected_version_ids
        ]
        if selected:
            return selected
    if selected_ids:
        selected = [
            asset for asset in assets if asset.get("id") in selected_ids
        ]
        if selected:
            return selected
    return [
        asset for asset in assets if asset.get("category") == "upload"
    ] or assets


def _asset_index(assets: list[dict]) -> dict[str, dict]:
    return {asset.get("id"): asset for asset in assets if asset.get("id")}


def _duration_target(unit: dict) -> int:
    raw = unit.get("duration") or sum(
        int(shot.get("duration", 0) or 0)
        for shot in unit.get("shots", []) or []
    )
    try:
        duration = int(raw)
    except (TypeError, ValueError):
        duration = 15
    return max(5, min(duration or 15, 180))


_INTERVIEW_MIN_DURATION = 60.0
_INTERVIEW_MAX_DURATION = 120.0


def _expected_overlay_kind(project: dict[str, Any]) -> str | None:
    if (
        project.get("contentType") == "pet_video"
        or project.get("scenario") == "pet_camera"
    ):
        return "pet_os"
    if project.get("contentType") == "interview":
        return "interview_summary"
    return None


def _validate_execution_overlay_copy(
    clip: dict[str, Any],
    *,
    expected_kind: str | None,
    clip_index: int,
    clip_duration: float,
) -> dict[str, Any] | None:
    """Treat overlay metadata as optional, best-effort decoration.

    Overlay must never block AI Edit planning or execution. Malformed or
    unsupported metadata is ignored instead of becoming a Runtime failure.
    """

    overlay = clip.get("overlay_copy")
    if not isinstance(overlay, dict):
        return None
    kind = str(overlay.get("kind") or "").strip()
    if kind not in {"pet_os", "interview_summary"}:
        return None
    text = str(overlay.get("text") or "").strip()
    if not text:
        return None
    appear_at = max(0.0, _safe_float(overlay.get("appear_at"), 0.0))
    if appear_at >= clip_duration:
        return None
    duration = min(
        max(
            0.001,
            _safe_float(overlay.get("duration"), clip_duration - appear_at),
        ),
        clip_duration - appear_at,
    )
    validated = {
        "kind": kind,
        "text": text,
        "appear_at": appear_at,
        "duration": duration,
    }
    if kind == "pet_os":
        vibe = str(overlay.get("vibe") or "").strip()
        validated["vibe"] = vibe if vibe in PET_OS_VIBES else "chill"
    return validated


def _build_asr_segments_lookup(
    analyses: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build a lookup from asset version ID to FunASR sentence segments (seconds)."""
    lookup: dict[str, list[dict[str, Any]]] = {}
    for analysis in analyses:
        version_id = str(analysis.get("assetVersionId") or "")
        if not version_id:
            continue
        segments: list[dict[str, Any]] = []
        for seg in analysis.get("transcript") or []:
            if not isinstance(seg, dict):
                continue
            start = round(_safe_float(seg.get("startMs"), 0) / 1000, 3)
            end = round(_safe_float(seg.get("endMs"), 0) / 1000, 3)
            text = str(seg.get("text") or "").strip()
            if end > start and text:
                segments.append({"start": start, "end": end, "text": text})
        if segments:
            lookup[version_id] = segments
    return lookup


def _selected_source_intelligence(
    project: dict[str, Any],
    unit: dict[str, Any],
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve exact analysis versions already selected by the edit Unit."""

    selected_versions = {
        str(asset.get("versionId") or "")
        for asset in assets
        if asset.get("versionId")
    }
    selected_refs = {
        str(value) for value in unit.get("analysisRefs", []) or [] if value
    }
    candidates = [
        dict(item)
        for item in project.get("sourceIntelligence", []) or []
        if isinstance(item, dict)
    ]
    if not candidates:
        candidates = [
            dict(item["sourceIntelligence"])
            for item in assets
            if isinstance(item.get("sourceIntelligence"), dict)
        ]
    return [
        item
        for item in candidates
        if str(item.get("assetVersionId") or "") in selected_versions
        and (
            not selected_refs
            or str(item.get("analysisRef") or "") in selected_refs
        )
        and isinstance(item.get("semanticEntries"), list)
        and item.get("semanticEntries")
    ]


_AI_EDIT_AGENT_SYSTEM_PROMPT = """你是 AI Editing Director。你只接收已经版本化的 Source Intelligence 文本候选目录，绝不能要求、推测或重新查看原视频。

你的职责是根据用户目标、成片时长和候选片段的客观描述完成语义剪辑：选择最合适的候选片段或其子区间，安排开场、发展、高潮和收尾，避免内容重复，并解释每个选择的叙事作用。

只输出严格 JSON，不要 Markdown。每个 clip 必须引用输入中真实存在的 candidateId，start/end 必须位于该候选的范围内。不得创造候选目录中不存在的画面、对象、动作或时间码。"""


def _semantic_agent_catalog(
    analyses: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build a URL-free candidate catalog for the text-only edit agent."""

    assets_by_version = {
        str(asset.get("versionId") or ""): asset for asset in assets
    }
    catalog: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for analysis in analyses:
        asset_version_id = str(analysis.get("assetVersionId") or "")
        asset = assets_by_version.get(asset_version_id)
        if asset is None:
            continue
        for semantic in analysis.get("semanticEntries", []) or []:
            if not isinstance(semantic, dict):
                continue
            semantic_start = _safe_float(semantic.get("startMs"), 0.0) / 1000
            semantic_end = _safe_float(semantic.get("endMs"), 0.0) / 1000
            if semantic_end <= semantic_start:
                continue
            candidate_id = f"candidate-{len(catalog) + 1:03d}"
            transcript_segments = [
                {
                    "start": round(
                        max(
                            0.0,
                            _safe_float(segment.get("startMs"), 0.0) / 1000,
                        ),
                        3,
                    ),
                    "end": round(
                        max(
                            0.0,
                            _safe_float(segment.get("endMs"), 0.0) / 1000,
                        ),
                        3,
                    ),
                    "text": str(segment.get("text") or "").strip(),
                }
                for segment in analysis.get("transcript", []) or []
                if isinstance(segment, dict)
                and _safe_float(segment.get("endMs"), 0.0)
                > semantic_start * 1000
                and _safe_float(segment.get("startMs"), 0.0)
                < semantic_end * 1000
                and str(segment.get("text") or "").strip()
                and _safe_float(segment.get("endMs"), 0.0)
                > _safe_float(segment.get("startMs"), 0.0)
            ]
            transcript_segments.sort(
                key=lambda item: (item["start"], item["end"]),
            )
            # A semantic interval may begin or end in the middle of a spoken
            # sentence. Expand only to the full boundaries of ASR segments that
            # overlap that interval so the Director can choose a complete utterance.
            start = min(
                [
                    semantic_start,
                    *(item["start"] for item in transcript_segments),
                ],
            )
            end = max(
                [semantic_end, *(item["end"] for item in transcript_segments)],
            )
            item = {
                "candidateId": candidate_id,
                "semanticEntryId": str(semantic.get("id") or ""),
                "analysisRef": str(analysis.get("analysisRef") or ""),
                "assetId": str(asset.get("id") or ""),
                "assetVersionId": asset_version_id,
                "assetName": str(asset.get("name") or ""),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "semanticStart": round(semantic_start, 3),
                "semanticEnd": round(semantic_end, 3),
                "confidence": max(
                    0.0,
                    min(1.0, _safe_float(semantic.get("confidence"), 0.5)),
                ),
                "description": str(semantic.get("text") or "").strip(),
                "transcript": " ".join(
                    segment["text"] for segment in transcript_segments
                ),
                "transcriptSegments": transcript_segments,
                "tags": [
                    str(value)
                    for value in semantic.get("tags", []) or []
                    if value
                ],
            }
            catalog.append(item)
            by_id[candidate_id] = {**item, "asset": asset}
    return catalog, by_id


def _snap_to_asr_boundary(
    timestamp: float,
    transcript_segments: list[dict[str, Any]],
    tolerance: float,
    prefer_end: bool,
) -> float:
    """Snap *timestamp* to the nearest ASR sentence boundary.

    For clip **end** (``prefer_end=True``): prefers sentence ends **>=**
    *timestamp* so the clip always includes complete speech.  Falls back
    to the earliest sentence end beyond tolerance, then keeps the
    original timestamp.  Never snaps to a sentence end before the
    timestamp, which would truncate speech.

    For clip **start** (``prefer_end=False``): prefers sentence starts
    **<=** *timestamp* so the clip always includes complete speech.
    Falls back to the latest sentence start beyond tolerance, then keeps
    the original timestamp.  Never snaps to a sentence start after the
    timestamp, which would skip speech.
    """
    if not transcript_segments:
        return timestamp

    if prefer_end:
        safe_best: float | None = None
        safe_distance = tolerance + 1
        any_later_end: float | None = None
        for seg in transcript_segments:
            seg_end = float(seg["end"])
            if seg_end >= timestamp:
                if any_later_end is None or seg_end < any_later_end:
                    any_later_end = seg_end
                distance = seg_end - timestamp
                if distance <= tolerance and distance < safe_distance:
                    safe_distance = distance
                    safe_best = seg_end
        if safe_best is not None:
            return safe_best
        return any_later_end if any_later_end is not None else timestamp
    else:
        safe_best = None
        safe_distance = tolerance + 1
        any_earlier_start: float | None = None
        for seg in transcript_segments:
            seg_start = float(seg["start"])
            if seg_start <= timestamp:
                if any_earlier_start is None or seg_start > any_earlier_start:
                    any_earlier_start = seg_start
                distance = timestamp - seg_start
                if distance <= tolerance and distance < safe_distance:
                    safe_distance = distance
                    safe_best = seg_start
        if safe_best is not None:
            return safe_best
        return (
            any_earlier_start if any_earlier_start is not None else timestamp
        )


def _asr_segment_containing(
    timestamp: float,
    transcript_segments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    containing = [
        segment
        for segment in transcript_segments
        if float(segment["start"]) + 0.001
        < timestamp
        < float(segment["end"]) - 0.001
    ]
    if not containing:
        return None
    return min(
        containing,
        key=lambda item: float(item["end"]) - float(item["start"]),
    )


def _review_clip_asr_boundaries(
    start: float,
    end: float,
    candidate: dict[str, Any],
    *,
    clip_id: str,
) -> dict[str, Any]:
    """Report possible sentence truncation without changing or rejecting the clip."""

    transcript_segments = [
        dict(item)
        for item in candidate.get("transcriptSegments", []) or []
        if isinstance(item, dict)
        and _safe_float(item.get("end"), 0.0)
        > _safe_float(item.get("start"), 0.0)
    ]
    if not transcript_segments:
        return {
            "source": "source_intelligence_transcript",
            "available": False,
            "risk_level": "none",
            "advisories": [],
        }

    advisories: list[str] = []
    start_segment = _asr_segment_containing(start, transcript_segments)
    end_segment = _asr_segment_containing(end, transcript_segments)
    if start_segment is not None:
        advisories.append(
            f"{clip_id} 起点 {start:.3f}s 位于 ASR 句子 "
            f"{float(start_segment['start']):.3f}-{float(start_segment['end']):.3f}s 内，"
            "存在从半句话开始的风险；建议结合叙事考虑使用句首或句尾。"
            f"文本：{str(start_segment.get('text') or '').strip()}",
        )
    if end_segment is not None:
        advisories.append(
            f"{clip_id} 终点 {end:.3f}s 位于 ASR 句子 "
            f"{float(end_segment['start']):.3f}-{float(end_segment['end']):.3f}s 内，"
            "存在半句话结束的风险；建议结合叙事考虑使用句首或句尾。"
            f"文本：{str(end_segment.get('text') or '').strip()}",
        )
    return {
        "source": "source_intelligence_transcript",
        "available": True,
        "risk_level": "warning" if advisories else "none",
        "start_inside_sentence": start_segment is not None,
        "end_inside_sentence": end_segment is not None,
        "advisories": advisories,
    }


def _semantic_agent_prompt(
    project: dict[str, Any],
    section: dict[str, Any],
    unit: dict[str, Any],
    analyses: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    goal: str,
) -> str:
    target = float(_duration_target(unit))
    is_interview = project.get("contentType") == "interview"
    if is_interview:
        target = _INTERVIEW_MAX_DURATION
    expected_overlay_kind = _expected_overlay_kind(project)
    prompt_candidates: list[dict[str, Any]] = []
    for item in catalog:
        prompt_item = {
            key: value
            for key, value in item.items()
            if key not in {"transcript", "transcriptSegments"}
        }
        transcript_segments = item.get("transcriptSegments", []) or []
        if transcript_segments:
            # Keep the model prompt compact: each ASR row is
            # [sentence_start_seconds, sentence_end_seconds, sentence_text].
            prompt_item["asr"] = [
                [segment["start"], segment["end"], segment["text"]]
                for segment in transcript_segments
            ]
        prompt_candidates.append(prompt_item)
    clip_schema: dict[str, Any] = {
        "candidateId": "candidate-001",
        "start": 0.3,
        "end": 4.7,
        "editorialBeat": "对应的叙事节拍",
        "reason": "选择理由",
        "editorialRole": "opening",
        "transition": "cut",
    }
    if expected_overlay_kind == "pet_os":
        clip_schema["overlayCopy"] = {
            "kind": "pet_os",
            "text": "宠物独白",
            "vibe": "chill",
            "appearAt": 0.2,
            "duration": 4.3,
        }
    elif expected_overlay_kind == "interview_summary":
        clip_schema["overlayCopy"] = {
            "kind": "interview_summary",
            "text": "采访片段总结",
            "appearAt": 0.2,
            "duration": 4.3,
        }
    output_schema = {
        "summary": "成片策略",
        "clips": [clip_schema],
        "audio_plan": {"bgm": "", "voiceover": "", "subtitle": ""},
    }
    payload = {
        "project": {
            "title": str(project.get("title") or project.get("name") or ""),
            "description": str(project.get("description") or ""),
            "scenario": project.get("scenario"),
            "contentType": project.get("contentType"),
        },
        "editIntent": goal or str(unit.get("narrative") or ""),
        "editorialStructure": {
            "sectionScript": str(section.get("script") or ""),
            "sectionNarrative": str(section.get("narrative") or ""),
            "unitContinuity": str(unit.get("continuity") or ""),
            "shots": [
                {
                    "id": str(item.get("id") or ""),
                    "description": str(item.get("description") or ""),
                    "duration": _safe_float(item.get("duration"), 0.0),
                }
                for item in unit.get("shots", []) or []
                if isinstance(item, dict)
            ],
        },
        "targetDurationSeconds": target,
        "sourceSummaries": [
            {
                "analysisRef": str(item.get("analysisRef") or ""),
                "summary": str(item.get("summary") or ""),
            }
            for item in analyses
        ],
        "candidates": prompt_candidates,
    }
    duration_instruction = (
        "要求：clips 按最终成片顺序排列；总时长尽量等于 targetDurationSeconds，"
        "但不得为了凑时长重复内容或越过候选范围；同一素材的时间范围不得重叠。"
    )
    if is_interview:
        duration_instruction = (
            "要求：clips 按最终成片顺序排列；采访剪辑总时长必须在 60 秒到 120 秒之间，"
            "请根据素材内容的丰富度和叙事完整性灵活决定具体时长，不必凑满 120 秒；"
            "不得为了凑时长重复内容或越过候选范围；同一素材的时间范围不得重叠。"
        )
    return (
        "请仅根据以下 Source Intelligence 文本目录制定剪辑方案。\n"
        "输出结构：\n"
        + json.dumps(output_schema, ensure_ascii=False, sort_keys=True)
        + "\n"
        + duration_instruction
        + "候选含 asr 时，每行格式为 [句首秒数,句尾秒数,句子文本]；建议优先参考"
        "这些句首/句尾时间点，降低从半句话开始或在半句话中结束的风险，但请结合叙事"
        "完整性自行判断，不把句界视为强制条件。"
        "重要：clip 的 start 和 end 必须使用 asr 行中的精确秒数（带小数），"
        "禁止使用 0、5、10、15 等整数或 5 的倍数作为时间点。\n"
        "editorialStructure 是剪辑前的叙事节拍指导；有 Shot 时按其顺序覆盖各节拍，"
        "没有 Shot 时从 sectionScript 和 unitContinuity 提取节拍。每个 clip 的 "
        "editorialBeat 必须简明写出它承担的具体节拍，不能把完整任务原文复制到每个 clip。"
        "editorialRole 使用 opening/development/highlight/transition/closing。"
        "宠物内容的每个 clip 必须输出 kind=pet_os 的 overlayCopy。text 是宠物此刻会在心里说的"
        "第一人称口语独白，可以省略‘我’，优先6至12个汉字且最多15个汉字；禁止写成镜头标题、"
        "动作标签、旁白摘要，禁止直接复制候选 description、editorialBeat 或 reason。只根据可验证"
        "画面事实决定语境，可以表达好奇、得意、紧张、嫌弃、嘴硬等主观反应，相邻 clip 不得套用"
        "同一句式。反例与正例：‘碎石路上飞奔’→‘这条路归我巡逻’，‘观察挖掘机’→‘这大铁猫会动吗’，"
        "‘低头饮水’→‘冒险家也得补水’。vibe 只能是 action/surprise/curious/chill，并与冲刺对峙/"
        "意外受惊/观察探索/放松满足分别对应。appearAt 和 duration 是相对 clip 入点的秒数，必须位于"
        "clip 内；通常在关键动作可读后0.2至1.0秒出现，停留1.5至3.0秒，短片段按剩余时长缩短，"
        "不要机械覆盖整个 clip。采访内容的每个 clip 必须输出"
        " kind=interview_summary 的 overlayCopy，text 是不超过30字的当前片段总结；其他内容"
        "不得输出 overlayCopy。overlayCopy 文案必须在本次语义规划中完成，不得留空或交给执行器补写。\n"
        "输入 JSON：\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _semantic_agent_plan_from_payload(
    payload: Any,
    *,
    project: dict[str, Any],
    unit: dict[str, Any],
    analyses: list[dict[str, Any]],
    candidates_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("AI Editing Director 输出必须是 JSON object")
    raw_clips = payload.get("clips")
    if not isinstance(raw_clips, list) or not raw_clips:
        raise ValueError("AI Editing Director 必须选择至少一个候选片段")

    target = float(_duration_target(unit))
    is_interview = project.get("contentType") == "interview"
    if is_interview:
        target = _INTERVIEW_MAX_DURATION
    timeline: list[dict[str, Any]] = []
    storyboard: list[dict[str, Any]] = []
    selected_ranges: list[tuple[str, float, float]] = []
    asr_boundary_advisories: list[str] = []
    output_cursor = 0.0
    expected_overlay_kind = _expected_overlay_kind(project)
    for index, raw in enumerate(raw_clips, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"clip #{index} 必须是 object")
        candidate_id = str(raw.get("candidateId") or "")
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(f"clip #{index} 引用了不存在的 candidateId")
        start = _safe_float(raw.get("start"), float(candidate["start"]))
        end = _safe_float(raw.get("end"), float(candidate["end"]))
        if (
            start < float(candidate["start"]) - 0.001
            or end > float(candidate["end"]) + 0.001
            or end - start < 0.5
        ):
            raise ValueError(f"clip #{index} 超出 Source Intelligence 候选范围")
        if is_interview:
            transcript_segments = candidate.get("transcriptSegments") or []
            start = _snap_to_asr_boundary(
                start,
                transcript_segments,
                tolerance=2.0,
                prefer_end=False,
            )
            end = _snap_to_asr_boundary(
                end,
                transcript_segments,
                tolerance=2.0,
                prefer_end=True,
            )
        asset_id = str(candidate["assetId"])
        clip_id = f"clip-{index:02d}"
        asr_boundary_review = _review_clip_asr_boundaries(
            start,
            end,
            candidate,
            clip_id=clip_id,
        )
        asr_boundary_advisories.extend(asr_boundary_review["advisories"])
        duration = round(end - start, 3)
        if any(
            asset_id == selected_asset
            and start < selected_end - 0.05
            and end > selected_start + 0.05
            for selected_asset, selected_start, selected_end in selected_ranges
        ):
            raise ValueError(f"clip #{index} 与同素材已选片段重叠")
        if is_interview:
            allowed_duration = _INTERVIEW_MAX_DURATION
        else:
            allowed_duration = target + duration_tolerance(target)
        if output_cursor + duration > allowed_duration + 0.001:
            raise ValueError(
                "AI Editing Director 选择的总时长超过目标时长容差"
                f"（目标 {target:g}s，最多 {allowed_duration:g}s）",
            )
        selected_ranges.append((asset_id, start, end))
        reason = str(raw.get("reason") or candidate["description"]).strip()
        editorial_beat = str(raw.get("editorialBeat") or "").strip()
        editorial_role = str(raw.get("editorialRole") or "development").strip()
        clip = {
            "clip_id": clip_id,
            "asset_id": asset_id,
            "asset_version_id": candidate["assetVersionId"],
            "asset_name": candidate["assetName"],
            "source_url": candidate["asset"].get("url"),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": duration,
            "order": index,
            "timeline_start": round(output_cursor, 3),
            "timeline_end": round(output_cursor + duration, 3),
            "transition": str(raw.get("transition") or "cut"),
            "reason": reason,
            "editorial_beat": editorial_beat,
            "editorial_role": editorial_role,
            "analysis_ref": candidate["analysisRef"],
            "semantic_entry_id": candidate["semanticEntryId"],
            "asr_boundary_review": asr_boundary_review,
        }
        raw_overlay = raw.get("overlayCopy")
        if expected_overlay_kind is None:
            if raw_overlay is not None:
                raise ValueError(f"clip #{index} 的内容类型不允许 overlayCopy")
        else:
            if not isinstance(raw_overlay, dict):
                raise ValueError(
                    f"clip #{index} 必须由 AI Editing Director 生成 overlayCopy",
                )
            overlay_kind = str(raw_overlay.get("kind") or "").strip()
            if overlay_kind != expected_overlay_kind:
                raise ValueError(
                    f"clip #{index} overlayCopy.kind 必须是 {expected_overlay_kind}",
                )
            overlay_text = str(raw_overlay.get("text") or "").strip()
            maximum_length = 15 if overlay_kind == "pet_os" else 30
            if not overlay_text or len(overlay_text) > maximum_length:
                raise ValueError(
                    f"clip #{index} overlayCopy.text 必须为 1-{maximum_length} 字",
                )
            appear_at = _safe_float(raw_overlay.get("appearAt"), 0.0)
            overlay_duration = _safe_float(
                raw_overlay.get("duration"),
                duration - appear_at,
            )
            if (
                appear_at < 0
                or overlay_duration <= 0
                or appear_at + overlay_duration > duration + 0.001
            ):
                raise ValueError(f"clip #{index} overlayCopy 时间范围超出片段")
            overlay_copy: dict[str, Any] = {
                "kind": overlay_kind,
                "text": overlay_text,
                "appear_at": round(appear_at, 3),
                "duration": round(overlay_duration, 3),
            }
            if overlay_kind == "pet_os":
                vibe = str(raw_overlay.get("vibe") or "").strip()
                if vibe not in PET_OS_VIBES:
                    raise ValueError(
                        f"clip #{index} overlayCopy.vibe 必须是合法宠物情绪",
                    )
                overlay_copy["vibe"] = vibe
            clip["overlay_copy"] = overlay_copy
            clip["overlay"] = dict(overlay_copy)
        timeline.append(clip)
        storyboard.append(
            {
                "panel_id": f"panel-{index:02d}",
                "clip_id": clip_id,
                "order": index,
                "title": editorial_beat or editorial_role,
                "description": reason,
                "source_asset_id": asset_id,
                "timestamp": round(start + duration / 2, 3),
                "timeline_start": round(output_cursor, 3),
                "timeline_end": round(output_cursor + duration, 3),
            },
        )
        output_cursor += duration

    analysis_refs = sorted(
        {
            str(item.get("analysisRef") or "")
            for item in analyses
            if item.get("analysisRef")
        },
    )
    raw_audio = payload.get("audio_plan")
    audio_plan = dict(raw_audio) if isinstance(raw_audio, dict) else {}
    return {
        "summary": str(payload.get("summary") or "AI Editing Director 语义选片方案"),
        "target_duration": round(output_cursor, 3),
        "requested_target_duration": target,
        "timeline": timeline,
        "storyboard": storyboard,
        "asr_boundary_advisories": asr_boundary_advisories,
        "audio_plan": audio_plan,
        "model": {
            "provider": "text_semantic_agent",
            "model": model_config.get_text_model_name(),
            "analysis_refs": analysis_refs,
            "native_video_requested": False,
            "planning_mode": "semantic_agent",
        },
    }


async def _semantic_agent_plan(
    project: dict[str, Any],
    section: dict[str, Any],
    unit: dict[str, Any],
    assets: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    goal: str,
) -> dict[str, Any]:
    catalog, candidates_by_id = _semantic_agent_catalog(analyses, assets)
    if not catalog:
        raise ValueError("Source Intelligence 没有有效文本候选")
    prompt = _semantic_agent_prompt(
        project,
        section,
        unit,
        analyses,
        catalog,
        goal,
    )
    last_error: Exception | None = None
    advisory_feedback: list[str] = []
    advisory_plan: dict[str, Any] | None = None
    for attempt in range(2):
        request_prompt = prompt
        if last_error is not None:
            request_prompt += (
                "\n上一次输出未通过格式与候选范围校验："
                f"{last_error}。请重新输出完整 JSON，不得修改或越过候选目录。"
            )
        elif advisory_feedback:
            request_prompt += (
                "\n以下是基于 ASR 时间码的非阻断剪辑风险建议。它们不是硬性校验，"
                "请结合叙事效果决定是否调整；即使保留原时间码也允许输出：\n- "
                + "\n- ".join(advisory_feedback)
            )
        response = await text_model.chat_completion(
            request_prompt,
            system_prompt=_AI_EDIT_AGENT_SYSTEM_PROMPT,
            temperature=0.25 if attempt == 0 else 0.0,
            max_tokens=6000,
        )
        try:
            plan = _semantic_agent_plan_from_payload(
                extract_json_payload(response),
                project=project,
                unit=unit,
                analyses=analyses,
                candidates_by_id=candidates_by_id,
            )
            if project.get("contentType") == "interview":
                if float(plan["target_duration"]) < _INTERVIEW_MIN_DURATION:
                    raise ValueError(
                        f"采访剪辑总时长不足 {_INTERVIEW_MIN_DURATION:g}s："
                        f"{plan['target_duration']:g}s",
                    )
            else:
                target = float(_duration_target(unit))
                if (
                    target >= 45
                    and float(plan["target_duration"]) < target * 0.9
                ):
                    raise ValueError(
                        "语义选片总时长不足目标的 90%："
                        f"{plan['target_duration']:g}s < {target * 0.9:g}s",
                    )
        except (ValueError, json.JSONDecodeError) as exc:
            if advisory_plan is not None:
                return advisory_plan
            last_error = exc
            advisory_feedback = []
            continue
        advisories = list(plan.get("asr_boundary_advisories") or [])
        if advisories and attempt == 0:
            advisory_plan = plan
            advisory_feedback = advisories
            last_error = None
            continue
        return plan
    if advisory_plan is not None:
        return advisory_plan
    assert last_error is not None
    raise last_error


def _resolve_ffprobe() -> str:
    """Locate the ffprobe executable.

    The Creator runtime manager owns configured/system/sibling resolution.  An
    empty result is valid because duration and size probing can use ffmpeg.
    """
    ffmpeg_path = ffmpeg_readiness().get("path")
    return resolve_ffprobe(ffmpeg_path=ffmpeg_path) or ""


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _probe_duration_ffprobe(target: str) -> float | None:
    """用 ffprobe 探时长；二进制不存在或失败返回 None（由调用方 fallback）。"""
    ffprobe = _resolve_ffprobe()
    if not ffprobe or not Path(ffprobe).exists():
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                target,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return (
            float(
                json.loads(result.stdout).get("format", {}).get("duration")
                or 0,
            )
            or None
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _probe_duration_ffmpeg(target: str) -> float | None:
    """用 ffmpeg -i 解析 stderr 的 Duration: 行探时长。

    imageio-ffmpeg 打包的 ffmpeg 二进制不含 ffprobe，这是唯一可用的探测手段。
    ffmpeg -i 不带输出参数会返回非 0，但 stderr 仍含格式信息，属正常。
    """
    ffmpeg = ffmpeg_readiness().get("path") or "ffmpeg"
    try:
        result = subprocess.run(
            [ffmpeg, "-i", target],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        return None
    h, m, s = match.groups()
    duration = int(h) * 3600 + int(m) * 60 + float(s)
    return duration or None


_DURATION_CACHE: dict[str, float] = {}


def _media_duration_seconds(url: str, project_id: str | None = None) -> float:
    """Probe media duration without turning planning into an implicit ingest.

    ``project_id`` remains in the frozen call signature, but is deliberately not
    used to download a remote source.  For HTTP(S), ffprobe/ffmpeg may perform a
    bounded metadata/range request against the exact public URL; failure returns
    ``0.0`` and lets the model-facing planner use its established unknown-duration
    fallback.  Full bytes are acquired only by explicit ingest or edit execution.
    """
    del project_id
    if not url:
        return 0.0
    if url.startswith(("http://", "https://")):
        probe_target = url
    elif url.startswith(("/generated/", "file://")):
        try:
            probe_target = str(_local_media_path(url))
        except ValueError:
            return 0.0
    else:
        return 0.0

    cached = _DURATION_CACHE.get(probe_target)
    if cached is not None:
        return cached
    for probe in (_probe_duration_ffprobe, _probe_duration_ffmpeg):
        duration = probe(probe_target)
        if duration:
            _DURATION_CACHE[probe_target] = duration
            return duration
    return 0.0


def _asset_duration_seconds(
    asset: dict[str, Any],
    project_id: str | None = None,
    *,
    probe: Callable[[str, str | None], float] | None = None,
) -> float:
    """Return projected ingest metadata before attempting a bounded media probe.

    Runtime projections expose completed ingest-cache duration as ``duration``;
    older/direct callers may use ``durationSeconds`` or ``duration_seconds``.
    Nested metadata/cache spellings are accepted only as read-compatible aliases.
    No branch in this helper downloads a remote object.
    """

    metadata = (
        asset.get("metadata")
        if isinstance(asset.get("metadata"), dict)
        else {}
    )
    cache = asset.get("cache") if isinstance(asset.get("cache"), dict) else {}
    candidates = (
        asset.get("duration"),
        asset.get("durationSeconds"),
        asset.get("duration_seconds"),
        metadata.get("durationSeconds"),
        metadata.get("duration_seconds"),
        cache.get("durationSeconds"),
        cache.get("duration_seconds"),
    )
    for raw in candidates:
        try:
            duration = float(raw)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    duration_probe = probe or _media_duration_seconds
    url = str(asset.get("url") or "")
    try:
        return duration_probe(url, project_id)
    except TypeError:
        # Characterization tests and legacy extension seams may provide the
        # original one-argument probe callable.
        return duration_probe(url)  # type: ignore[call-arg]


def _editorial_beat_texts(
    unit: dict[str, Any],
    section: dict[str, Any] | None = None,
) -> list[str]:
    """Return concise pre-plan story beats without treating them as clip truth."""

    candidates = [
        str(shot.get("description") or "").strip()
        for shot in unit.get("shots", []) or []
        if isinstance(shot, dict)
    ]
    if not any(candidates):
        source_texts = [
            str((section or {}).get("script") or ""),
            str(unit.get("continuity") or ""),
        ]
        candidates = []
        for source_text in source_texts:
            for raw_line in source_text.splitlines():
                line = re.sub(
                    r"^\s*(?:[-*+]\s+|#{1,6}\s+|\d+[.)、]\s*)",
                    "",
                    raw_line,
                ).strip()
                if not line or len(line) > 160:
                    continue
                candidates.append(line)

    beats: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = re.sub(r"\s+", " ", candidate).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        beats.append(normalized)
        if len(beats) >= 10:
            break
    return beats


def _heuristic_plan(
    project: dict,
    unit: dict,
    assets: list[dict],
    goal: str,
    reason: str = "",
    section: dict[str, Any] | None = None,
    asr_segments_by_asset: dict[str, list[dict[str, Any]]] | None = None,
) -> dict:
    target = _duration_target(unit)
    if not assets:
        # 没有可剪辑素材时不能进入下面的取模/分段逻辑（index % len(assets) 会
        # 抛 integer modulo by zero）。返回空 timeline 的合法 plan，让上游
        # 据此跳过剪辑或提示用户补充素材。
        return {
            "summary": (
                "没有可剪辑视频素材，无法生成剪辑方案。" + (f" 降级原因：{reason}" if reason else "")
            ),
            "target_duration": 0,
            "timeline": [],
            "storyboard": [],
            "audio_plan": {
                "bgm": "保留后续人工选择或素材音频",
                "voiceover": "未配置",
                "subtitle": "可在成片增强阶段生成",
            },
            "model": {
                "provider": "heuristic",
                "model": "metadata-edit-planner",
                "fallback_reason": reason or "没有可剪辑视频素材",
            },
        }
    editorial_beats = _editorial_beat_texts(unit, section)
    clip_count = (
        len(editorial_beats)
        if editorial_beats
        else max(
            1,
            min(
                10,
                len(assets) if target < 30 else max(len(assets), target // 8),
            ),
        )
    )
    default_clip_duration = max(
        4,
        min(12, target / clip_count if clip_count else target),
    )
    timeline = []
    storyboard = []
    cursor = 0
    for index in range(clip_count):
        asset = assets[index % len(assets)]
        source_duration = _asset_duration_seconds(asset, project.get("id"))
        if not source_duration:
            # 拿不到视频时长时不做随机偏移，统一从 0 起，避免在未知长度素材上截到无效区间。
            logger.warning(
                "heuristic plan source_duration=0 url=%s —— 所有片段将从 0 起切，"
                "可能只用到素材开头。请检查 ffprobe/ffmpeg 是否可用或素材 URL 是否可访问。",
                str(asset.get("url") or "")[:80],
            )
            start = 0.0
            end = start + default_clip_duration
        else:
            usable_end = max(
                default_clip_duration + 1,
                source_duration - default_clip_duration - 1,
            )
            start = (
                0
                if clip_count == 1
                else min(
                    usable_end,
                    (usable_end / max(1, clip_count - 1)) * index,
                )
            )
            end = min(source_duration, start + default_clip_duration)
        # Snap to FunASR sentence boundaries when available
        version_id = str(asset.get("versionId") or "")
        speech = (asr_segments_by_asset or {}).get(version_id) or []
        if speech and source_duration:
            start_is_round = abs(start - round(start)) < 0.05
            end_is_round = abs(end - round(end)) < 0.05
            snapped_end = find_nearest_sentence_boundary(
                end,
                speech,
                tolerance=3.0 if end_is_round else 1.5,
                prefer_end=True,
            )
            snapped_start = find_nearest_sentence_boundary(
                start,
                speech,
                tolerance=3.0 if start_is_round else 1.0,
                prefer_end=False,
            )
            if snapped_start is None:
                for seg in speech:
                    seg_start = float(seg["start"])
                    if seg_start <= start:
                        if snapped_start is None or seg_start > snapped_start:
                            snapped_start = seg_start
                if snapped_start is None:
                    for seg in speech:
                        seg_start = float(seg["start"])
                        if seg_start > start:
                            if (
                                snapped_start is None
                                or seg_start < snapped_start
                            ):
                                snapped_start = seg_start
            if snapped_end is None:
                for seg in speech:
                    seg_end = float(seg["end"])
                    if seg_end >= end:
                        if snapped_end is None or seg_end < snapped_end:
                            snapped_end = seg_end
                if snapped_end is None:
                    for seg in speech:
                        seg_end = float(seg["end"])
                        if seg_end < end:
                            if snapped_end is None or seg_end > snapped_end:
                                snapped_end = seg_end
            if snapped_end is not None and snapped_end > start + 0.5:
                end = min(source_duration, snapped_end)
            if snapped_start is not None and snapped_start < end - 0.5:
                start = max(0.0, snapped_start)
        clip_id = f"clip-{index + 1:02d}"
        editorial_beat = (
            editorial_beats[index] if index < len(editorial_beats) else ""
        )
        selection_reason = (
            editorial_beat
            or f"素材候选 {index + 1}，原片约 {start + (end - start) / 2:.1f} 秒处。"
        )
        clip = {
            "clip_id": clip_id,
            "asset_id": asset.get("id"),
            "asset_name": asset.get("name"),
            "source_url": asset.get("url"),
            "start": start,
            "end": end,
            "duration": end - start,
            "order": index + 1,
            "transition": "cut" if index == 0 else "match_cut",
            "reason": selection_reason,
            "editorial_beat": editorial_beat,
        }
        if asset.get("versionId"):
            clip["asset_version_id"] = str(asset["versionId"])
        timeline.append(clip)
        storyboard.append(
            {
                "panel_id": f"panel-{index + 1:02d}",
                "order": index + 1,
                "title": editorial_beat or f"候选片段 {index + 1}",
                "description": selection_reason,
                "source_asset_id": asset.get("id"),
                "timestamp": round(start + max(0.5, (end - start) / 2), 3),
                "timeline_start": cursor,
                "timeline_end": cursor + end - start,
            },
        )
        cursor += end - start
    return {
        "summary": (
            f"已为 AI 剪辑单元选择 {len(timeline)} 段素材，目标成片约 {cursor}s。"
            + (f" 降级原因：{reason}" if reason else "")
        ),
        "target_duration": cursor,
        "timeline": timeline,
        "storyboard": storyboard,
        "audio_plan": {
            "bgm": "保留后续人工选择或素材音频",
            "voiceover": "未配置",
            "subtitle": "可在成片增强阶段生成",
        },
        "model": {
            "provider": "heuristic",
            "model": "metadata-edit-planner",
            "fallback_reason": reason,
        },
    }


def _prompt(
    project: dict,
    unit: dict,
    assets: list[dict],
    goal: str,
    asr_segments_by_asset: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    target_duration = _duration_target(unit)
    inventory = []
    for asset in assets:
        version_id = str(asset.get("versionId") or "")
        speech_segments = (
            (asr_segments_by_asset or {}).get(version_id) or []
        )[:30]
        inventory.append(
            {
                "asset_id": asset.get("id"),
                "name": asset.get("name"),
                "url": asset.get("url"),
                "duration_seconds": round(
                    _asset_duration_seconds(asset, project.get("id")),
                    2,
                ),
                "description": asset.get("description"),
                "semantic_category": asset.get("semanticCategory"),
                "usable_for": asset.get("usableFor"),
                "speech_segments": speech_segments,
            },
        )
    audio_constraint = (
        "音频对齐约束：每个 clip 的 start/end 必须落在该素材某条 speech_segment 的 start 或 end ±0.5s 内，"
        "避免半句切入或戛然而止；若该素材 speech_segments 为空（无语音或未分析），则不受此约束。"
        if any(item.get("speech_segments") for item in inventory)
        else ""
    )
    return (
        "你是专业 AI 剪辑规划器。请理解视频素材，决定应该使用哪些素材、在素材基础上取哪些片段，"
        "输出可执行剪辑决策列表和由关键帧组成的分镜说明。不要使用 R2V 的引用图/生成资产字段。\n"
        "返回严格 JSON，不要输出 Markdown。JSON Schema:\n"
        "{\n"
        '  "summary":"剪辑方案摘要",\n'
        f'  "target_duration":{target_duration},\n'
        f'  "timeline":[{{"clip_id":"clip-01","asset_id":"...","asset_name":"...",'
        f'"source_url":"...","start":0.3,"end":4.7,"duration":4.4,"order":1,'
        '"transition":"cut|fade|match_cut","reason":"为什么选这段"}}],\n'
        '  "storyboard":[{"panel_id":"panel-01","order":1,"title":"...",'
        '"description":"关键帧画面描述","source_asset_id":"...","timestamp":2.1,'
        '"timeline_start":0.0,"timeline_end":4.4}],\n'
        '  "audio_plan":{"bgm":"...","voiceover":"...","subtitle":"..."}\n'
        "}\n\n"
        "约束：所有文本字段控制在 80 个汉字以内；timestamp 必须落在对应 clip 的 start/end 之间；"
        "关键帧图片由系统按 timestamp 从原视频抽取，你只需要给出真实视频时间点和画面说明。\n"
        "重要：start、end、timestamp 必须使用带小数的精确秒数（如 3.2、7.8、12.4），"
        "禁止使用 0、5、10、15 等整数或 5 的倍数；有 speech_segments 时必须参考其 "
        "start/end 值来确定剪辑点。\n"
        f"{audio_constraint}\n"
        f"项目：{project.get('name', '')}\n"
        f"剪辑目标：{goal or unit.get('storyText') or project.get('description', '')}\n"
        f"目标时长：{target_duration} 秒。若素材超过10分钟，请从全程挑选高光，优先输出 8-12 个 4-8 秒片段，最终总时长接近目标时长。\n"
        f"视频素材清单：{json.dumps(inventory, ensure_ascii=False)}"
    )


def _retry_prompt(
    project: dict,
    unit: dict,
    assets: list[dict],
    goal: str,
    parse_error: str,
    asr_segments_by_asset: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    return (
        f"上一次剪辑规划返回无法解析为 JSON：{parse_error}。\n"
        "请重新理解视频并只返回一个完整 JSON 对象，不要 Markdown，不要解释，不要省略结尾。\n"
        "字段必须只有 summary、target_duration、timeline、storyboard、audio_plan。"
        "timeline 输出 8-12 个片段，每个 4-8 秒；storyboard 与 timeline 一一对应。"
        "所有 description/reason 控制在 60 个汉字以内。"
        "timestamp 必须是原视频中的真实秒数，且位于对应片段 start/end 之间。\n\n"
        + _prompt(project, unit, assets, goal, asr_segments_by_asset)
    )


def _ensure_target_duration(
    plan: dict,
    project: dict,
    unit: dict,
    assets: list[dict],
    goal: str,
) -> dict:
    target = _duration_target(unit)
    if target < 45:
        return plan
    timeline = list(plan.get("timeline") or [])
    current = sum(_safe_float(item.get("duration"), 0.0) for item in timeline)
    # Keep plan admission aligned with the final video completion tolerance:
    # a 60-second Unit must reach at least 54 seconds (10% tolerance).  The
    # former 80% threshold admitted 48-53 second plans that could execute and
    # compose successfully but could never pass deterministic completion.
    if current >= target * 0.9:
        return plan

    filler = _heuristic_plan(
        project,
        unit,
        assets,
        goal,
        "VLM timeline shorter than target; supplemented by duration balancer",
    )
    used = {
        (
            item.get("asset_id"),
            round(_safe_float(item.get("start"), 0.0), 1),
            round(_safe_float(item.get("end"), 0.0), 1),
        )
        for item in timeline
    }
    next_order = len(timeline) + 1
    cursor = current
    storyboard = list(plan.get("storyboard") or [])
    for clip in filler.get("timeline", []):
        if current >= target * 0.92:
            break
        key = (
            clip.get("asset_id"),
            round(_safe_float(clip.get("start"), 0.0), 1),
            round(_safe_float(clip.get("end"), 0.0), 1),
        )
        if key in used:
            continue
        duration = _safe_float(clip.get("duration"), 0.0)
        if duration <= 0:
            continue
        enriched = {
            **clip,
            "clip_id": f"clip-{next_order:02d}",
            "order": next_order,
        }
        timeline.append(enriched)
        storyboard.append(
            {
                "panel_id": f"panel-{next_order:02d}",
                "clip_id": f"clip-{next_order:02d}",
                "order": next_order,
                "title": clip.get("asset_name") or f"高光片段 {next_order}",
                "description": f"补足 1 分钟高光成片的候选动作片段：{clip.get('reason') or '从长素材中抽取节奏点。'}",
                "source_asset_id": clip.get("asset_id"),
                "timestamp": round(
                    _safe_float(clip.get("start"), 0.0) + duration / 2,
                    3,
                ),
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
            },
        )
        current += duration
        cursor += duration
        next_order += 1
        used.add(key)

    plan["timeline"] = timeline
    plan["storyboard"] = storyboard
    plan["target_duration"] = round(
        sum(_safe_float(item.get("duration"), 0.0) for item in timeline),
        3,
    )
    plan[
        "summary"
    ] = f"{plan.get('summary', '')} 已按 1 分钟目标补足剪辑段，总时长约 {plan['target_duration']} 秒。".strip()
    return plan


def _snap_and_cap_for_interview(
    plan: dict,
    project: dict,
    unit: dict,
    asr_segments_by_asset: dict[str, list[dict[str, Any]]] | None = None,
) -> dict:
    """Align interview clips to speech boundaries and enforce the Unit duration.

    Uses FunASR sentence segments from Source Intelligence (via
    *asr_segments_by_asset*) rather than running local Whisper analysis.
    """

    timeline = list(plan.get("timeline") or [])
    if not timeline:
        return plan
    project_id = str(project.get("id") or "project")
    original_clip_ids = {
        id(clip): str(clip.get("clip_id") or f"clip-{index + 1:02d}")
        for index, clip in enumerate(timeline)
    }

    for clip in timeline:
        version_id = str(clip.get("asset_version_id") or "")
        segments = (asr_segments_by_asset or {}).get(version_id) or []
        if not segments:
            continue
        start = _safe_float(clip.get("start"), 0.0)
        end = _safe_float(clip.get("end"), start + 1.0)
        start_is_round = abs(start - round(start)) < 0.05
        end_is_round = abs(end - round(end)) < 0.05
        start_tolerance = 3.0 if start_is_round else 1.0
        end_tolerance = 3.0 if end_is_round else 2.5
        snapped_start = find_nearest_sentence_boundary(
            start,
            segments,
            tolerance=start_tolerance,
            prefer_end=False,
        )
        snapped_end = find_nearest_sentence_boundary(
            end,
            segments,
            tolerance=end_tolerance,
            prefer_end=True,
        )
        if snapped_start is None:
            for seg in segments:
                seg_start = float(seg["start"])
                if seg_start <= start:
                    if snapped_start is None or seg_start > snapped_start:
                        snapped_start = seg_start
            if snapped_start is None:
                for seg in segments:
                    seg_start = float(seg["start"])
                    if seg_start > start:
                        if snapped_start is None or seg_start < snapped_start:
                            snapped_start = seg_start
        if snapped_end is None:
            for seg in segments:
                seg_end = float(seg["end"])
                if seg_end >= end:
                    if snapped_end is None or seg_end < snapped_end:
                        snapped_end = seg_end
            if snapped_end is None:
                for seg in segments:
                    seg_end = float(seg["end"])
                    if seg_end < end:
                        if snapped_end is None or seg_end > snapped_end:
                            snapped_end = seg_end
        if snapped_start is not None and snapped_start < end - 0.5:
            start = max(0.0, snapped_start)
        if snapped_end is not None and snapped_end > start + 0.5:
            end = snapped_end
        asset_duration = _media_duration_seconds(
            str(clip.get("source_url") or ""),
            project_id,
        )
        if asset_duration > 0:
            start = min(start, asset_duration)
            end = min(end, asset_duration)
        if end <= start + 0.5:
            continue
        clip["start"] = round(start, 3)
        clip["end"] = round(end, 3)
        clip["duration"] = round(end - start, 3)
        overlap_texts = [
            str(segment["text"])
            for segment in segments
            if segment.get("text")
            and _safe_float(segment.get("end"), 0.0) > start
            and _safe_float(segment.get("start"), 0.0) < end
        ]
        if overlap_texts:
            clip["transcript"] = " ".join(overlap_texts)

    target = _INTERVIEW_MAX_DURATION
    timeline.sort(key=lambda clip: clip.get("order", 0))
    kept: list[dict[str, Any]] = []
    accumulated = 0.0
    for clip in timeline:
        duration = _safe_float(clip.get("duration"), 0.0)
        if duration <= 0:
            continue
        if accumulated + duration > target and kept:
            break
        if duration > target:
            # Semantic plans are already rejected above 120 seconds.  Keep a
            # hard fail-safe for heuristic or legacy payloads containing one
            # oversized first clip so this normalization step cannot publish
            # an interview outside the documented upper bound.
            start = _safe_float(clip.get("start"), 0.0)
            clip["end"] = round(start + target, 3)
            clip["duration"] = target
            duration = target
        kept.append(clip)
        accumulated += duration
        if accumulated >= target:
            break
    if len(kept) < len(timeline):
        logger.info(
            "interview cap: %d->%d clips, %.1fs->%.1fs (max=%.1fs)",
            len(timeline),
            len(kept),
            sum(_safe_float(clip.get("duration"), 0.0) for clip in timeline),
            accumulated,
            target,
        )
    timeline = kept
    total_duration = sum(
        _safe_float(clip.get("duration"), 0.0) for clip in timeline
    )
    if total_duration < _INTERVIEW_MIN_DURATION and timeline:
        deficit = _INTERVIEW_MIN_DURATION - total_duration
        project_id = str(project.get("id") or "project")
        for clip in reversed(timeline):
            if deficit <= 0.05:
                break
            start = _safe_float(clip.get("start"), 0.0)
            end = _safe_float(clip.get("end"), start + 1.0)
            version_id = str(clip.get("asset_version_id") or "")
            segments = (asr_segments_by_asset or {}).get(version_id) or []
            asset_dur = _media_duration_seconds(
                str(clip.get("source_url") or ""),
                project_id,
            )
            raw_max = end + deficit
            max_end = min(asset_dur, raw_max) if asset_dur > 0 else raw_max
            if max_end <= end + 0.1:
                continue
            if segments:
                extended = False
                for seg in segments:
                    seg_end = float(seg["end"])
                    if seg_end >= max_end - 0.5 and seg_end <= max_end + 3.0:
                        if seg_end > start + 0.5:
                            clip["end"] = round(seg_end, 3)
                            clip["duration"] = round(seg_end - start, 3)
                            deficit -= seg_end - end
                            extended = True
                            break
                if not extended:
                    clip["end"] = round(max_end, 3)
                    clip["duration"] = round(max_end - start, 3)
                    deficit -= max_end - end
            else:
                clip["end"] = round(max_end, 3)
                clip["duration"] = round(max_end - start, 3)
                deficit -= max_end - end
        total_duration = sum(
            _safe_float(clip.get("duration"), 0.0) for clip in timeline
        )
        if total_duration < _INTERVIEW_MIN_DURATION:
            logger.warning(
                "interview total duration %.1fs is below minimum %.1fs "
                "after extending clips to source limits",
                total_duration,
                _INTERVIEW_MIN_DURATION,
            )

    timeline.sort(key=lambda clip: _safe_float(clip.get("start"), 0.0))
    clips_by_original_id: dict[str, dict[str, Any]] = {}
    for index, clip in enumerate(timeline):
        original_id = original_clip_ids.get(
            id(clip),
            str(clip.get("clip_id") or ""),
        )
        clip["order"] = index + 1
        clip["clip_id"] = f"clip-{index + 1:02d}"
        clips_by_original_id[original_id] = clip

    def clip_for_timestamp(timestamp: float) -> dict[str, Any] | None:
        return next(
            (
                clip
                for clip in timeline
                if _safe_float(clip.get("start"), 0.0)
                <= timestamp
                <= _safe_float(clip.get("end"), timestamp)
            ),
            None,
        )

    cursor = 0.0
    clip_windows: dict[str, tuple[float, float]] = {}
    for clip in timeline:
        duration = _safe_float(clip.get("duration"), 0.0)
        clip_windows[str(clip["clip_id"])] = (
            round(cursor, 3),
            round(cursor + duration, 3),
        )
        cursor += duration

    clip_asr_map: dict[str, list[dict[str, Any]]] = {}
    for clip in timeline:
        version_id = str(clip.get("asset_version_id") or "")
        clip_asr_map[str(clip["clip_id"])] = (asr_segments_by_asset or {}).get(
            version_id,
        ) or []

    storyboard: list[dict[str, Any]] = []
    for index, panel in enumerate(plan.get("storyboard") or []):
        if not isinstance(panel, dict):
            continue
        timestamp = _safe_float(panel.get("timestamp"), 0.0)
        clip = clips_by_original_id.get(str(panel.get("clip_id") or ""))
        if clip is None:
            clip = clip_for_timestamp(timestamp)
        if clip is None and index < len(timeline):
            clip = timeline[index]
        if clip is None:
            continue
        clip_id = str(clip["clip_id"])
        output_start, output_end = clip_windows[clip_id]
        source_start = _safe_float(clip.get("start"), 0.0)
        source_end = _safe_float(clip.get("end"), source_start)
        asr_segs = clip_asr_map.get(clip_id) or []
        if asr_segs:
            snapped_ts = find_nearest_sentence_boundary(
                timestamp,
                asr_segs,
                tolerance=2.0,
                prefer_end=False,
            )
            if snapped_ts is not None:
                timestamp = snapped_ts
        storyboard.append(
            {
                **panel,
                "clip_id": clip_id,
                "order": len(storyboard) + 1,
                "source_asset_id": panel.get("source_asset_id")
                or clip.get("asset_id", ""),
                "timestamp": round(
                    max(source_start, min(timestamp, source_end)),
                    3,
                ),
                "timeline_start": output_start,
                "timeline_end": output_end,
            },
        )

    if not storyboard:
        for index, clip in enumerate(timeline):
            clip_id = str(clip["clip_id"])
            output_start, output_end = clip_windows[clip_id]
            storyboard.append(
                {
                    "panel_id": f"panel-{index + 1:02d}",
                    "clip_id": clip_id,
                    "order": index + 1,
                    "title": clip.get("asset_name") or f"片段 {index + 1}",
                    "description": clip.get("reason") or "",
                    "source_asset_id": clip.get("asset_id", ""),
                    "timestamp": round(_safe_float(clip.get("start"), 0.0), 3),
                    "timeline_start": output_start,
                    "timeline_end": output_end,
                },
            )

    plan["timeline"] = timeline
    plan["storyboard"] = storyboard
    plan["target_duration"] = round(
        sum(_safe_float(clip.get("duration"), 0.0) for clip in timeline),
        2,
    )
    plan["summary"] = (
        f"{plan.get('summary', '')} 采访剪辑：已按句界对齐，总时长 "
        f"{plan['target_duration']} 秒。"
    ).strip()
    return plan


def _normalize_plan(
    payload: Any,
    project: dict,
    unit: dict,
    assets: list[dict],
    goal: str,
) -> dict:
    # 惰性构建启发式 fallback：仅在真正需要降级（VLM 输出无效 / timeline 为空 /
    # storyboard、summary、audio_plan 缺字段）时才调用。VLM 成功路径不再触发
    # _heuristic_plan 内的时长探测，避免每次都打 source_duration 那条噪音 warning。
    fallback_cache: list[dict] = []

    def fallback() -> dict:
        if not fallback_cache:
            fallback_cache.append(_heuristic_plan(project, unit, assets, goal))
        return fallback_cache[0]

    if not isinstance(payload, dict):
        return fallback()

    # episode 绑定的源素材与时间区间（由 video_edit_highlight_agent._unit_like 注入）。
    # episode_asset_id 非空时，clip 强制取该素材；episode_start/end>0 时，完全落在
    # 区间外的 clip 丢弃（padding 允许略超区间，见 prompt）。
    ep_asset_id = str(unit.get("episode_asset_id") or "")
    ep_start = _safe_float(unit.get("episode_start"), 0.0)
    ep_end = _safe_float(unit.get("episode_end"), 0.0)
    bound_active = (
        bool(ep_asset_id) and (ep_start or ep_end) and ep_end > ep_start
    )

    assets_by_id = _asset_index(assets)
    timeline = []
    for index, item in enumerate(
        payload.get("timeline", [])
        if isinstance(payload.get("timeline"), list)
        else [],
    ):
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "")
        # episode 绑定单素材时，强制 clip 取该素材（忽略模型给错的 asset_id）
        if ep_asset_id:
            asset_id = ep_asset_id
        asset = assets_by_id.get(asset_id)
        if not asset:
            continue
        start = max(0.0, _safe_float(item.get("start"), 0.0))
        # 区分 end（绝对结束时间）与 duration（片段时长）：模型只给 duration 时
        # 结束时间应为 start + duration，而不是把 duration 当成绝对时间位置。
        if item.get("end") is not None:
            end = max(start + 1.0, _safe_float(item.get("end"), start + 4.7))
        else:
            end = max(
                start + 1.0,
                start + _safe_float(item.get("duration"), 4.7),
            )
        # 硬约束：clip 不得超出素材本身 [0, duration]
        asset_duration = _asset_duration_seconds(asset, project.get("id"))
        if asset_duration > 0:
            start = min(start, asset_duration)
            end = min(end, asset_duration)
            if end <= start:
                continue
        # 软约束：clip 不得完全落在 episode 区间外（padding 允许略超）
        if bound_active and (end <= ep_start or start >= ep_end):
            continue
        clip = {
            "clip_id": str(
                item.get("clip_id") or f"clip-{len(timeline) + 1:02d}",
            ),
            "asset_id": asset_id,
            "asset_name": asset.get("name", ""),
            "source_url": asset.get("url", ""),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "order": int(item.get("order") or len(timeline) + 1),
            "transition": str(item.get("transition") or "cut"),
            "reason": str(item.get("reason") or ""),
        }
        if item.get("overlay_copy"):
            clip["overlay_copy"] = dict(item["overlay_copy"])
        if item.get("overlay"):
            clip["overlay"] = dict(item["overlay"])
        if asset.get("versionId"):
            clip["asset_version_id"] = str(asset["versionId"])
        timeline.append(clip)
    if not timeline:
        return fallback()

    # 按源视频内 start 时间先后排序（替代旧的按 order 排序），并重排 order 与 clip_id
    timeline.sort(key=lambda c: (c["start"], c["end"]))
    for index, clip in enumerate(timeline):
        clip["order"] = index + 1
        if not str(clip.get("clip_id") or "").startswith("clip-"):
            clip["clip_id"] = f"clip-{index + 1:02d}"

    # timeline_start/timeline_end 由 clip 在 timeline 中的累计 duration 推导，
    # 不再采信模型给的值（避免漂移导致 shot/分镜跨 clip）。
    cursor = 0.0
    clip_output_window: dict[str, tuple[float, float]] = {}
    for clip in timeline:
        dur = _safe_float(clip.get("duration"), 0.0)
        clip_output_window[clip["clip_id"]] = (
            round(cursor, 3),
            round(cursor + dur, 3),
        )
        cursor += dur

    # storyboard panel 钉到 clip：优先用模型给的 clip_id；否则按 timestamp 落点反查
    # 所属 clip；查不到则丢弃。panel 的 timeline_start/end 取其所属 clip 的输出窗。
    clips_by_id = {c["clip_id"]: c for c in timeline}

    def _find_clip_for_timestamp(ts: float) -> dict | None:
        for clip in timeline:
            if clip["start"] <= ts <= clip["end"]:
                return clip
        return None

    storyboard = []
    for index, item in enumerate(
        payload.get("storyboard", [])
        if isinstance(payload.get("storyboard"), list)
        else [],
    ):
        if not isinstance(item, dict):
            continue
        asset_id = str(
            item.get("source_asset_id") or item.get("asset_id") or ep_asset_id,
        )
        if asset_id and asset_id not in assets_by_id:
            continue
        ts = _safe_float(item.get("timestamp"), 0.0)
        clip = clips_by_id.get(
            str(item.get("clip_id") or ""),
        ) or _find_clip_for_timestamp(ts)
        if not clip:
            continue
        out_start, out_end = clip_output_window[clip["clip_id"]]
        storyboard.append(
            {
                "panel_id": str(
                    item.get("panel_id") or f"panel-{index + 1:02d}",
                ),
                "clip_id": clip["clip_id"],
                "order": len(storyboard) + 1,
                "title": str(
                    item.get("title")
                    or clip.get("asset_name")
                    or f"关键帧 {index + 1}",
                ),
                "description": str(
                    item.get("description") or clip.get("reason") or "",
                ),
                "source_asset_id": clip["asset_id"],
                "timestamp": round(ts, 3),
                "timeline_start": out_start,
                "timeline_end": out_end,
            },
        )
    fb = fallback()
    if not storyboard:
        # A heuristic storyboard belongs to the heuristic timeline.  Reusing it
        # for a valid VLM timeline produces dangling clip ids, so synthesize one
        # panel per normalized clip instead.
        storyboard = [
            {
                "panel_id": f"panel-{index + 1:02d}",
                "clip_id": clip["clip_id"],
                "order": index + 1,
                "title": clip.get("asset_name") or f"片段 {index + 1}",
                "description": clip.get("reason") or "",
                "source_asset_id": clip["asset_id"],
                "timestamp": round(
                    (
                        _safe_float(clip.get("start"), 0.0)
                        + _safe_float(clip.get("end"), 0.0)
                    )
                    / 2,
                    2,
                ),
                "timeline_start": clip_output_window[clip["clip_id"]][0],
                "timeline_end": clip_output_window[clip["clip_id"]][1],
            }
            for index, clip in enumerate(timeline)
        ]
    plan = {
        "summary": str(payload.get("summary") or fb["summary"]),
        "target_duration": round(
            sum(_safe_float(item.get("duration"), 0.0) for item in timeline),
            3,
        ),
        "timeline": timeline,
        "storyboard": sorted(
            storyboard,
            key=lambda item: item.get("order", 0),
        ),
        "audio_plan": payload.get("audio_plan")
        if isinstance(payload.get("audio_plan"), dict)
        else fb["audio_plan"],
        "model": {
            "provider": "DashScope Bailian",
            "model": model_config.get_vlm_model_name(),
        },
    }
    if project.get("contentType") == "interview":
        return _snap_and_cap_for_interview(plan, project, unit)
    return _ensure_target_duration(plan, project, unit, assets, goal)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timeline_clip_for_panel(panel: dict, timeline: list[dict]) -> dict | None:
    order = int(panel.get("order") or 0)
    source_asset_id = panel.get("source_asset_id")
    if 1 <= order <= len(timeline):
        candidate = timeline[order - 1]
        if not source_asset_id or candidate.get("asset_id") == source_asset_id:
            return candidate

    if source_asset_id:
        for clip in timeline:
            if clip.get("asset_id") == source_asset_id:
                return clip
    return timeline[0] if timeline else None


def _extract_keyframe(
    ffmpeg: str,
    project_id: str,
    unit_id: str,
    panel: dict,
    timeline: list[dict],
    index: int,
) -> str:
    """Extract one real source-video frame for a storyboard panel."""
    clip = _timeline_clip_for_panel(panel, timeline)
    if not clip:
        panel["keyframe_error"] = "timeline 无对应片段"
        return ""
    source_url = str(clip.get("source_url") or "")
    if not source_url.startswith(
        ("/generated/", "file://", "http://", "https://"),
    ):
        panel["keyframe_error"] = f"不支持素材来源: {source_url[:60]}"
        return ""
    if source_url.startswith(("http://", "https://")):
        # Storyboard rendering is still part of planning.  Let ffmpeg perform a
        # single range seek against the provider-usable URL; never turn a frame
        # preview into a second full remote download beside background ingest.
        source_path: str | Path = source_url
    else:
        try:
            source_path = _local_media_path(source_url)
        except ValueError as exc:
            # 受控本地素材文件不存在 / 路径非法 —— 最常见的黑屏原因
            panel["keyframe_error"] = f"素材文件缺失: {exc}"
            return ""

    clip_start = _safe_float(clip.get("start"), 0.0)
    clip_end = _safe_float(
        clip.get("end"),
        clip_start + _safe_float(clip.get("duration"), 1.0),
    )
    timestamp = _safe_float(panel.get("timestamp"), clip_start)
    if timestamp <= 0 and clip_end > clip_start:
        timestamp = clip_start + min(
            (clip_end - clip_start) / 2,
            max(0.5, clip_end - clip_start - 0.1),
        )
    timestamp = max(
        clip_start,
        min(timestamp, max(clip_start, clip_end - 0.1)),
    )

    frame_dir = ensure_preview_subdir(
        "editing",
        project_id,
        f"{unit_id}-keyframes",
    )
    frame_path = (
        frame_dir / f"panel-{index + 1:02d}-{uuid.uuid4().hex[:8]}.jpg"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(source_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=640:-2",
        "-q:v",
        "3",
        str(frame_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not frame_path.exists():
        tail = (
            (result.stderr or "").strip().splitlines()[-1]
            if result.stderr
            else "未知原因"
        )
        panel["keyframe_error"] = f"抽帧失败({tail[:80]})"
        logger.warning(
            "Keyframe extraction failed for %s: %s",
            source_url,
            result.stderr[-300:],
        )
        return ""
    return media_url_for(frame_path)


def _data_uri_for_media_image(url: str) -> str:
    try:
        path = media_path_from_url(url)
    except ValueError:
        return ""
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _text_units(text: str) -> int:
    return sum(1 if ord(char) < 128 else 2 for char in text)


def _trim_to_units(text: str, max_units: int) -> str:
    current = ""
    units = 0
    for char in text:
        char_units = 1 if ord(char) < 128 else 2
        if units + char_units > max_units:
            break
        current += char
        units += char_units
    return current.rstrip()


def _escape_lines(
    text: str,
    max_units: int = 36,
    max_lines: int = 4,
    limit: int = 150,
) -> list[str]:
    clean = " ".join(str(text or "").split())
    hard_truncated = len(clean) > limit
    if len(clean) > limit:
        clean = clean[:limit].rstrip()
    lines: list[str] = []
    current = ""
    consumed_all = True
    for char in clean:
        char_units = 1 if ord(char) < 128 else 2
        if current and _text_units(current) + char_units > max_units:
            lines.append(current.rstrip())
            current = ""
            if len(lines) >= max_lines:
                consumed_all = False
                break
            if char.isspace():
                continue
        current += char
    if consumed_all and current.strip() and len(lines) < max_lines:
        lines.append(current.rstrip())
    if (hard_truncated or not consumed_all) and lines:
        lines[-1] = f"{_trim_to_units(lines[-1], max(1, max_units - 3))}..."
    return lines or [""]


def _write_storyboard_sheet(project_id: str, unit_id: str, plan: dict) -> str:
    out_dir = ensure_preview_subdir("editing", project_id)
    path = out_dir / f"{unit_id}-{uuid.uuid4().hex[:8]}-storyboard.svg"
    panels = plan.get("storyboard", []) or []
    # The workbench renders an exact-range ClipPreview directly from each
    # panel's source AssetVersion and timestamp. Extracting every JPEG here made
    # Plan publication wait on N sequential ffmpeg/remote range reads while the
    # resulting images were not consumed by the primary UI. Keep supplied image
    # versions, but defer optional keyframe materialization to an explicit/on-
    # demand path instead of blocking the authoritative PlanVersion.
    for panel in panels:
        if not panel.get("image_url"):
            panel["keyframe_deferred"] = True
            panel["keyframe_error"] = "关键帧由工作台按时间码实时预览"

    width = 1080
    margin_x = 28
    cols = 4
    gap = 14
    panel_w = (width - margin_x * 2 - gap * (cols - 1)) // cols
    image_h = round(panel_w * 9 / 16)
    caption_h = 86
    panel_h = image_h + caption_h
    row_gap = 34
    rows = max(1, (len(panels) + cols - 1) // cols)
    height = 92 + rows * (panel_h + row_gap)
    summary_lines = _escape_lines(
        str(plan.get("summary", "AI 剪辑关键帧分镜")),
        max_units=92,
        max_lines=2,
        limit=180,
    )
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
    ]
    for line_index, line in enumerate(summary_lines):
        chunks.append(
            f'<text x="28" y="{34 + line_index * 20}" font-family="Inter, Arial" font-size="18" font-weight="700" fill="#111827">{html.escape(line)}</text>',
        )
    chunks.append(
        f'<text x="28" y="76" font-family="Inter, Arial" font-size="12" fill="#64748b">VLM keyframe storyboard · real frames with captions · {len(panels)} panels</text>',
    )
    for index, panel in enumerate(panels):
        col = index % cols
        row = index // cols
        x = margin_x + col * (panel_w + gap)
        y = 98 + row * (panel_h + row_gap)
        title_line = _escape_lines(
            f"#{index + 1} {panel.get('title') or f'Panel {index + 1}'}",
            max_units=32,
            max_lines=1,
            limit=60,
        )[0]
        desc_lines = _escape_lines(
            str(panel.get("description") or ""),
            max_units=38,
            max_lines=3,
            limit=120,
        )
        source = html.escape(str(panel.get("source_asset_id") or ""))
        source_line = _escape_lines(
            f"source: {panel.get('source_asset_id') or ''} · {panel.get('timestamp', 0)}s",
            max_units=38,
            max_lines=1,
            limit=72,
        )[0]
        timeline_line = _escape_lines(
            f"timeline {panel.get('timeline_start', 0)}s - {panel.get('timeline_end', 0)}s",
            max_units=38,
            max_lines=1,
            limit=72,
        )[0]
        image_href = _data_uri_for_media_image(
            str(panel.get("image_url") or ""),
        )
        chunks.extend(
            [
                f'<rect x="{x}" y="{y}" width="{panel_w}" height="{panel_h}" rx="6" fill="#ffffff" stroke="#d8e0e8"/>',
                f'<rect x="{x}" y="{y}" width="{panel_w}" height="{image_h}" rx="6" fill="#0f172a"/>',
            ],
        )
        if image_href:
            chunks.append(
                f'<image x="{x}" y="{y}" width="{panel_w}" height="{image_h}" href="{image_href}" preserveAspectRatio="xMidYMid slice"/>',
            )
        else:
            # 显示具体失败原因（素材缺失/下载失败/抽帧失败），便于排查；无原因才回落到笼统文案
            error_lines = _escape_lines(
                str(panel.get("keyframe_error") or "关键帧抽取失败"),
                max_units=42,
                max_lines=2,
                limit=80,
            )
            chunks.append(
                f'<text x="{x + 18}" y="{y + 86}" font-family="Inter, Arial" font-size="13" fill="#fca5a5">{html.escape(error_lines[0])}</text>',
            )
            if len(error_lines) > 1:
                chunks.append(
                    f'<text x="{x + 18}" y="{y + 106}" font-family="Inter, Arial" font-size="11" fill="#94a3b8">{html.escape(error_lines[1])}</text>',
                )
            chunks.append(
                f'<text x="{x + 18}" y="{y + 126}" font-family="Inter, Arial" font-size="11" fill="#94a3b8">source: {source}</text>',
            )
        chunks.extend(
            [
                f'<rect x="{x}" y="{y + image_h - 28}" width="{panel_w}" height="28" fill="rgba(15,23,42,0.76)"/>',
                f'<text x="{x + 10}" y="{y + image_h - 10}" font-family="Inter, Arial" font-size="11" font-weight="700" fill="#ffffff">{html.escape(title_line)}</text>',
                f'<text x="{x + 10}" y="{y + image_h + 16}" font-family="Inter, Arial" font-size="9" fill="#64748b">{html.escape(source_line)}</text>',
            ],
        )
        for line_index, line in enumerate(desc_lines):
            chunks.append(
                f'<text x="{x + 10}" y="{y + image_h + 34 + line_index * 14}" font-family="Inter, Arial" font-size="10" fill="#1f2937">{html.escape(line)}</text>',
            )
        chunks.append(
            f'<text x="{x + 10}" y="{y + panel_h - 10}" font-family="Inter, Arial" font-size="9" fill="#475569">{html.escape(timeline_line)}</text>',
        )
    chunks.append("</svg>")
    atomic_replace_bytes(path, "\n".join(chunks).encode("utf-8"))
    return media_url_for(path)


def _write_storyboard_sheet_with_retry(
    project_id: str,
    unit_id: str,
    plan: dict,
    *,
    writer: Callable[[str, str, dict], str] | None = None,
    attempts: int = 2,
) -> str:
    """Regenerate a missing Edit storyboard before publishing a PlanVersion.

    The removed ``production_run`` retried empty Edit storyboard URLs on a
    later monolithic rerun.  The refactored runtime has immutable PlanVersions,
    so the equivalent retry must happen at the AI Edit core/Task boundary,
    before the envelope becomes durable.
    """

    render = writer or _write_storyboard_sheet
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            url = str(render(project_id, unit_id, plan) or "").strip()
        except (
            Exception
        ) as exc:  # noqa: BLE001 - bounded retry then caller policy
            last_error = exc
            logger.warning(
                "AI Edit storyboard attempt %d/%d failed unit=%s: %s",
                attempt,
                attempts,
                unit_id,
                exc,
            )
            continue
        if url:
            return url
        last_error = RuntimeError(
            "AI Edit storyboard renderer returned an empty URL",
        )
        logger.warning(
            "AI Edit storyboard attempt %d/%d returned empty unit=%s",
            attempt,
            attempts,
            unit_id,
        )
    raise RuntimeError(
        f"AI Edit storyboard generation failed after {attempts} attempts",
    ) from last_error


async def build_ai_edit_plan(
    project: dict,
    unit_id: str,
    *,
    goal: str = "",
    material_asset_ids: list[str] | None = None,
    use_model: bool = True,
) -> dict:
    started = time.perf_counter()
    trace_event(
        "creator.ai_edit.plan_started",
        component="ai_edit_core",
        attributes={
            "projectId": project.get("id"),
            "unitId": unit_id,
            "contentType": project.get("contentType"),
            "requestedMaterialAssetCount": len(material_asset_ids or ()),
            "useModel": use_model,
        },
        projectId=project.get("id"),
    )
    section, unit = _find_unit(project, unit_id)
    if not section or not unit:
        raise ValueError("AI 剪辑单元不存在")
    assets = _selected_video_assets(project, unit, material_asset_ids)
    if not assets:
        raise ValueError("AI 剪辑需要至少一个视频素材")

    trace = [
        {
            "key": "edit_materials",
            "label": "剪辑素材选择",
            "status": "success",
            "detail": f"选中 {len(assets)} 个视频素材。",
        },
    ]
    analyses = _selected_source_intelligence(project, unit, assets)
    asr_segments_by_asset = _build_asr_segments_lookup(analyses)
    if use_model and analyses:
        try:
            plan = await _semantic_agent_plan(
                project,
                section,
                unit,
                assets,
                analyses,
                goal,
            )
            if project.get("contentType") == "interview":
                plan = _snap_and_cap_for_interview(
                    plan,
                    project,
                    unit,
                    asr_segments_by_asset,
                )
            trace.append(
                {
                    "key": "semantic_ai_edit_plan",
                    "label": "语义剪辑方案",
                    "status": "success",
                    "detail": (
                        f"已根据 {len(analyses)} 份素材理解结果完成语义选片，"
                        f"生成 {len(plan.get('timeline') or [])} 个片段；"
                        "存在 ASR 时已参考转写句界并记录非阻断风险建议。"
                    ),
                },
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - semantic planning is optional
            logger.warning(
                "AI Edit semantic planning fallback unit=%s: %s",
                unit_id,
                exc,
            )
            plan = _heuristic_plan(
                project,
                unit,
                assets,
                goal,
                f"语义选片未完成：{exc}",
                section,
                asr_segments_by_asset,
            )
            trace.append(
                {
                    "key": "semantic_ai_edit_plan",
                    "label": "语义剪辑方案",
                    "status": "fallback",
                    "detail": "语义选片未完成，已按叙事节拍生成基础候选方案。",
                },
            )
    else:
        fallback_reason = "调用方关闭了语义选片" if not use_model else "所选素材尚无可用的素材理解结果"
        plan = _heuristic_plan(
            project,
            unit,
            assets,
            goal,
            fallback_reason,
            section,
            asr_segments_by_asset,
        )
        trace.append(
            {
                "key": "basic_ai_edit_plan",
                "label": "基础剪辑方案",
                "status": "success",
                "detail": "已按叙事节拍生成基础候选方案。",
            },
        )

    try:
        storyboard_url = _write_storyboard_sheet_with_retry(
            project.get("id", "project"),
            unit_id,
            plan,
        )
    except Exception as exc:  # noqa: BLE001 - storyboard is optional
        logger.warning("AI Edit optional storyboard skipped: %s", exc)
        storyboard_url = ""
    plan["storyboard_image_url"] = storyboard_url
    trace.append(
        {
            "key": "storyboard_sheet",
            "label": "关键帧分镜",
            "status": "success" if storyboard_url else "skipped",
            "detail": (
                "已生成 AI 剪辑关键帧分镜图。"
                if storyboard_url
                else "分镜图为可选项，本次未生成，不阻塞剪辑方案。"
            ),
        },
    )
    envelope = {
        "unit_id": unit_id,
        "plan": plan,
        "storyboard_image_url": storyboard_url,
        "material_assets": assets,
        "workflow_trace": trace,
    }
    trace_event(
        "creator.ai_edit.plan_completed",
        component="ai_edit_core",
        attributes={
            "unitId": unit_id,
            "timelineClipCount": len(plan.get("timeline") or ()),
            "targetDurationSeconds": plan.get("target_duration"),
            "materialAssetCount": len(assets),
            "storyboardGenerated": bool(storyboard_url),
            "workflowTrace": trace,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
        },
        projectId=project.get("id"),
    )
    return envelope


def _local_media_path(url: str) -> Path:
    if url.startswith("/generated/"):
        path = media_path_from_url(url)
    elif url.startswith("file://"):
        path = Path(unquote(urlparse(url).path)).expanduser().resolve()
    else:
        raise ValueError(f"剪辑执行仅支持受控本地素材: {url}")
    if not path.exists():
        raise ValueError(f"素材文件不存在: {url}")
    return path


def _remote_cache_path(url: str, project_id: str) -> Path:
    """URL 视频下载到本地的缓存路径：remote-{url哈希前12位}-{basename}。

    按 URL 哈希命名，重复执行剪辑时复用缓存，不重复下载。
    """
    parsed = urlparse(url)
    basename = unquote(Path(parsed.path).name) or "remote-video.mp4"
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    cache_dir = ensure_task_work_subdir("uploads", project_id)
    return cache_dir / f"remote-{url_hash}-{basename}"


def _source_local_path(url: str, project_id: str) -> Path:
    """把受控本地或 http(s) 素材解析为本地可剪路径。

    - /generated/ 或 file:// 开头：受控本地素材，直接返回（含存在性校验）。
    - http(s):// 开头：下载到当前 ``task-work``（已存在则复用），
      供 ffmpeg 裁剪/抽帧。VLM 理解阶段仍直读 URL（不下载），仅执行/抽帧需要本地文件。
    - 其他：不支持。
    """
    if url.startswith(("/generated/", "file://")):
        return _local_media_path(url)
    if url.startswith(("http://", "https://")):
        cached = _remote_cache_path(url, project_id)
        if not cached.exists():
            download_remote_file(url, str(cached))
        return cached
    raise ValueError(f"不支持的素材来源: {url}")


def _execution_source_url(
    project: dict[str, Any],
    clip: dict[str, Any],
) -> str:
    """Prefer the exact AssetVersion's completed ingest cache for ffmpeg.

    Planning persists the provider-facing ``source_url`` so a remote video can
    be understood immediately.  A later execute Run receives a fresh projection
    where the same immutable AssetVersion may now expose its content-store
    ``file://`` cache.  Match by version first, then by logical id plus the exact
    native/public URL; never take an unrelated historical version's local file.
    """

    source_url = str(clip.get("source_url") or "")
    asset_id = str(clip.get("asset_id") or "")
    version_id = str(clip.get("asset_version_id") or "")
    assets = [
        asset
        for asset in project.get("assets", []) or []
        if isinstance(asset, dict) and str(asset.get("id") or "") == asset_id
    ]
    if version_id:
        assets = [
            asset
            for asset in assets
            if str(asset.get("versionId") or "") == version_id
        ]
    else:
        url_matches = [
            asset
            for asset in assets
            if source_url
            in {
                str(asset.get("url") or ""),
                str(asset.get("nativeModelUrl") or ""),
            }
        ]
        # Without exact version provenance, only a unique URL match is safe.
        assets = url_matches if len(url_matches) == 1 else []

    if len(assets) == 1:
        asset = assets[0]
        cache = (
            asset.get("cache") if isinstance(asset.get("cache"), dict) else {}
        )
        for candidate in (
            asset.get("url"),
            asset.get("localUrl"),
            asset.get("cacheUrl"),
            cache.get("url"),
        ):
            local_url = str(candidate or "")
            if local_url.startswith(("/generated/", "file://")):
                return local_url
    return source_url


def _probe_video_size(video_path: str) -> tuple[int, int]:
    """Return the first video stream size, with an ffmpeg-compatible fallback."""
    try:
        metadata = probe_media(video_path, timeout=15)
        if metadata.width and metadata.height:
            return metadata.width, metadata.height
    except MediaProbeError:
        logger.debug("media size lookup failed", exc_info=True)
    return 1280, 720


async def execute_ai_edit_plan(
    project: dict,
    unit_id: str,
    plan: dict,
    on_clip_done: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict:
    """Execute an edit plan with ffmpeg using controlled local/task scratch."""
    started = time.perf_counter()
    logger.info(
        "execute_ai_edit_plan unit=%s timeline_len=%d",
        unit_id,
        len(plan.get("timeline") or [])
        if isinstance(plan.get("timeline"), list)
        else 0,
    )
    section, unit = _find_unit(project, unit_id)
    if not section or not unit:
        raise ValueError("AI 剪辑单元不存在")
    timeline = (
        plan.get("timeline") if isinstance(plan.get("timeline"), list) else []
    )
    if not timeline:
        raise ValueError("剪辑方案没有 timeline")
    expected_overlay_kind = _expected_overlay_kind(project)
    ordered_timeline = sorted(timeline, key=lambda item: item.get("order", 0))
    validated_overlays = [
        _validate_execution_overlay_copy(
            clip,
            expected_kind=expected_overlay_kind,
            clip_index=index + 1,
            clip_duration=max(
                0.5,
                float(
                    clip.get("duration")
                    or (
                        float(clip.get("end", 5) or 5)
                        - float(clip.get("start", 0) or 0)
                    ),
                ),
            ),
        )
        for index, clip in enumerate(ordered_timeline)
    ]
    if expected_overlay_kind == "interview_summary":
        for index, clip in enumerate(ordered_timeline):
            if validated_overlays[index] is not None:
                continue
            reason = str(clip.get("reason") or "").strip()
            if not reason:
                continue
            clip_dur = max(
                0.5,
                float(
                    clip.get("duration")
                    or (
                        float(clip.get("end", 5) or 5)
                        - float(clip.get("start", 0) or 0)
                    ),
                ),
            )
            validated_overlays[index] = {
                "kind": "interview_summary",
                "text": reason[:30],
                "appear_at": 0.2,
                "duration": min(3.0, max(0.5, clip_dur - 0.3)),
            }
    trace_event(
        "creator.ai_edit.ffmpeg_started",
        component="ai_edit_core",
        attributes={
            "unitId": unit_id,
            "clipCount": len(ordered_timeline),
            "targetDurationSeconds": sum(
                float(item.get("duration") or 0) for item in ordered_timeline
            ),
            "overlayKind": expected_overlay_kind,
        },
        projectId=project.get("id"),
    )

    readiness = ffmpeg_readiness()
    if readiness["status"] != "ok":
        logger.warning(
            "execute_ai_edit_plan ffmpeg 未就绪: %s",
            readiness.get("blockers"),
        )
        trace_event(
            "creator.ai_edit.ffmpeg_failed",
            component="ai_edit_core",
            status="error",
            attributes={
                "stage": "readiness",
                "blockers": readiness["blockers"],
            },
            projectId=project.get("id"),
        )
        return {
            "success": False,
            "output_url": None,
            "blockers": readiness["blockers"],
            "runtime_readiness": {"ffmpeg": readiness},
        }
    ffmpeg = readiness["path"]
    out_dir = ensure_task_work_subdir("editing", project.get("id", "project"))
    work_dir = out_dir / f"{unit_id}-{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    clip_durations: list[float] = []
    transitions: list[str] = []
    resolved_sources: dict[tuple[str, str, str], Path] = {}

    for index, clip in enumerate(ordered_timeline):
        source_url = str(clip.get("source_url") or "")
        source_key = (
            str(clip.get("asset_id") or ""),
            str(clip.get("asset_version_id") or ""),
            source_url,
        )
        source_path = resolved_sources.get(source_key)
        if source_path is None:
            execution_url = _execution_source_url(project, clip)
            source_path = _source_local_path(
                execution_url,
                project.get("id", "project"),
            )
            resolved_sources[source_key] = source_path
        start = max(0.0, float(clip.get("start", 0) or 0))
        duration = max(
            0.5,
            float(
                clip.get("duration")
                or (float(clip.get("end", start + 4.7)) - start),
            ),
        )
        clip_path = work_dir / f"clip-{index + 1:02d}.mp4"
        logger.info(
            "execute_ai_edit_plan clip#%d/%d source_url=%s source_path=%s start=%.2f duration=%.2f",
            index + 1,
            len(ordered_timeline),
            source_url[:80],
            source_path,
            start,
            duration,
        )
        clip_started = time.perf_counter()
        trace_event(
            "creator.ai_edit.clip_started",
            component="ai_edit_core",
            attributes={
                "unitId": unit_id,
                "clipIndex": index + 1,
                "clipCount": len(ordered_timeline),
                "assetId": clip.get("asset_id"),
                "assetVersionId": clip.get("asset_version_id"),
                "sourceStartSeconds": start,
                "durationSeconds": duration,
                "overlayKind": validated_overlays[index].get("kind")
                if validated_overlays[index]
                else None,
            },
            projectId=project.get("id"),
        )
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(source_path),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(clip_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "execute_ai_edit_plan clip#%d 裁剪失败 rc=%d stderr=%s",
                index + 1,
                result.returncode,
                (result.stderr or "")[-300:],
            )
            trace_event(
                "creator.ai_edit.clip_failed",
                component="ai_edit_core",
                status="error",
                attributes={
                    "unitId": unit_id,
                    "clipIndex": index + 1,
                    "stage": "trim",
                    "returnCode": result.returncode,
                    "stderrTail": (result.stderr or "")[-500:],
                },
                projectId=project.get("id"),
            )
            return {
                "success": False,
                "output_url": None,
                "blockers": [f"FFmpeg 裁剪失败: {result.stderr[-500:]}"],
                "runtime_readiness": {"ffmpeg": readiness},
                "work_dir": str(work_dir),
            }

        overlay_copy = validated_overlays[index]
        if overlay_copy is not None:
            video_size = _probe_video_size(str(clip_path))
            rendered_path = work_dir / f"clip-{index + 1:02d}-overlay.mp4"
            if overlay_copy["kind"] == "pet_os":
                render_result = render_pet_os_overlay(
                    ffmpeg_path=ffmpeg,
                    input_path=clip_path,
                    output_path=rendered_path,
                    text=str(overlay_copy["text"]),
                    vibe=str(overlay_copy["vibe"]),
                    video_size=video_size,
                    appear_at=float(overlay_copy["appear_at"]),
                    duration=float(overlay_copy["duration"]),
                )
            else:
                render_result = render_interview_summary_overlay(
                    ffmpeg_path=ffmpeg,
                    input_path=clip_path,
                    output_path=rendered_path,
                    text=str(overlay_copy["text"]),
                    video_size=video_size,
                    appear_at=float(overlay_copy["appear_at"]),
                    duration=float(overlay_copy["duration"]),
                )
            if not render_result.success:
                logger.warning(
                    "editorial overlay failed clip#%d kind=%s: %s",
                    index + 1,
                    overlay_copy["kind"],
                    render_result.error,
                )
                trace_event(
                    "creator.ai_edit.clip_failed",
                    component="ai_edit_core",
                    status="error",
                    attributes={
                        "unitId": unit_id,
                        "clipIndex": index + 1,
                        "stage": "overlay",
                        "overlayKind": overlay_copy["kind"],
                        "error": render_result.error,
                    },
                    projectId=project.get("id"),
                )
                return {
                    "success": False,
                    "output_url": None,
                    "blockers": [
                        f"{overlay_copy['kind']} 渲染失败: {render_result.error}",
                    ],
                    "runtime_readiness": {"ffmpeg": readiness},
                    "work_dir": str(work_dir),
                }
            clip_path.unlink(missing_ok=True)
            rendered_path.rename(clip_path)
            logger.info(
                "editorial overlay applied clip#%d kind=%s text=%r",
                index + 1,
                overlay_copy["kind"],
                str(overlay_copy["text"])[:30],
            )
        trace_event(
            "creator.ai_edit.clip_completed",
            component="ai_edit_core",
            attributes={
                "unitId": unit_id,
                "clipIndex": index + 1,
                "durationSeconds": duration,
                "overlayApplied": overlay_copy is not None,
                "durationMs": round(
                    (time.perf_counter() - clip_started) * 1000,
                    3,
                ),
            },
            projectId=project.get("id"),
        )
        clip_paths.append(clip_path)
        clip_durations.append(duration)
        if on_clip_done is not None:
            await on_clip_done(index + 1, len(ordered_timeline))
        # transitions[i] describes the pair (i-1, i); force cut for clip 0.
        transitions.append(
            "cut",
        )  # always hard cut; xfade not used for manual timing

    output_path = out_dir / f"{unit_id}-{uuid.uuid4().hex[:8]}-ai-edit.mp4"
    any_xfade = any(t != "cut" for t in transitions)

    if any_xfade and len(clip_paths) > 1:
        # xfade path: crossfade video + audio between non-cut pairs.
        from services.media.ffmpeg import (
            _has_audio_stream,
            build_xfade_command,
        )

        has_audio = [_has_audio_stream(ffmpeg, str(p)) for p in clip_paths]
        xfade_cmd = build_xfade_command(
            ffmpeg,
            [str(p) for p in clip_paths],
            clip_durations,
            transitions,
            str(output_path),
            has_audio=has_audio,
        )
        result = subprocess.run(
            xfade_cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "execute_ai_edit_plan xfade 拼接失败 rc=%d stderr=%s，回退到 concat -c copy",
                result.returncode,
                (result.stderr or "")[-300:],
            )
            # Fallback to concat -c copy below.
            any_xfade = False
        else:
            trace_event(
                "creator.ai_edit.concat_completed",
                component="ai_edit_core",
                attributes={"mode": "xfade", "clipCount": len(clip_paths)},
                projectId=project.get("id"),
            )

    if not any_xfade or len(clip_paths) == 1:
        concat_file = work_dir / "concat.txt"
        atomic_replace_bytes(
            concat_file,
            "\n".join(
                f"file '{path.as_posix()}'" for path in clip_paths
            ).encode("utf-8"),
        )
        concat_cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ]
        result = subprocess.run(
            concat_cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "execute_ai_edit_plan 拼接失败 rc=%d stderr=%s",
                result.returncode,
                (result.stderr or "")[-300:],
            )
            trace_event(
                "creator.ai_edit.ffmpeg_failed",
                component="ai_edit_core",
                status="error",
                attributes={
                    "stage": "concat",
                    "returnCode": result.returncode,
                    "stderrTail": (result.stderr or "")[-500:],
                },
                projectId=project.get("id"),
            )
            return {
                "success": False,
                "output_url": None,
                "blockers": [f"FFmpeg 拼接失败: {result.stderr[-500:]}"],
                "runtime_readiness": {"ffmpeg": readiness},
                "work_dir": str(work_dir),
            }
        trace_event(
            "creator.ai_edit.concat_completed",
            component="ai_edit_core",
            attributes={"mode": "concat_copy", "clipCount": len(clip_paths)},
            projectId=project.get("id"),
        )

    logger.info(
        "execute_ai_edit_plan 成功 unit=%s output=%s clips=%d",
        unit_id,
        media_url_for(output_path),
        len(clip_paths),
    )
    trace_event(
        "creator.ai_edit.ffmpeg_completed",
        component="ai_edit_core",
        attributes={
            "unitId": unit_id,
            "clipCount": len(clip_paths),
            "outputUrl": media_url_for(output_path),
            "outputSizeBytes": output_path.stat().st_size
            if output_path.exists()
            else None,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
        },
        projectId=project.get("id"),
    )
    return {
        "success": True,
        "output_url": media_url_for(output_path),
        "output_path": str(output_path),
        "updated_timeline": ordered_timeline,
        "blockers": [],
        "runtime_readiness": {"ffmpeg": readiness},
        "work_dir": str(work_dir),
    }
