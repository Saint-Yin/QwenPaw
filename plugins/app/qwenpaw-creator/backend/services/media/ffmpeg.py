"""FFmpeg readiness, transition planning and explicit-version stitching.

This module is the mechanically relocated media implementation.  Runtime work
paths are rooted under CREATOR_DATA_ROOT via utils.paths; no generated output
is written into the source tree.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from services.runtime_files.media_probe import MediaProbeError, probe_media
from services.runtime_files.runtime_dependencies import resolve_ffmpeg
from utils.logger import setup_logger
from utils.paths import (
    ensure_task_work_subdir,
    media_path_from_url,
    media_url_for,
)
from utils.remote_download import download_remote_file


def ffmpeg_readiness() -> dict[str, Any]:
    path = resolve_ffmpeg()
    return {
        "status": "ok" if path else "missing",
        "binary": "ffmpeg",
        "path": path,
        "capabilities": ["concat_demuxer", "stream_copy", "remote_protocol_whitelist"],
        "blockers": [] if path else ["ffmpeg binary is not available on PATH or bundled dependencies"],
    }


def _sanitize_filename(name: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_length] or "video"


def download_video_to_local(
    project_id: str,
    video_id: str,
    remote_url: str,
    display_name: str = "",
    force: bool = False,
    task_id: str | None = None,
) -> str:
    del force
    try:
        extension = os.path.splitext(urlparse(remote_url).path)[1] or ".mp4"
        version = datetime.now().strftime("%m%d-%H%M%S")
        directory = ensure_task_work_subdir("downloads", project_id, task_id=task_id)
        target = directory / f"{_sanitize_filename(display_name or video_id)}_{version}{extension}"
        if not target.exists() or target.stat().st_size == 0:
            download_remote_file(remote_url, str(target))
        return media_url_for(target)
    except Exception as exc:
        logger.warning("Failed to materialize remote video %s: %s", video_id, exc)
        return remote_url


DEFAULT_TRANSITION_DURATION = 0.4
SUPPORTED_XFADE_TYPES = {"fade", "fadeblack", "fadewhite", "dissolve", "wipeleft"}
# 规整目标：跨 section 成片分辨率/帧率不一致时统一到此规格，避免 xfade 失败回退硬切。
# None 表示不强制（保留原分辨率/帧率，仅做像素格式统一）。
DEFAULT_TARGET_WIDTH: int | None = None
DEFAULT_TARGET_HEIGHT: int | None = None
DEFAULT_TARGET_FPS: float | None = 30.0


def _normalize_transition(value: Any) -> str:
    """Map per-clip transition fields to a crossfade decision.

    `cut` stays a hard cut; `fade`/`match_cut`/unknown → `fade` crossfade.
    """
    name = str(value or "fade").strip().lower() or "fade"
    if name == "cut":
        return "cut"
    return "fade"


def _resolve_xfade_type(value: Any) -> str:
    """Resolve the xfade transition type; unsupported values fall back to fade."""
    name = str(value or "fade").strip().lower() or "fade"
    if name in SUPPORTED_XFADE_TYPES:
        return name
    return "fade"


def compute_total_duration(
    durations: list[float],
    transitions: list[str],
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
) -> float:
    """Total output duration after crossfades overlap adjacent clips."""
    if not durations:
        return 0.0
    crossfade_pairs = sum(1 for t in transitions if _normalize_transition(t) != "cut")
    return max(0.0, sum(durations) - crossfade_pairs * transition_duration)


def _clip_durations_sanity(durations: list[float], transitions: list[str]) -> None:
    if len(durations) != len(transitions):
        raise ValueError(
            f"durations/transitions length mismatch: {len(durations)} vs {len(transitions)}"
        )
    for index, value in enumerate(durations):
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"invalid duration at index {index}: {value!r}")


def build_xfade_filter_chain(
    clip_durations: list[float],
    transitions: list[str],
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
    has_audio: list[bool] | None = None,
    target_width: int | None = DEFAULT_TARGET_WIDTH,
    target_height: int | None = DEFAULT_TARGET_HEIGHT,
    target_fps: float | None = DEFAULT_TARGET_FPS,
    xfade_type: str = "fade",
) -> str:
    """Build a filter_complex string for N clips with xfade + acrossfade.

    `transitions[i]` describes the transition *into* clip i (i.e. the pair
    (i-1, i)). transitions[0] is ignored — there is no pair before clip 0.

    `has_audio[i]` indicates whether clip i has an audio stream; clips without
    audio get an `anullsrc` substitute so acrossfade has matching streams.

    `target_width`/`target_height`/`target_fps` normalize every clip so xfade
    never fails on mismatched source specs (common when stitching section-level
    final videos that were produced independently). None = leave as-is.

    `xfade_type` overrides the per-pair fade type (fade/fadeblack/fadewhite/...).
    """
    _clip_durations_sanity(clip_durations, transitions)
    n = len(clip_durations)
    if n == 0:
        return ""
    resolved_xfade = _resolve_xfade_type(xfade_type)
    video_prep_filters: list[str] = []
    for i in range(n):
        filters_for_clip: list[str] = []
        if target_width and target_height:
            filters_for_clip.append(
                f"scale={int(target_width)}:{int(target_height)}:force_original_aspect_ratio=decrease"
            )
            filters_for_clip.append(
                f"pad={int(target_width)}:{int(target_height)}:(ow-iw)/2:(oh-ih)/2"
            )
            filters_for_clip.append("setsar=1")
        if target_fps:
            filters_for_clip.append(f"fps={float(target_fps)}")
        filters_for_clip.append("format=yuv420p")
        filters_for_clip.append("setpts=PTS-STARTPTS")
        video_prep_filters.append(f"[{i}:v]" + ",".join(filters_for_clip) + f"[v{i}]")

    if n == 1:
        out: list[str] = list(video_prep_filters)
        out.append("[v0]format=yuv420p[vout]")
        if has_audio is None or has_audio[0]:
            out.append("[0:a]aresample=async=1[aout]")
        else:
            out.append("anullsrc=channel_layout=stereo:sample_rate=44100[aout]")
        return ";".join(out)

    normalized = [_normalize_transition(t) for t in transitions]
    # Cumulative end-time of clip i (before subtracting overlaps).
    # offset for the k-th xfade = (sum of durations so far) - (k * transition_duration)
    # because each prior crossfade already shortened the timeline by transition_duration.
    filters: list[str] = list(video_prep_filters)
    audio_filters: list[str] = []

    # Pad missing audio with anullsrc so acrossfade always has two streams.
    for i in range(n):
        if has_audio is not None and not has_audio[i]:
            filters.append(
                f"[{i}:a]anullsrc=channel_layout=stereo:sample_rate=44100:d={clip_durations[i]:.3f}[a{i}]"
            )

    # Audio prep: rename input audio labels for consistency.
    for i in range(n):
        if has_audio is None or has_audio[i]:
            audio_filters.append(f"[{i}:a]aresample=async=1,asetpts=PTS-STARTPTS[ai{i}]")
        else:
            audio_filters.append(f"[a{i}]asetpts=PTS-STARTPTS[ai{i}]")

    # Chain xfades. prev_label_video / prev_label_audio track the accumulated chain.
    prev_v = "v0"
    prev_a = "ai0"
    accumulated = float(clip_durations[0])
    for i in range(1, n):
        transition = normalized[i]
        # Offset = end-of-chain so far minus transition_duration.
        if transition == "cut":
            # No xfade — concat this clip after the chain.
            new_v = f"vchain{i}"
            new_a = f"achain{i}"
            filters.append(
                f"[{prev_v}][v{i}]concat=n=2:v=1:a=0[{new_v}]"
            )
            audio_filters.append(f"[{prev_a}][ai{i}]concat=n=2:v=0:a=1[{new_a}]")
            prev_v = new_v
            prev_a = new_a
            accumulated += float(clip_durations[i])
        else:
            offset = max(0.0, accumulated - transition_duration)
            new_v = f"vchain{i}"
            new_a = f"achain{i}"
            filters.append(
                f"[{prev_v}][v{i}]xfade=transition={resolved_xfade}:duration={transition_duration:.3f}:offset={offset:.3f}[{new_v}]"
            )
            audio_filters.append(
                f"[{prev_a}][ai{i}]acrossfade=d={transition_duration:.3f}:c1=tri:c2=tri[{new_a}]"
            )
            prev_v = new_v
            prev_a = new_a
            accumulated = offset + float(clip_durations[i])

    filters.extend(audio_filters)
    filters.append(f"[{prev_v}]format=yuv420p[vout]")
    filters.append(f"[{prev_a}]aresample=async=1[aout]")
    return ";".join(filters)


def build_xfade_command(
    ffmpeg_path: str,
    clip_paths: list[str],
    clip_durations: list[float],
    transitions: list[str],
    output_path: str,
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
    has_audio: list[bool] | None = None,
    extra_input_args: list[str] | None = None,
    target_width: int | None = DEFAULT_TARGET_WIDTH,
    target_height: int | None = DEFAULT_TARGET_HEIGHT,
    target_fps: float | None = DEFAULT_TARGET_FPS,
    xfade_type: str = "fade",
) -> list[str]:
    """Assemble the full ffmpeg command for xfade stitching."""
    if len(clip_paths) != len(clip_durations) or len(clip_paths) != len(transitions):
        raise ValueError("clip_paths / clip_durations / transitions length mismatch")
    if not clip_paths:
        raise ValueError("clip_paths is empty")

    cmd: list[str] = [ffmpeg_path, "-y"]
    for path in clip_paths:
        if extra_input_args:
            cmd.extend(extra_input_args)
        cmd.extend(["-i", str(path)])

    filter_complex = build_xfade_filter_chain(
        clip_durations,
        transitions,
        transition_duration,
        has_audio,
        target_width=target_width,
        target_height=target_height,
        target_fps=target_fps,
        xfade_type=xfade_type,
    )
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", "[vout]", "-map", "[aout]"])
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return cmd

REMOTE_PROTOCOL_WHITELIST = "file,http,https,tcp,tls,crypto"
logger = setup_logger("service.video_stitching")


QUALITY_CHECKS = [
    {
        "key": "stream_compatibility",
        "label": "编码/分辨率/帧率一致",
        "status": "manual_review",
        "detail": "concat demuxer使用-c copy，需确认所有Clip的容器、编码参数、分辨率与帧率一致。",
    },
    {
        "key": "audio_continuity",
        "label": "音轨连续性",
        "status": "manual_review",
        "detail": "检查对白、环境声与静音段，避免拼接点音轨缺失或突变。",
    },
    {
        "key": "color_consistency",
        "label": "色彩统一",
        "status": "manual_review",
        "detail": "抽查每个Clip首尾帧，必要时进入调色或重生成流程。",
    },
    {
        "key": "transition_review",
        "label": "转场审查",
        "status": "pass",
        "detail": "xfade+acrossfade 已在拼接点应用 0.4s 交叉淡化；cut 对保留硬切。仅当回退到 concat -c copy 时需人工复核。",
    },
]


def _escape_concat_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace("'", "\\'")


def build_concat_manifest(clips: list[dict[str, Any]]) -> str:
    lines = ["ffconcat version 1.0"]
    for clip in clips:
        lines.append(f"file '{_escape_concat_path(str(clip['video_url']))}'")
    return "\n".join(lines) + "\n"


def _is_remote_video_url(video_url: str) -> bool:
    return urlparse(video_url).scheme in {"http", "https"}


def _local_media_path(video_url: str) -> Path | None:
    if video_url.startswith("/generated/"):
        return media_path_from_url(video_url)
    parsed = urlparse(video_url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).expanduser().resolve()
    candidate = Path(video_url)
    return candidate.expanduser().resolve() if candidate.is_absolute() else None


def _localize_downloaded(downloaded_url: str) -> str:
    """将 download_video_to_local 返回值转为本地文件路径。

    下载成功时返回 /generated/ URL → 转为本地绝对路径供 ffmpeg 使用；
    若仍为远程 URL（下载失败）则抛出清晰错误，由 execute_stitch 转为拼接失败。
    """
    if downloaded_url.startswith("/generated/"):
        return str(media_path_from_url(downloaded_url))
    raise ValueError(f"远程视频下载失败，无法本地化用于拼接：{downloaded_url}")


def _ffmpeg_error_summary(stderr: str, limit: int = 900) -> str:
    detail_lines = []
    for line in stderr.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("ffmpeg version", "built with ", "configuration: ")):
            continue
        detail_lines.append(stripped)
    detail = "\n".join(detail_lines[-12:]) or stderr.strip() or "unknown ffmpeg error"
    return detail[-limit:]


def _has_audio_stream(ffmpeg_path: str, media_path: str) -> bool:
    try:
        return probe_media(media_path, ffmpeg_path=ffmpeg_path).has_audio
    except MediaProbeError:
        logger.warning("Media probe unavailable; skipping audio stream verification")
        return True


def _any_clip_has_audio(ffmpeg_path: str, clips: list[dict[str, Any]]) -> bool:
    for clip in clips:
        video_url = str(clip.get("video_url") or "")
        if video_url and _has_audio_stream(ffmpeg_path, video_url):
            return True
    return False


def _probe_clip_duration_seconds(ffmpeg_path: str, media_path: str) -> float:
    """Probe a clip's duration via ffprobe/ffmpeg; return 0.0 on failure."""
    try:
        return probe_media(
            media_path,
            ffmpeg_path=ffmpeg_path,
        ).duration_seconds or 0.0
    except MediaProbeError:
        return 0.0


