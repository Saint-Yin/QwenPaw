"""Speech boundary analysis for source-footage editing.

Wraps the Whisper CLI to produce sentence-level timestamps that the editing
pipeline snaps cut points to, so a clip doesn't land mid-utterance.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from services.workspace.content_store import atomic_replace_bytes
from utils.logger import setup_logger
from utils.paths import ensure_preview_subdir

logger = setup_logger("services.media.ai_edit.audio_segments")

WHISPER_BIN_CANDIDATES = (
    "whisper",
)
WHISPER_TIMEOUT_SECONDS = 600
DEFAULT_TOLERANCE_SECONDS = 1.5


def _resolve_whisper_binary() -> str | None:
    for candidate in WHISPER_BIN_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _cache_key(media_path: Path) -> str:
    stat = media_path.stat()
    fingerprint = f"{media_path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return ensure_preview_subdir("audio_analysis") / f"{key}.json"


def _read_cache(key: str) -> list[dict[str, Any]] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        logger.warning("audio_segments cache read failed: %s", path)
    return None


def _write_cache(key: str, segments: list[dict[str, Any]]) -> None:
    path = _cache_path(key)
    try:
        atomic_replace_bytes(path, json.dumps(segments, ensure_ascii=False).encode("utf-8"))
    except OSError as error:
        logger.warning("audio_segments cache write failed: %s (%s)", path, error)


def _run_whisper(binary: str, media_path: Path) -> list[dict[str, Any]]:
    cmd = [
        binary,
        str(media_path),
        "--task",
        "transcribe",
        "--output_format",
        "json",
        "--output_dir",
        "-",
        "--verbose",
        "False",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=WHISPER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Whisper timed out after %ss on %s", WHISPER_TIMEOUT_SECONDS, media_path)
        return []
    if result.returncode != 0:
        logger.warning(
            "Whisper failed rc=%d stderr=%s",
            result.returncode,
            (result.stderr or "")[-400:],
        )
        return []

    # Whisper prints JSON to stdout when output_dir is "-" on most builds; fall
    # back to parsing any JSON-looking blob if the stdout path doesn't yield.
    payload: dict[str, Any] | None = None
    if result.stdout:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
    if payload is None:
        # Some builds write "<stem>.json" next to the source; check there.
        sibling = media_path.with_suffix(".json")
        if sibling.exists():
            try:
                payload = json.loads(sibling.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
    if not payload:
        logger.warning("Whisper produced no parseable JSON for %s", media_path)
        return []

    raw_segments = payload.get("segments") or []
    parsed: list[dict[str, Any]] = []
    for item in raw_segments:
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        parsed.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": str(item.get("text", "")).strip(),
            }
        )
    return parsed


def analyze_speech_boundaries(media_path: str) -> list[dict[str, Any]]:
    """Return Whisper sentence segments for a media file, with on-disk cache.

    Returns an empty list when Whisper is unavailable or the file has no
    speech — callers should treat that as "no constraint" and fall back to
    the original cut logic.
    """
    path = Path(media_path)
    if not path.exists():
        logger.warning("analyze_speech_boundaries: missing file %s", media_path)
        return []

    key = _cache_key(path)
    cached = _read_cache(key)
    if cached is not None:
        return cached

    binary = _resolve_whisper_binary()
    if not binary:
        logger.warning("Whisper CLI not found; skipping speech boundary analysis for %s", media_path)
        return []

    segments = _run_whisper(binary, path)
    _write_cache(key, segments)
    return segments


def find_nearest_sentence_boundary(
    timestamp: float,
    segments: list[dict[str, Any]],
    tolerance: float = DEFAULT_TOLERANCE_SECONDS,
    prefer_end: bool = True,
) -> float | None:
    """Snap a timestamp to the nearest sentence boundary in the safe direction.

    ``prefer_end=True`` (clip end): finds the nearest sentence end **>=
    timestamp** within *tolerance* so the clip always includes complete
    speech.  Returns ``None`` when no later end exists within tolerance,
    letting the caller fall back to a broader search.

    ``prefer_end=False`` (clip start): finds the nearest sentence start
    **<= timestamp** within *tolerance* so the clip always includes
    complete speech.  Returns ``None`` when no earlier start exists within
    tolerance.
    """
    if not segments:
        return None

    if prefer_end:
        best: tuple[float, float] | None = None
        for seg in segments:
            candidate = float(seg["end"])
            if candidate < timestamp:
                continue
            distance = candidate - timestamp
            if distance > tolerance:
                continue
            if best is None or distance < best[0]:
                best = (distance, candidate)
        return best[1] if best is not None else None
    else:
        best = None
        for seg in segments:
            candidate = float(seg["start"])
            if candidate > timestamp:
                continue
            distance = timestamp - candidate
            if distance > tolerance:
                continue
            if best is None or distance < best[0]:
                best = (distance, candidate)
        return best[1] if best is not None else None


def find_enclosing_sentence_boundaries(
    start: float,
    end: float,
    segments: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    """Find sentence boundaries that enclose the given time range.

    Returns ``(snap_start, snap_end)`` where ``snap_start`` is the latest
    sentence start <= ``start`` and ``snap_end`` is the earliest sentence
    end >= ``end``.  Either value is ``None`` when no suitable boundary
    exists, letting the caller keep the original timestamp for that side.
    """
    if not segments:
        return None, None

    snap_start: float | None = None
    snap_end: float | None = None
    for seg in segments:
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        if seg_start <= start + 0.001:
            if snap_start is None or seg_start > snap_start:
                snap_start = seg_start
        if seg_end >= end - 0.001:
            if snap_end is None or seg_end < snap_end:
                snap_end = seg_end
    return snap_start, snap_end
