# -*- coding: utf-8 -*-
"""Whole-piece cover poster inputs and helpers for interactive bundles.

The platform lists interactive works from a static cover image; unlike the
local player it never runs ``index.html``, so it cannot grab the entry
segment's first frame at runtime. The cover therefore ships inside the exported
ZIP as ``cover.jpg``.

Generation is a project-level task (see ``cover_execution``): it renders a 16:9
text-to-image poster from the story and persists it on the project. At export
we only read that stored poster; if it has not been produced yet we fall back
to a single frame pulled from the entry segment so the bundle essentially
always carries a cover.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

#: The poster is always landscape, whatever the video's own aspect ratio is.
COVER_ASPECT_RATIO = "16:9"
COVER_FILENAME = "cover.jpg"
#: Mirror the interaction base-frame cap; oversized posters are rejected.
COVER_LIMIT_BYTES = 8 * 1024 * 1024
#: Skip the very start of a clip, which is often a fade-from-black.
_COVER_SEEK_SECONDS = 1.0

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_FINGERPRINT_MARKER = "input_fingerprint="


def cover_input_fingerprint(project: Any) -> str:
    """Hash the inputs that decide the poster, driving staleness."""

    raw = json.dumps(
        {
            "name": project.name,
            "description": project.description,
            "brief": project.strategy.creative_brief,
            "style": project.visual.style,
            "bible": project.visual.visual_bible,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def cover_is_current(project: Any) -> bool:
    """Whether a stored cover exists and still matches the current inputs."""

    presentation = project.interactive_presentation
    return bool(
        presentation.cover_file_id
        and presentation.cover_checksum
        and presentation.cover_fingerprint
        == _FINGERPRINT_MARKER + cover_input_fingerprint(project),
    )


def cover_design_notes(project: Any) -> str:
    return (
        "Agent-authored whole-piece cover\n"
        f"{_FINGERPRINT_MARKER}{cover_input_fingerprint(project)}"
    )


def build_cover_prompt(project: Any) -> str:
    """A landscape key-art brief drawn from the story, not a template."""

    brief = (
        project.strategy.creative_brief or project.description or ""
    ).strip()
    style = (project.visual.style or "").strip()
    lines = [
        f"为互动短剧《{project.name}》设计一张横版宣传海报（key art）。",
        "构图横向 16:9，主体清晰、留白可放标题，电影质感。",
    ]
    if brief:
        lines.append(f"故事基调：{brief}")
    if style:
        lines.append(f"视觉风格：{style}")
    return "\n".join(lines)


async def render_cover_bytes(project: Any) -> bytes:
    """Render a 16:9 poster with the configured image model and return bytes.

    Raises on any failure so the caller can record a durable task error; a
    missing cover never reaches the export path unannounced. Provider imports
    stay lazy so read-only paths never load the image backends.
    """

    from models.image import generate_image
    from utils.paths import media_path_from_url, media_task_scope

    prompt = build_cover_prompt(project)
    with media_task_scope(f"cover-{uuid4().hex[:16]}", project_id=None):
        result = await generate_image(
            prompt,
            aspect_ratio=COVER_ASPECT_RATIO,
        )
    url = result["url"] if isinstance(result, dict) else result
    payload = media_path_from_url(url).read_bytes()
    if not payload or not _looks_like_image(payload):
        raise ValueError("封面生成结果不是有效图片")
    jpeg = _to_jpeg(payload, _suffix_for(payload))
    final = jpeg or payload
    if len(final) > COVER_LIMIT_BYTES:
        raise ValueError(
            f"封面超过 {COVER_LIMIT_BYTES} 字节上限",
        )
    return final


def poster_frame_from_video(video_bytes: bytes) -> bytes | None:
    """Extract one landscape frame from the entry cut as a cover fallback."""

    if not video_bytes:
        return None
    frame = _run_ffmpeg_frame(video_bytes, ".mp4", seek=_COVER_SEEK_SECONDS)
    if frame and len(frame) <= COVER_LIMIT_BYTES:
        return frame
    return None


def _looks_like_image(payload: bytes) -> bool:
    return payload.startswith(_JPEG_MAGIC) or payload.startswith(_PNG_MAGIC)


def _suffix_for(payload: bytes) -> str:
    return ".png" if payload.startswith(_PNG_MAGIC) else ".img"


def _to_jpeg(payload: bytes, suffix: str) -> bytes | None:
    """Re-encode a PNG poster so ``cover.jpg`` matches its name."""

    return _run_ffmpeg_frame(payload, suffix, seek=0.0)


def _run_ffmpeg_frame(
    payload: bytes,
    suffix: str,
    *,
    seek: float,
) -> bytes | None:
    from services.runtime_files.runtime_dependencies import resolve_ffmpeg

    executable = resolve_ffmpeg()
    if not executable:
        logger.info("未找到 ffmpeg，跳过封面转码/抽帧")
        return None
    with tempfile.TemporaryDirectory(prefix="creator-cover-") as tmp:
        source = Path(tmp) / f"source{suffix or '.img'}"
        output = Path(tmp) / "cover.jpg"
        source.write_bytes(payload)
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
        ]
        if seek > 0:
            command += ["-ss", f"{seek}"]
        command += [
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output),
        ]
        try:
            subprocess.run(  # noqa: S603
                command,
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            logger.info("ffmpeg 抽帧失败：%s", exc)
            return None
        if not output.is_file():
            return None
        return output.read_bytes()


__all__ = [
    "COVER_ASPECT_RATIO",
    "COVER_FILENAME",
    "COVER_LIMIT_BYTES",
    "build_cover_prompt",
    "cover_design_notes",
    "cover_input_fingerprint",
    "cover_is_current",
    "poster_frame_from_video",
    "render_cover_bytes",
]