def _run_xfade_stitch(
    ffmpeg_path: str,
    clip_paths: list[str],
    clip_durations: list[float],
    transitions: list[str],
    has_audio: list[bool],
    output_path: str,
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
    xfade_type: str = "fade",
) -> Any:
    """Run the xfade+acrossfade ffmpeg command; returns subprocess.CompletedProcess."""
    import subprocess

    cmd = build_xfade_command(
        ffmpeg_path,
        clip_paths,
        clip_durations,
        transitions,
        output_path,
        transition_duration=transition_duration,
        has_audio=has_audio,
        xfade_type=xfade_type,
    )
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def _run_reencode_concat(ffmpeg_path: str, manifest_path: str, output_path: str) -> Any:
    import subprocess

    reencode_cmd = [
        ffmpeg_path,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        manifest_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        output_path,
    ]
    return subprocess.run(reencode_cmd, capture_output=True, text=True, timeout=600)


def _safe_output_filename(output_path: str) -> str:
    from pathlib import Path

    name = Path(output_path or "episode.mp4").name
    if not name or name in {".", ".."}:
        name = "episode.mp4"
    if not Path(name).suffix:
        name = f"{name}.mp4"
    return name


def _runtime_concat_command(
    command: list[str],
    *,
    manifest_path: str,
    output_path: str,
) -> list[str]:
    """Bind plan placeholders to Task-scoped paths without trusting raw names.

    ``build_stitch_plan`` intentionally exposes only a safe basename as the
    command's final argument.  The public compose request may carry a logical
    path such as ``post/final/rendered-video.mp4``; comparing the basename to
    that raw value leaves ffmpeg writing into the server's current directory.
    The output argument is structurally the final command item, so replace it
    by position and keep every runtime write under ``CREATOR_DATA_ROOT``.
    """

    if not command:
        raise ValueError("FFmpeg concat command is empty")
    localized = [manifest_path if arg == "concat.txt" else arg for arg in command]
    localized[-1] = output_path
    return localized


