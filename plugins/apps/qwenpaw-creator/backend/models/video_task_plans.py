# -*- coding: utf-8 -*-
"""Wan3.0 video task-shape planning and the continuity operator mode.

Wan3.0 is All-in-One: one model id routes between text-to-video,
first-frame (and first/last-frame) image-to-video, omni reference
generation and video extension purely from ``input.media`` types plus
prompt intent. Two contract facts drive the plan (measured against the
official docs, and M0-verified against the live API on 2026-11-19):

* ``first_frame``/``last_frame`` are mutually exclusive with every
  ``reference_*`` type — "the last frame as first_frame WITH the cast
  reference stack" is not a request Wan3.0 can express.
* Video extension (``reference_video`` + 延长 intent) may freely combine
  with ``reference_image`` entries, and it is the only shape where the
  next segment starts *pixel-exactly* from the predecessor's tail while
  still consuming character/scene anchors.
* An extension response CONTAINS the material: submitting an 8s clip
  with ``duration=13`` returns a 13s video whose first 8s are the
  material (measured: output first frame SSIM 0.81 vs the material's
  FIRST frame, 0.40 vs its last frame). Callers must submit
  ``duration = material + new`` and trim the material prefix before
  publishing the segment artifact.

This module is pure: it never touches the filesystem, providers or the
Project graph. ``r2v_execution`` gathers the facts (predecessor
resolution, probed durations, scene identity) and executes the plan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
import math

# Wan3.0 reference_video quota: at most 5 clips totalling <=15s, and
# input + output share the 30s ceiling. The headroom absorbs provider
# rounding so a plan never submits right at the documented edge.
WAN_30_MAX_REFERENCE_VIDEO_SECONDS = 15.0
WAN_30_MAX_INPUT_PLUS_OUTPUT_SECONDS = 30.0
WAN_30_EXTEND_HEADROOM_SECONDS = 2.0
# Trimmed-tail material fallback when the whole predecessor clip cannot
# fit the budget above: enough motion for the extension to match, small
# enough to keep long segments eligible.
EXTEND_CLIP_FALLBACK_SECONDS = 5.0

CONTINUITY_MODE_AUTO = "auto"
CONTINUITY_MODE_WEAK = "weak"
CONTINUITY_MODE_OFF = "off"
_CONTINUITY_MODES = {
    CONTINUITY_MODE_AUTO,
    CONTINUITY_MODE_WEAK,
    CONTINUITY_MODE_OFF,
}
_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})

VIDEO_CONTINUITY_MODE_ENV = "CREATOR_VIDEO_CONTINUITY"
# Deprecated alias kept for one release: TAIL_CLIP=0 selects weak mode,
# any other value (including unset) leaves the unified mode's default.
LEGACY_TAIL_CLIP_ENV = "CREATOR_CONTINUITY_TAIL_CLIP"


class VideoTaskShape(StrEnum):
    """The Wan3.0 request task a segment submission materializes as."""

    TEXT_ONLY = "text_only"
    FIRST_FRAME = "first_frame"
    FIRST_LAST_FRAME = "first_last_frame"
    OMNI_REFERENCE = "omni_reference"
    # Omni reference stack PLUS a predecessor video anchor; prompt carries
    # the extension intent, so the provider continues the predecessor's
    # tail pixel-coherently while still honoring image references. The
    # published artifact is the material prefix trimmed off.
    EXTEND = "extend"


@dataclass(frozen=True, slots=True)
class ContinuityFacts:
    """Deterministic, already-published inputs to one plan decision.

    ``predecessor_duration_seconds`` is probed from the predecessor's
    selected artifact; ``same_scene`` compares the two Elements'
    ``scene_ref`` identity. Everything here is durable data, so the same
    project state always plans the same shape (claim/submit replay safe).
    """

    has_published_predecessor: bool = False
    same_scene: bool = False
    predecessor_duration_seconds: float = 0.0
    segment_duration_seconds: int = 0
    ffmpeg_ready: bool = True
    video_extension_supported: bool = False
    has_reference_stack: bool = False


@dataclass(frozen=True, slots=True)
class Wan3TaskPlan:
    """What the submit path must do differently for this segment.

    ``last_frame_anchor``: append the predecessor's last-frame image as a
    reference_image anchor (weak continuity). ``extension_material``:
    ``""`` (none), ``"full"`` (the predecessor's whole published video as
    reference_video) or ``"clip"`` (a trimmed tail of
    ``material_duration_seconds``). ``ratio`` overrides the project
    ratio when the shape must follow the material instead of the plan.
    ``submit_duration_seconds`` is the provider duration (extension
    semantics: material + new), which the timeline keeps separate as the
    Element's own duration. ``trim_offset_seconds`` is how much of the
    returned video's head is material and must be cut before publishing;
    ``None`` means the provider output is already the segment.
    """

    shape: VideoTaskShape
    last_frame_anchor: bool = False
    extension_material: str = ""
    material_duration_seconds: float = 0.0
    ratio: str = ""
    submit_duration_seconds: int = 0
    trim_offset_seconds: float | None = None


def video_continuity_mode() -> str:
    """Unified operator dial for inter-segment continuity: auto/weak/off.

    ``auto`` (default) lets the planner pick the strongest shape the
    facts allow; ``weak`` pins the image-only last-frame anchor (the
    behaviour measured as acceptable in production); ``off`` disables
    injection entirely. The deprecated ``CREATOR_CONTINUITY_TAIL_CLIP``
    alias maps ``0`` to weak so already-deployed hosts keep semantics.
    """

    raw = os.environ.get(VIDEO_CONTINUITY_MODE_ENV, "").strip().casefold()
    if raw in _CONTINUITY_MODES:
        return raw
    if raw:
        # Unknown values fail toward the conservative documented
        # behaviour, never toward skipping paid continuity silently.
        return CONTINUITY_MODE_AUTO
    legacy = os.environ.get(LEGACY_TAIL_CLIP_ENV, "").strip().casefold()
    if legacy in _DISABLED_VALUES:
        return CONTINUITY_MODE_WEAK
    return CONTINUITY_MODE_AUTO


def _omni(
    facts: ContinuityFacts,
    *,
    last_frame: bool,
    ratio: str,
) -> Wan3TaskPlan:
    return Wan3TaskPlan(
        shape=VideoTaskShape.OMNI_REFERENCE,
        last_frame_anchor=last_frame,
        ratio=ratio,
        submit_duration_seconds=facts.segment_duration_seconds,
    )


# pylint: disable-next=too-many-return-statements
def select_wan3_task_plan(
    facts: ContinuityFacts,
    *,
    mode: str = CONTINUITY_MODE_AUTO,
    project_ratio: str = "",
) -> Wan3TaskPlan:
    """Pick the strongest Wan3.0 shape the published facts allow.

    Rule order (docs + M0 measured):
    1. No predecessor / no ffmpeg / ``off``: no continuity at all.
    2. Model without a documented extension contract, or ``weak`` mode:
       last-frame image anchor inside the omni reference stack.
    3. Scene change: pixel continuation would fight the cut; anchor with
       the last frame only (weak), keeping the reference stack.
    4. Same scene on an extension-capable model: EXTEND with the whole
       predecessor video when it fits the 15s/30s budgets, else a
       trimmed tail fallback, else degrade to the weak anchor.
    First-frame shapes stay with their own request path (an authored
    ``first_frame_version_id`` or the I2V auto frame); this planner
    covers the R2V stack only.
    """

    # OMNI keeps the caller's project ratio verbatim (empty in, empty
    # out): the submit path already resolved it. Only EXTEND overrides
    # to adaptive because the material dictates the frame there.
    ratio = project_ratio
    if mode == CONTINUITY_MODE_OFF or not facts.has_published_predecessor:
        return _omni(facts, last_frame=False, ratio=ratio)
    if not facts.ffmpeg_ready:
        # No extract at all without ffmpeg: not even the image anchor.
        return _omni(facts, last_frame=False, ratio=ratio)
    if mode == CONTINUITY_MODE_WEAK or not facts.video_extension_supported:
        return _omni(facts, last_frame=True, ratio=ratio)
    if not facts.same_scene:
        return _omni(facts, last_frame=True, ratio=ratio)

    segment = facts.segment_duration_seconds
    budget = (
        WAN_30_MAX_INPUT_PLUS_OUTPUT_SECONDS - WAN_30_EXTEND_HEADROOM_SECONDS
    )
    prev = facts.predecessor_duration_seconds
    if (
        0 < prev <= WAN_30_MAX_REFERENCE_VIDEO_SECONDS
        and prev + segment <= budget
    ):
        return Wan3TaskPlan(
            shape=VideoTaskShape.EXTEND,
            last_frame_anchor=True,
            extension_material="full",
            material_duration_seconds=prev,
            # The provider matches the material's own frame; the project
            # ratio must not force a letterbox the extension path cannot
            # honour mid-clip.
            ratio="adaptive",
            submit_duration_seconds=int(math.ceil(prev + segment)),
            trim_offset_seconds=prev,
        )
    if EXTEND_CLIP_FALLBACK_SECONDS + segment <= budget:
        return Wan3TaskPlan(
            shape=VideoTaskShape.EXTEND,
            last_frame_anchor=True,
            extension_material="clip",
            material_duration_seconds=EXTEND_CLIP_FALLBACK_SECONDS,
            ratio="adaptive",
            submit_duration_seconds=int(
                EXTEND_CLIP_FALLBACK_SECONDS + segment,
            ),
            trim_offset_seconds=EXTEND_CLIP_FALLBACK_SECONDS,
        )
    return _omni(facts, last_frame=True, ratio=ratio)


__all__ = [
    "CONTINUITY_MODE_AUTO",
    "CONTINUITY_MODE_OFF",
    "CONTINUITY_MODE_WEAK",
    "ContinuityFacts",
    "VideoTaskShape",
    "Wan3TaskPlan",
    "select_wan3_task_plan",
    "video_continuity_mode",
]
