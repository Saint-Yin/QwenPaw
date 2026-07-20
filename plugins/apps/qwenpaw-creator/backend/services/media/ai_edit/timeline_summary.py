# -*- coding: utf-8 -*-
"""Human-readable AI Edit timeline projection used by Workspace diffs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def format_timeline_summary(
    *,
    plan_version_id: str,
    timeline: Sequence[Mapping[str, Any]],
    duration: float,
) -> str:
    lines = [
        f"AI Edit Plan：{plan_version_id}",
        f"Timeline 片段：{len(timeline)}",
        f"目标时长：{duration:g} 秒",
        "片段范围：",
    ]
    for index, clip in enumerate(timeline, 1):
        clip_id = str(clip.get("clip_id") or f"clip-{index:02d}")
        start = float(clip.get("start") or 0)
        end = float(clip.get("end") or 0)
        lines.append(f"- {clip_id}: {start:g}–{end:g} 秒")
    return "\n".join(lines) + "\n"