def build_agent_review_notes(ordered_clips: list[dict[str, Any]], uses_remote_sources: bool) -> list[dict[str, str]]:
    notes = [
        {
            "key": "transition_pairs",
            "label": "相邻Clip转场对",
            "detail": f"逐对审查{max(0, len(ordered_clips) - 1)}个拼接点，检查尾帧动作、视线方向与剧情时间是否连续。",
        },
        {
            "key": "color_sampling",
            "label": "首尾帧抽样",
            "detail": f"对{len(ordered_clips)}个Clip抽取首帧/尾帧，标记曝光、白平衡和主色调突变。",
        },
    ]
    if uses_remote_sources:
        notes.append({
            "key": "remote_cache",
            "label": "远程结果缓存",
            "detail": "R2V结果为HTTP(S)地址，执行FFmpeg前建议落本地缓存并校验文件完整性。",
        })
    if len(ordered_clips) > 1:
        notes.append({
            "key": "semantic_bridge",
            "label": "语义转场补写",
            "detail": "若硬切不成立，Agent应基于前后Clip剧情进度补写转场提示或要求重生成边界Clip。",
        })
    return notes


def execute_stitch(
    project_id: str,
    clips: list[dict[str, Any]],
    output_path: str = "episode.mp4",
    transition_duration: float | None = None,
    xfade_type: str = "fade",
    task_id: str | None = None,
) -> dict[str, Any]:
    """Execute FFmpeg stitching for given clips. Returns result with output_url.

    `transition_duration` overrides the default 0.4s crossfade length (None = default).
    `xfade_type` selects the xfade transition (fade/fadeblack/fadewhite/dissolve/wipeleft).
    """
    import subprocess
    import uuid

    effective_transition_duration = (
        DEFAULT_TRANSITION_DURATION if transition_duration is None
        else max(0.0, float(transition_duration))
    )
    plan = build_stitch_plan(clips, output_path)
    if not plan["can_stitch"]:
        return {"success": False, "error": "Cannot stitch: " + "; ".join(plan["blockers"]), "output_url": None}

    try:
        output_filename = _safe_output_filename(output_path)
        work_dir = ensure_task_work_subdir("stitches", uuid.uuid4().hex, task_id=task_id)
        local_clips = []
        downloaded_urls = {}  # unit_id -> local_url

        for index, clip in enumerate(sorted(clips, key=lambda item: item.get("order", 0)), start=1):
            video_url = str(clip.get("video_url") or "")
            remote_url = str(clip.get("remote_video_url") or "")
            clip_id = clip.get("id") or f"clip_{index:03d}"

            # Canonical Blob/Artifact URLs and compatibility preview URLs are
            # resolved to local paths before invoking ffmpeg.
            local_path = _local_media_path(video_url)
            if local_path is not None:
                if local_path.exists() and local_path.stat().st_size > 0:
                    local_url = str(local_path)
                elif remote_url:
                    downloaded_url = download_video_to_local(
                        project_id,
                        clip_id,
                        remote_url,
                        clip_id,
                        force=True,
                        task_id=task_id,
                    )
                    downloaded_urls[clip_id] = downloaded_url
                    local_url = _localize_downloaded(downloaded_url)
                else:
                    local_url = video_url
            elif _is_remote_video_url(video_url):
                # video_url 本身就是远程 URL
                if remote_url:
                    # 有备用远程 URL，下载
                    downloaded_url = download_video_to_local(
                        project_id,
                        clip_id,
                        remote_url,
                        clip_id,
                        force=True,
                        task_id=task_id,
                    )
                else:
                    # 没有备用远程 URL，使用当前远程 URL 下载
                    downloaded_url = download_video_to_local(
                        project_id,
                        clip_id,
                        video_url,
                        clip_id,
                        force=True,
                        task_id=task_id,
                    )
                downloaded_urls[clip_id] = downloaded_url
                # 转换为本地路径
                local_url = _localize_downloaded(downloaded_url)
            else:
                # 其他情况，直接使用原始 URL
                local_url = video_url

            local_clips.append({**clip, "video_url": local_url})

        plan = build_stitch_plan(local_clips, output_path)
        if not plan["can_stitch"]:
            return {"success": False, "error": "Cannot stitch cached clips: " + "; ".join(plan["blockers"]), "output_url": None}

        manifest_path = str(work_dir / "concat.txt")
        out_path = str(work_dir / output_filename)

        ffmpeg_ready = ffmpeg_readiness()
        ffmpeg_path = ffmpeg_ready["path"] or ffmpeg_ready["binary"]

        # Decide transition strategy. xfade is preferred whenever any pair wants
        # a crossfade; pure-cut timelines still take the fast -c copy path.
        ordered_local = sorted(local_clips, key=lambda item: item.get("order", 0))
        transitions = [str(clip.get("transition") or "fade").lower() or "fade" for clip in ordered_local]
        # transitions[0] describes the (non-existent) pair before clip 0 — force cut.
        if transitions:
            transitions[0] = "cut"
        all_cuts = all(t == "cut" for t in transitions)
        # transition_duration=0 表示用户选择硬切，走 concat 路径而非 duration=0 的 xfade。
        use_xfade = (
            plan["can_stitch"]
            and len(ordered_local) > 1
            and not all_cuts
            and effective_transition_duration > 0
        )

        if use_xfade:
            xfade_out_path = str(work_dir / f"xfade-{output_filename}")
            clip_paths = [str(clip.get("video_url")) for clip in ordered_local]
            clip_durations = [
                _probe_clip_duration_seconds(ffmpeg_path, p) or 1.0 for p in clip_paths
            ]
            has_audio = [_has_audio_stream(ffmpeg_path, p) for p in clip_paths]
            xfade_result = _run_xfade_stitch(
                ffmpeg_path,
                clip_paths,
                clip_durations,
                transitions,
                has_audio,
                xfade_out_path,
                transition_duration=effective_transition_duration,
                xfade_type=xfade_type,
            )
            if xfade_result.returncode == 0:
                out_path = xfade_out_path
                plan["strategy"] = "ffmpeg_xfade_acrossfade"
            else:
                logger.warning(
                    "xfade stitch failed, falling back to reencode concat: %s",
                    _ffmpeg_error_summary(xfade_result.stderr, 300),
                )
                # Fall through to the concat demuxer path below.
                with open(manifest_path, "w") as f:
                    f.write(plan["manifest"])
                cmd = _runtime_concat_command(
                    list(plan["command"]),
                    manifest_path=manifest_path,
                    output_path=out_path,
                )
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    logger.warning(f"FFmpeg stream-copy stitch failed, retrying with re-encode: {_ffmpeg_error_summary(result.stderr, 300)}")
                    reencoded_out_path = str(work_dir / f"reencoded-{output_filename}")
                    result = _run_reencode_concat(ffmpeg_path, manifest_path, reencoded_out_path)
                    if result.returncode != 0:
                        return {"success": False, "error": f"FFmpeg failed: {_ffmpeg_error_summary(result.stderr)}", "output_url": None}
                    out_path = reencoded_out_path
        else:
            with open(manifest_path, "w") as f:
                f.write(plan["manifest"])

            cmd = _runtime_concat_command(
                list(plan["command"]),
                manifest_path=manifest_path,
                output_path=out_path,
            )

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.warning(f"FFmpeg stream-copy stitch failed, retrying with re-encode: {_ffmpeg_error_summary(result.stderr, 300)}")
                reencoded_out_path = str(work_dir / f"reencoded-{output_filename}")
                result = _run_reencode_concat(cmd[0], manifest_path, reencoded_out_path)
                if result.returncode != 0:
                    return {"success": False, "error": f"FFmpeg failed: {_ffmpeg_error_summary(result.stderr)}", "output_url": None}
                out_path = reencoded_out_path

        source_has_audio = _any_clip_has_audio(ffmpeg_path, local_clips)
        output_has_audio = _has_audio_stream(ffmpeg_path, out_path)
        if source_has_audio and not output_has_audio:
            logger.warning("Stitched output has no audio stream while source clips do; retrying with explicit audio map")
            reencoded_out_path = str(work_dir / f"audio-fixed-{output_filename}")
            result = _run_reencode_concat(ffmpeg_path, manifest_path, reencoded_out_path)
            if result.returncode != 0:
                return {"success": False, "error": f"FFmpeg audio-preserving retry failed: {_ffmpeg_error_summary(result.stderr)}", "output_url": None}
            out_path = reencoded_out_path
            if not _has_audio_stream(ffmpeg_path, out_path):
                return {
                    "success": False,
                    "error": "FFmpeg stitched output still has no audio stream after audio-preserving retry.",
                    "output_url": None,
                }

        return {
            "success": True,
            "error": None,
            "output_url": media_url_for(Path(out_path)),
            "output_path": str(Path(out_path).resolve()),
            "work_dir": str(work_dir.resolve()),
            "downloaded_clips": downloaded_urls,  # unit_id -> local_url
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "FFmpeg execution timed out (300s)", "output_url": None}
    except Exception as e:
        return {"success": False, "error": str(e), "output_url": None}


