# -*- coding: utf-8 -*-
"""First-class video task kinds and the continuity planning layer.

Wan3.0 (and the other All-in-One families) expose five peer task types
that the provider routes on ``input.media`` types plus prompt intent:
text-to-video, image-to-video (first / first+last frame), omni
reference generation, video editing and video extension. They are
*peers*: extension and editing are not decorations on top of the
reference stack, they are their own request shapes.

Two contract facts (official docs, M0-verified against the live API on
2026-11-19) shape the planner:

* ``first_frame``/``last_frame`` are mutually exclusive with every
  ``reference_*`` type, so a continuation that needs pixel-level
  anchoring cannot also carry the cast reference stack.
* An extension response CONTAINS the material: submitting an 8s clip
  with ``duration=13`` returns a 13s video whose first 8s are the
  material (output head frame SSIM 0.81 vs the material's first frame).
  Callers must submit ``duration = material + new`` and trim the
  material prefix before publishing, or the segment duplicates its
  predecessor on the timeline.

The planner is pure: facts in, one ``VideoTaskPlan`` out. It never
touches the filesystem, providers or the Project graph; the execution
layer gathers durable facts and runs the plan.
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


class VideoTaskKind(StrEnum):
    """The five peer provider task types a submission materializes as.

    Values match the wire ``mode`` strings consumed by
    ``video_model.submit_video_task`` so a plan's kind can be handed
    straight to the provider layer.
    """

    T2V = "t2v"
    I2V = "i2v"
    R2V = "r2v"
    VIDEO_EDIT = "video_edit"
    # Continuation: media carries ONLY the predecessor video as
    # ``reference_video`` plus an extend-intent prompt. No reference
    # stack, no synthetic ids, no last-frame image — the predecessor's
    # own footage is the continuity, and the published artifact is the
    # material prefix trimmed off.
    VIDEO_EXTEND = "video_extend"


@dataclass(frozen=True, slots=True)
class ContinuityFacts:
    """Deterministic, already-published inputs to one routing decision.

    ``predecessor_version_id`` is the predecessor Element's selected
    main-slot artifact (the real Asset Index version an extension
    references); ``predecessor_duration_seconds`` is probed from it.
    ``same_scene`` compares the two Elements' ``scene_ref``; ``
    new_elements`` is true when this segment introduces a character or
    prop the predecessor did not carry. ``cross_episode`` marks a
    segment with no in-timeline predecessor (a new episode's opener).
    Everything here is durable data, so the same project state always
    routes the same way (claim/submit replay safe).
    """

    creation_type: str = "r2v"
    has_published_predecessor: bool = False
    predecessor_version_id: str = ""
    predecessor_duration_seconds: float = 0.0
    same_scene: bool = False
    cross_episode: bool = False
    new_elements: bool = False
    explicit_first_frame: bool = False
    segment_duration_seconds: int = 0
    ffmpeg_ready: bool = True
    video_extension_supported: bool = False
    # Author-intent signals read off the Timeline (see the routing
    # matrix): ``transition_kind`` is the normalized kind of an explicit
    # Transition element between predecessor and this segment
    # ("none"/"cut"/"blend"); ``continuity_intent`` classifies the
    # segment's ``creation.continuity`` text ("continue"/"cut"/
    # "neutral"); ``one_take`` marks continuity text that explicitly
    # asks for an unbroken camera continuation (一镜到底/延续运镜), the
    # only way VIDEO_EXTEND is still chosen for an r2v segment.
    transition_kind: str = "none"
    continuity_intent: str = "neutral"
    one_take: bool = False


@dataclass(frozen=True, slots=True)
class VideoTaskPlan:
    """The routed task kind plus everything the submit path must honour.

    ``predecessor_version_id``/``material_duration_seconds``/
    ``trim_offset_seconds`` are only meaningful for VIDEO_EXTEND (the
    material is the predecessor's whole published video). ``ratio``
    overrides the project ratio when the kind must follow the material
    (extension) instead of the plan. ``submit_duration_seconds`` is the
    provider duration (extension semantics: material + new); the
    timeline keeps the Element's own duration separately.
    ``auto_first_frame`` marks an I2V whose first frame is adopted from
    the predecessor's last frame rather than authored.
    ``strong_continuity`` marks an R2V whose reference stack the
    executor must lead with the predecessor's last frame (promoted to
    图1, authored [Image N] markers shifted +1) so a same-scene
    continuous take opens on the predecessor's final picture; A/B
    measurement showed the buried-anchor stack (storyboard-led) seams at
    SSIM 0.39-0.53 while a single promoted anchor reaches ~0.79.
    """

    kind: VideoTaskKind
    predecessor_version_id: str = ""
    material_duration_seconds: float = 0.0
    ratio: str = ""
    submit_duration_seconds: int = 0
    trim_offset_seconds: float | None = None
    auto_first_frame: bool = False
    strong_continuity: bool = False


def video_continuity_mode() -> str:
    """Unified operator dial for inter-segment continuity: auto/weak/off.

    ``auto`` (default) lets the planner route same-scene segments onto
    the strongest continuation kind the facts allow; ``weak`` and
    ``off`` both pin segments to plain R2V (no continuation), the
    difference being historical only. The deprecated
    ``CREATOR_CONTINUITY_TAIL_CLIP`` alias maps ``0`` to weak so
    already-deployed hosts keep semantics.
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


# Project-level dial (the UI "段间连贯优先" switch) mapped onto the
# planner modes: continuity == auto routing, throughput == plain r2v
# everywhere. An unset value falls back to the env dial, so hosts that
# still pin CREATOR_VIDEO_CONTINUITY keep working until the project
# carries an explicit choice.
_PROJECT_DIAL_MODES = {
    "continuity": CONTINUITY_MODE_AUTO,
    "throughput": CONTINUITY_MODE_WEAK,
}


def resolve_continuity_mode(project_value: str | None = None) -> str:
    """One dial for both the executor and the work graph.

    Precedence: the project's explicit ``settings.video_continuity``
    (what the UI switch writes) beats the global env fallback. Keeping
    the resolution in one pure function is what stops the dependency
    graph and the routing from ever disagreeing about a segment.
    """

    mapped = _PROJECT_DIAL_MODES.get(str(project_value or ""))
    if mapped is not None:
        return mapped
    return video_continuity_mode()


# Author-intent keyword tables shared by the planner, the fingerprint
# and the work graph's dependency decision. Cut vocabulary wins over
# continuation vocabulary (a sentence mixing both describes an edit).
CONTINUITY_CUT_KEYWORDS = (
    "切到",
    "切换到",
    "另一机位",
    "时间跳转",
    "回忆",
    "闪回",
    "转场到",
)
CONTINUITY_CONTINUE_KEYWORDS = (
    "承接",
    "继续",
    "同一动作",
    "延续",
    "一镜",
)
CONTINUITY_ONE_TAKE_KEYWORDS = ("一镜到底", "延续运镜")


def continuity_signals(
    elements_by_id: dict,
    element,
    prev,
) -> tuple[str, str, bool]:
    """Author-intent signals from durable Project data only.

    Returns ``(transition_kind, continuity_intent, one_take)``: the
    normalized kind of an explicit Transition element wired
    predecessor→this segment ("none"/"cut"/"blend"), the keyword class
    of ``creation.continuity``, and whether the text asks for an
    unbroken camera continuation. Pure so the dispatch resolver, the
    claim fingerprint and the work graph derive identical values.
    """

    transition_kind = "none"
    if prev is not None:
        for item in elements_by_id.values():
            creation = item.creation
            if (
                getattr(creation, "type", "") == "transition"
                and creation.from_element_id == prev.element_id
                and creation.to_element_id == element.element_id
            ):
                from services.media_files.transitions import (
                    normalize_transition_kind,
                )

                transition_kind = (
                    "cut"
                    if normalize_transition_kind(creation.transition_kind)
                    == "cut"
                    else "blend"
                )
                break
    text = str(getattr(element.creation, "continuity", "") or "")
    one_take = any(k in text for k in CONTINUITY_ONE_TAKE_KEYWORDS)
    if any(k in text for k in CONTINUITY_CUT_KEYWORDS):
        intent = "cut"
    elif any(k in text for k in CONTINUITY_CONTINUE_KEYWORDS):
        intent = "continue"
    else:
        intent = "neutral"
    return transition_kind, intent, one_take


def r2v_may_consume_predecessor(
    elements_by_id: dict,
    element,
    prev,
) -> bool:
    """Whether an r2v segment can be routed onto an anchored shape.

    The work graph serializes a video node behind its predecessor only
    while this holds; scene changes, explicit transitions, cut-flavoured
    continuity and newly introduced elements all route to plain omni
    reference, which never reads the predecessor's footage — gating
    those waits was over-conservative serialization. Mirrors the
    planner's rules 2-4 exactly (rule 1's dial is resolved by the
    caller), and it is cheap pure data so graph and executor agree.
    """

    if prev is None:
        return False
    if getattr(prev.creation, "scene_ref", None) != getattr(
        element.creation,
        "scene_ref",
        None,
    ):
        return False
    prev_refs = set(getattr(prev.creation, "character_refs", []) or [])
    prev_refs |= set(getattr(prev.creation, "prop_refs", []) or [])
    cur_refs = set(getattr(element.creation, "character_refs", []) or [])
    cur_refs |= set(getattr(element.creation, "prop_refs", []) or [])
    if cur_refs - prev_refs:
        return False
    transition_kind, intent, _one_take = continuity_signals(
        elements_by_id,
        element,
        prev,
    )
    if transition_kind != "none" or intent == "cut":
        return False
    return True


def _plain(
    facts: ContinuityFacts,
    kind: VideoTaskKind,
    *,
    ratio: str,
    auto_first_frame: bool = False,
) -> VideoTaskPlan:
    return VideoTaskPlan(
        kind=kind,
        ratio=ratio,
        submit_duration_seconds=facts.segment_duration_seconds,
        auto_first_frame=auto_first_frame,
    )


# pylint: disable-next=too-many-return-statements
def select_video_task_kind(
    base_mode: str,
    facts: ContinuityFacts,
    *,
    mode: str = CONTINUITY_MODE_AUTO,
    project_ratio: str = "",
) -> VideoTaskPlan:
    """Route one segment submission onto a first-class task kind.

    Non-r2v base modes keep their own kind (the author already chose
    i2v/t2v/video_edit; i2v may still auto-adopt the predecessor frame).
    For an r2v base the planner applies the author-intent routing rules
    in order — the seam evidence (A/B, 2026-11-24) is that a PROMOTED
    last-frame anchor inside the reference stack stitches nearly as well
    as pixel-locking while keeping the cast references and the bgm
    reference_audio channel, so same-scene continuations stay R2V:

    1. ``off``/``weak``, no published predecessor, or a new episode:
       plain R2V.
    2. An explicit Transition element between predecessor and this
       segment (cut OR blend): plain R2V — the author asked for an edit
       point, and a crossfade hides the seam by construction.
    3. continuity text with cut vocabulary (切到/另一机位/时间跳转…):
       plain R2V.
    4. Scene change or newly introduced characters/props: plain R2V —
       new anchors need the reference stack, and a cut fights pixel
       continuation.
    5. ``one_take`` text, extension-capable model, whole predecessor
       within the 15s/30s budgets: VIDEO_EXTEND (camera and audio
       literally continue; output is prefix-trimmed before publishing).
    6. Otherwise (same scene, continuous-take or neutral intent):
       R2V with ``strong_continuity`` — the executor extracts the
       predecessor's last frame and leads the reference stack with it.
       Without ffmpeg the anchor cannot be extracted, so fall back to
       plain R2V.
    """

    if base_mode != "r2v":
        kind = VideoTaskKind(base_mode)
        return _plain(
            facts,
            kind,
            ratio=project_ratio,
            auto_first_frame=(
                kind is VideoTaskKind.I2V and not facts.explicit_first_frame
            ),
        )

    if (
        mode in (CONTINUITY_MODE_OFF, CONTINUITY_MODE_WEAK)
        or not facts.has_published_predecessor
        or facts.cross_episode
    ):
        return _plain(facts, VideoTaskKind.R2V, ratio=project_ratio)
    if facts.transition_kind != "none" or facts.continuity_intent == "cut":
        return _plain(facts, VideoTaskKind.R2V, ratio=project_ratio)
    if not facts.same_scene or facts.new_elements:
        return _plain(facts, VideoTaskKind.R2V, ratio=project_ratio)

    segment = facts.segment_duration_seconds
    budget = (
        WAN_30_MAX_INPUT_PLUS_OUTPUT_SECONDS - WAN_30_EXTEND_HEADROOM_SECONDS
    )
    prev = facts.predecessor_duration_seconds
    if (
        facts.one_take
        and facts.video_extension_supported
        and facts.predecessor_version_id
        and 0 < prev <= WAN_30_MAX_REFERENCE_VIDEO_SECONDS
        and prev + segment <= budget
    ):
        return VideoTaskPlan(
            kind=VideoTaskKind.VIDEO_EXTEND,
            predecessor_version_id=facts.predecessor_version_id,
            material_duration_seconds=prev,
            # The provider matches the material's own frame; the project
            # ratio must not force a letterbox mid-clip.
            ratio="adaptive",
            submit_duration_seconds=int(math.ceil(prev + segment)),
            trim_offset_seconds=prev,
        )
    if facts.ffmpeg_ready:
        plan = _plain(facts, VideoTaskKind.R2V, ratio=project_ratio)
        return VideoTaskPlan(
            kind=plan.kind,
            ratio=plan.ratio,
            submit_duration_seconds=plan.submit_duration_seconds,
            strong_continuity=True,
        )
    return _plain(facts, VideoTaskKind.R2V, ratio=project_ratio)


__all__ = [
    "CONTINUITY_MODE_AUTO",
    "CONTINUITY_MODE_OFF",
    "CONTINUITY_MODE_WEAK",
    "ContinuityFacts",
    "VideoTaskKind",
    "VideoTaskPlan",
    "continuity_signals",
    "r2v_may_consume_predecessor",
    "resolve_continuity_mode",
    "select_video_task_kind",
    "video_continuity_mode",
]
