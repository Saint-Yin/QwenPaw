# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Element 转场的 xfade/acrossfade 滤镜链构造。

Timeline 中 ``creation.type=transition`` 的 Element 显式引用相邻两个主轨
Element，其 span 落在两端点 span 的时间交集内。本模块把这一模型语义翻译成
一条确定性的 ffmpeg ``filter_complex``：

- 相邻片段之间存在非硬切转场时使用 ``xfade``（视频）+ ``acrossfade``（音频）；
- 硬切（cut）或没有转场的相邻对使用 ``concat``；
- 无声片段用 ``anullsrc`` 补齐，保证 acrossfade/concat 的流对齐。

时间约定：blend 时长 d 表示相邻片段在链上的重叠消耗。第 k 对转场的
``offset = 已累计链时长 - d``，链总时长 = Σ片段时长 - Σd，与 Timeline
上"两端 Element 重叠 d、转场 span 即交集"的 authoring 约定一致。
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_TRANSITION_DURATION_SECONDS = 0.4
# xfade 官方滤镜名白名单；crossfade 是模型侧常用别名，规整为 fade。
SUPPORTED_XFADE_KINDS = {
    "fade",
    "fadeblack",
    "fadewhite",
    "dissolve",
    "wipeleft",
}
_KIND_ALIASES = {
    "crossfade": "fade",
    "": "fade",
}


def normalize_transition_kind(value: object) -> str:
    """归一 transition_kind：cut 保持硬切，未知类型回退 fade。"""

    name = str(value or "").strip().casefold()
    if name == "cut":
        return "cut"
    name = _KIND_ALIASES.get(name, name)
    if name in SUPPORTED_XFADE_KINDS:
        return name
    return "fade"


@dataclass(frozen=True, slots=True)
class TransitionClip:
    """一个已规整片段：链上时长（秒）与是否携带音频流。"""

    duration_seconds: float
    has_audio: bool


@dataclass(frozen=True, slots=True)
class TransitionJoin:
    """片段 i-1 → i 的衔接方式。``blend_seconds<=0`` 即硬切 concat。"""

    kind: str = "cut"
    blend_seconds: float = 0.0

    def effective_blend(self) -> float:
        if normalize_transition_kind(self.kind) == "cut":
            return 0.0
        return max(0.0, float(self.blend_seconds))


def compute_chain_duration(
    clips: list[TransitionClip],
    joins: list[TransitionJoin],
) -> float:
    """链总时长 = Σ片段时长 - Σ有效 blend。"""

    _validate_shapes(clips, joins)
    total = sum(clip.duration_seconds for clip in clips)
    consumed = sum(join.effective_blend() for join in joins)
    return max(0.0, total - consumed)


def _validate_shapes(
    clips: list[TransitionClip],
    joins: list[TransitionJoin],
) -> None:
    if not clips:
        raise ValueError("transition chain requires at least one clip")
    if len(joins) != len(clips) - 1:
        raise ValueError(
            f"joins/clips length mismatch: {len(joins)} vs {len(clips) - 1}",
        )
    for index, clip in enumerate(clips):
        if not clip.duration_seconds > 0:
            raise ValueError(
                f"invalid clip duration at index {index}: "
                f"{clip.duration_seconds!r}",
            )
    for index, join in enumerate(joins):
        blend = join.effective_blend()
        if blend <= 0:
            continue
        # blend 消耗前后两个片段的时间，超过任一片段都会让 offset 倒退。
        limit = min(
            clips[index].duration_seconds,
            clips[index + 1].duration_seconds,
        )
        if blend >= limit:
            raise ValueError(
                f"transition blend at join {index} ({blend:.3f}s) must be "
                f"shorter than both adjacent clips ({limit:.3f}s)",
            )


def build_transition_filter_chain(
    clips: list[TransitionClip],
    joins: list[TransitionJoin],
    *,
    canvas_size: tuple[int, int],
    fps: float = 30.0,
) -> str:
    """构造 N 片段的 filter_complex，输出 ``[vout]``/``[aout]``。

    片段先统一到 canvas 尺寸、帧率与 yuv420p，避免 xfade 因规格不一致
    失败；音频统一到 44100Hz 立体声 fltp，缺失音轨用 anullsrc 补齐。
    """

    _validate_shapes(clips, joins)
    width, height = int(canvas_size[0]), int(canvas_size[1])
    n = len(clips)
    filters: list[str] = []
    for i, clip in enumerate(clips):
        filters.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"fps={fps:g},format=yuv420p,setpts=PTS-STARTPTS[v{i}]",
        )
        if clip.has_audio:
            filters.append(
                f"[{i}:a]aresample=44100,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS[ai{i}]",
            )
        else:
            filters.append(
                "anullsrc=channel_layout=stereo:sample_rate=44100,"
                f"atrim=duration={clip.duration_seconds:.6f},"
                f"asetpts=PTS-STARTPTS[ai{i}]",
            )

    if n == 1:
        filters.append("[v0]format=yuv420p[vout]")
        filters.append("[ai0]anull[aout]")
        return ";".join(filters)

    prev_v = "v0"
    prev_a = "ai0"
    accumulated = clips[0].duration_seconds
    for i in range(1, n):
        join = joins[i - 1]
        blend = join.effective_blend()
        new_v = f"vchain{i}"
        new_a = f"achain{i}"
        if blend <= 0:
            filters.append(
                f"[{prev_v}][v{i}]concat=n=2:v=1:a=0[{new_v}]",
            )
            filters.append(
                f"[{prev_a}][ai{i}]concat=n=2:v=0:a=1[{new_a}]",
            )
            accumulated += clips[i].duration_seconds
        else:
            kind = normalize_transition_kind(join.kind)
            offset = max(0.0, accumulated - blend)
            filters.append(
                f"[{prev_v}][v{i}]xfade=transition={kind}:"
                f"duration={blend:.6f}:offset={offset:.6f}[{new_v}]",
            )
            filters.append(
                f"[{prev_a}][ai{i}]acrossfade=d={blend:.6f}:"
                f"c1=tri:c2=tri[{new_a}]",
            )
            accumulated = offset + clips[i].duration_seconds
        prev_v = new_v
        prev_a = new_a

    filters.append(f"[{prev_v}]format=yuv420p[vout]")
    filters.append(f"[{prev_a}]anull[aout]")
    return ";".join(filters)


__all__ = [
    "DEFAULT_TRANSITION_DURATION_SECONDS",
    "SUPPORTED_XFADE_KINDS",
    "TransitionClip",
    "TransitionJoin",
    "build_transition_filter_chain",
    "compute_chain_duration",
    "normalize_transition_kind",
]