def build_stitch_plan(clips: list[dict[str, Any]], output_path: str = "episode.mp4") -> dict[str, Any]:
    ordered_clips = sorted(clips, key=lambda clip: clip.get("order", 0))
    output_filename = _safe_output_filename(output_path)
    blockers: list[str] = []
    ordered_clip_ids = [str(clip.get("id") or f"clip-{index}") for index, clip in enumerate(ordered_clips, start=1)]
    ffmpeg = ffmpeg_readiness()

    if not ordered_clips:
        blockers.append("缺少可拼接Clip。")

    orders = [clip.get("order") for clip in ordered_clips]
    duplicate_orders = sorted({order for order in orders if orders.count(order) > 1})
    if duplicate_orders:
        blockers.append(f"Clip顺序重复: {', '.join(str(order) for order in duplicate_orders)}。")

    expected_orders = list(range(1, len(ordered_clips) + 1))
    if ordered_clips and orders != expected_orders:
        blockers.append(
            f"Clip顺序必须从1连续排列；当前顺序为 {', '.join(str(order) for order in orders)}。"
        )
    if ffmpeg["status"] != "ok":
        blockers.extend(ffmpeg["blockers"])

    for index, clip in enumerate(ordered_clips, start=1):
        video_url = str(clip.get("video_url") or "").strip()
        if not video_url:
            clip_id = clip.get("id") or f"clip-{index}"
            task_id = str(clip.get("task_id") or "").strip()
            if task_id:
                blockers.append(f"{clip_id} 仍在生成任务 {task_id}，等待 video_url 回填。")
            else:
                blockers.append(f"{clip_id} 缺少视频结果，尚未提交R2V生成。")

    can_stitch = len(blockers) == 0
    uses_remote_sources = any(_is_remote_video_url(str(clip.get("video_url") or "")) for clip in ordered_clips)
    # Per-pair transition field: transitions[i] describes the pair (i-1, i).
    # transitions[0] is forced to "cut" (no pair before clip 0).
    transitions = [str(clip.get("transition") or "fade").lower() or "fade" for clip in ordered_clips]
    if transitions:
        transitions[0] = "cut"
    any_xfade = any(t != "cut" for t in transitions)
    transition_strategy = "ffmpeg_xfade_acrossfade" if (can_stitch and len(ordered_clips) > 1 and any_xfade) else "ffmpeg_concat_demuxer_copy"
    manifest = build_concat_manifest(ordered_clips) if can_stitch else ""
    command = [
        ffmpeg["path"] or ffmpeg["binary"],
        "-f",
        "concat",
        "-safe",
        "0",
    ]
    if uses_remote_sources:
        command.extend(["-protocol_whitelist", REMOTE_PROTOCOL_WHITELIST])
    command.extend([
        "-i",
        "concat.txt",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        output_filename,
    ])

    return {
        "can_stitch": can_stitch,
        "strategy": transition_strategy if can_stitch else "blocked",
        "transition_pairs": transitions if can_stitch else [],
        "blockers": blockers,
        "manifest": manifest,
        "command": command if can_stitch else [],
        "ordered_clip_ids": ordered_clip_ids,
        "runtime_readiness": {
            "ffmpeg": ffmpeg,
        },
        "uses_remote_sources": uses_remote_sources if can_stitch else False,
        "protocol_whitelist": REMOTE_PROTOCOL_WHITELIST if can_stitch and uses_remote_sources else "",
        "quality_checks": QUALITY_CHECKS if can_stitch else [],
        "agent_review_notes": build_agent_review_notes(ordered_clips, uses_remote_sources) if can_stitch else [],
    }
