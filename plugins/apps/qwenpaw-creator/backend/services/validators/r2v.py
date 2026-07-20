# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long,too-many-branches,too-many-statements
# pylint: disable=unused-argument
"""Operation-level R2V validation; never used as delegate-admission inference."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from domain.enums import UnitTaskType

from .base import ValidationIssue, ValidationReport
from .unit_segments import MAX_R2V_UNIT_DURATION_SECONDS


# ffprobe reports encoded container duration at frame granularity.  Real Wan
# results requested at 4 seconds are commonly 4.04 seconds, so a strict float
# comparison would reject a provider-compliant 15-second result solely for one
# trailing frame.  Planning/submission remain hard-limited to 15 seconds; this
# epsilon applies only to post-download measurement.
R2V_PROBE_DURATION_EPSILON_SECONDS = 0.1


@dataclass(frozen=True, slots=True)
class ProviderCapabilitySnapshot:
    provider: str
    model: str
    version: str
    captured_at: datetime
    min_duration_seconds: float
    max_duration_seconds: float
    max_reference_images: int
    allowed_durations_seconds: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class R2VExecutionRequest:
    unit_ref: str
    route: str
    duration_seconds: float
    storyboard_version_ref: str | None
    storyboard_checksum: str | None
    video_prompt: str
    reference_image_refs: tuple[str, ...]
    transaction_active: bool
    input_fingerprint: str
    expected_slot_generation: int | None
    observed_slot_generation: int | None
    capability: ProviderCapabilitySnapshot
    authorization_valid: bool = True


def validate_r2v_execution(request: R2VExecutionRequest) -> ValidationReport:
    issues: list[ValidationIssue] = []
    target = request.unit_ref
    capability = request.capability
    if request.route != UnitTaskType.R2V.value:
        issues.append(
            ValidationIssue(
                "R2V_ROUTE_REQUIRED",
                "Unit route 必须为 r2v",
                target,
            ),
        )
    if request.duration_seconds > MAX_R2V_UNIT_DURATION_SECONDS:
        issues.append(
            ValidationIssue(
                "R2V_DURATION_MAX",
                "R2V Unit 总时长不能超过 15 秒",
                target,
            ),
        )
    if (
        request.duration_seconds < capability.min_duration_seconds
        or request.duration_seconds > capability.max_duration_seconds
    ):
        issues.append(
            ValidationIssue(
                "R2V_PROVIDER_DURATION",
                f"时长不在 provider 能力范围 {capability.min_duration_seconds:g}-{capability.max_duration_seconds:g} 秒",
                target,
            ),
        )
    if (
        capability.allowed_durations_seconds
        and request.duration_seconds
        not in capability.allowed_durations_seconds
    ):
        issues.append(
            ValidationIssue(
                "R2V_DURATION_DISCRETE",
                "时长不在 provider 离散时长集合中",
                target,
            ),
        )
    if not request.storyboard_version_ref or not request.storyboard_checksum:
        issues.append(
            ValidationIssue(
                "R2V_STORYBOARD_REQUIRED",
                "提交视频任务必须引用具体 storyboard version",
                target,
            ),
        )
    if not request.video_prompt.strip():
        issues.append(
            ValidationIssue("R2V_PROMPT_REQUIRED", "视频 Prompt 不能为空", target),
        )
    if len(request.reference_image_refs) > capability.max_reference_images:
        issues.append(
            ValidationIssue(
                "R2V_REFERENCE_LIMIT",
                "参考图数量超过 provider 上限",
                target,
            ),
        )
    if request.storyboard_version_ref and (
        not request.reference_image_refs
        or request.reference_image_refs[0] != request.storyboard_version_ref
    ):
        issues.append(
            ValidationIssue(
                "R2V_STORYBOARD_FIRST",
                "storyboard 必须是第一张参考图",
                target,
            ),
        )
    if not request.transaction_active:
        issues.append(
            ValidationIssue(
                "TRANSACTION_NOT_ACTIVE",
                "R2V execution 必须绑定 active Transaction",
                target,
            ),
        )
    if not request.input_fingerprint:
        issues.append(
            ValidationIssue("INPUT_FINGERPRINT_REQUIRED", "必须持久化输入指纹", target),
        )
    if (
        request.expected_slot_generation is None
        or request.observed_slot_generation != request.expected_slot_generation
    ):
        issues.append(
            ValidationIssue(
                "SLOT_GENERATION_STALE",
                "目标 video Slot generation 已变化",
                target,
            ),
        )
    if not request.authorization_valid:
        issues.append(
            ValidationIssue(
                "EXECUTION_AUTH_REQUIRED",
                "execution authorization 无效",
                target,
            ),
        )
    return ValidationReport.from_iterable(issues)


def validate_actual_r2v_duration(
    duration_seconds: float,
    capability: ProviderCapabilitySnapshot,
) -> ValidationReport:
    """Do not reject an encoded R2V result based on probed duration."""

    return ValidationReport()


def stable_reference_manifest(refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(ref.strip() for ref in refs if ref.strip())


# These prompt-quality checks are the frozen, deterministic half of the R2V
# Specialist's prompt loop.  They intentionally remain heuristic: operation
# validation above decides whether execution is safe; this report tells the
# Specialist what to revise before it asks Runtime to submit.
FORBIDDEN_CONTEXT_TERMS = [
    "上一Clip",
    "下一个Clip",
    "下一Clip",
    "上一个片段",
    "下一个片段",
    "承接上一",
    "延续上一",
    "续写",
    "后续剧情",
    "转场到下一",
]

ABSTRACT_EMOTIONS = [
    "悲伤",
    "愤怒",
    "紧张",
    "焦虑",
    "开心",
    "高兴",
    "害怕",
    "孤独",
    "释然",
]
VISIBLE_EMOTION_DETAILS = [
    "低头",
    "肩",
    "手指",
    "攥",
    "呼吸",
    "眼神",
    "嘴角",
    "眉",
    "下颌",
    "胸口",
    "停顿",
    "微微",
]
ACTION_DETAIL_TERMS = [
    "缓慢",
    "轻轻",
    "微微",
    "用力",
    "停顿",
    "抬手",
    "低头",
    "转头",
    "握",
    "放下",
    "靠近",
    "后退",
    "抬起",
    "垂下",
]
CAMERA_TERMS = [
    "全景",
    "中景",
    "近景",
    "特写",
    "固定机位",
    "缓慢推",
    "平稳横移",
    "跟拍",
    "切到",
    "拉远",
    "环绕",
]
QUALITY_CONSTRAINT_TERMS = ["高清", "电影", "细节", "光影", "色彩", "无卡顿", "无闪烁"]
NEGATIVE_CONSTRAINT_TERMS = [
    "保持无字幕",
    "避免生成任何文字或字幕",
    "不要生成Logo",
    "不要生成水印",
]


@dataclass
class PromptEvaluation:
    passed: bool
    score: int
    max_score: int
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def feedback(self) -> str:
        items = self.failures + self.warnings
        return "\n".join(f"- {item}" for item in items)


def _context_list(context: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = context.get(key)
    return value if isinstance(value, list) else []


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _expected_refs(context: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for binding in _context_list(context, "reference_bindings"):
        ref = str(binding.get("ref") or "").strip()
        if ref:
            refs.append(ref)
    return refs


def evaluate_video_prompt(
    prompt: str,
    context: dict[str, Any],
) -> PromptEvaluation:
    """Evaluate a Specialist-authored prompt using the frozen P0 rubric."""

    failures: list[str] = []
    warnings: list[str] = []
    score = 0
    max_score = 13
    normalized = prompt.strip()

    if len(normalized) < 180:
        failures.append("prompt过短，缺少足够的导演描述和生成约束。")
    elif len(normalized) <= 1200:
        score += 1
    else:
        warnings.append("prompt较长，可能包含冗余信息，建议控制在约350-900字。")

    forbidden = [
        term for term in FORBIDDEN_CONTEXT_TERMS if term in normalized
    ]
    if forbidden:
        failures.append(f"包含相邻Clip或续写语义：{', '.join(forbidden)}。")
    else:
        score += 1

    expected_refs = _expected_refs(context)
    missing_refs = [ref for ref in expected_refs if ref not in normalized]
    if missing_refs:
        failures.append(f"缺少参考素材编号绑定：{', '.join(missing_refs)}。")
    elif expected_refs:
        score += 1
    else:
        warnings.append("上下文没有参考素材编号，无法验证图N/视频N绑定。")

    has_subject_definition = bool(
        re.search(r"将(?:图|图片|视频)\d+中.+定义为", normalized),
    )
    character_count = len(_context_list(context, "characters"))
    if character_count and not has_subject_definition:
        failures.append(
            "缺少Seedance建议的主体定义句式：将图N中的稳定特征定义为主体名。",
        )
    else:
        score += 1

    character_names = [
        str(item.get("name") or "")
        for item in _context_list(context, "characters")
        if item.get("name")
    ]
    missing_characters = [
        name for name in character_names if name not in normalized
    ]
    if missing_characters:
        failures.append(f"缺少角色标签持续指代：{', '.join(missing_characters)}。")
    elif character_names:
        score += 1

    shot_count = len(_context_list(context, "shots"))
    missing_shots = [
        f"镜头{index}"
        for index in range(1, min(shot_count, 4) + 1)
        if f"镜头{index}" not in normalized
    ]
    if shot_count and missing_shots:
        failures.append(f"缺少自然分镜标识：{', '.join(missing_shots)}。")
    else:
        score += 1

    if re.search(
        r"\b\d+\s*(?:-|–|—|到)\s*\d+\s*秒|\[\s*\d+\s*s",
        normalized,
        re.IGNORECASE,
    ):
        failures.append("使用了精确秒段，Seedance建议使用镜头顺序而非强行限制0-3秒。")
    else:
        score += 1

    if _contains_any(normalized, ACTION_DETAIL_TERMS):
        score += 1
    else:
        failures.append("动作描述不够细，缺少肢体部位、速度、幅度或力度。")

    abstract_hits = [term for term in ABSTRACT_EMOTIONS if term in normalized]
    if abstract_hits and not _contains_any(
        normalized,
        VISIBLE_EMOTION_DETAILS,
    ):
        failures.append("情绪仍偏抽象，需外化为可见身体细节。")
    else:
        score += 1

    if _contains_any(normalized, CAMERA_TERMS):
        score += 1
    else:
        failures.append("缺少明确镜头语言，如中景、特写、固定机位、缓慢推镜等。")

    dialogues = [
        str(item.get("dialogue") or "").strip()
        for item in _context_list(context, "shots")
        if item.get("dialogue")
    ]
    if dialogues:
        missing_dialogues = [
            dialogue
            for dialogue in dialogues
            if f"{{{dialogue}}}" not in normalized
        ]
        if missing_dialogues:
            failures.append("台词未按Seedance建议使用中文花括号{}标注。")
        else:
            score += 1
    elif "<" in normalized and ">" in normalized:
        score += 1
    else:
        warnings.append("无台词Clip建议补充<环境声/动作声>。")

    missing_negative = [
        term for term in NEGATIVE_CONSTRAINT_TERMS if term not in normalized
    ]
    if missing_negative:
        failures.append(f"缺少稳定性约束：{', '.join(missing_negative)}。")
    else:
        score += 1

    if _contains_any(normalized, QUALITY_CONSTRAINT_TERMS):
        score += 1
    else:
        failures.append(
            "缺少画质/风格收束词，如高清、电影质感、光影、色彩、无卡顿无闪烁。",
        )

    return PromptEvaluation(
        passed=not failures and score >= 11,
        score=score,
        max_score=max_score,
        failures=failures,
        warnings=warnings,
    )
