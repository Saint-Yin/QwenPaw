# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Adjacent-segment continuity anchors for R2V / I2V video generation.

Short dramas split their storyline into several R2V / I2V Elements. Each
Element is generated independently by the video provider, so the seam
between two adjacent clips drifts in pose, camera and background audio.
This module extracts two ephemeral artifacts from the predecessor's
published video:

* the last visible PNG frame, used as an additional ``reference_image``
  (or as the strict ``first_frame`` on I2V Elements without an authored
  first frame); and
* a 3-second tail clip with its audio track preserved, used as a Wan3.0
  ``reference_video`` in the "视频延长" task route.

The tail clip is only attached when the configured model documents
video extension. For every other model the executor falls back to
last-frame image continuity alone. Nothing here is persisted into the
Project Asset Index — extracts live under ``runtime/continuity/<hash>/``
and are cached per-process keyed by the predecessor's selected version,
so sibling dispatches of the same segment do not re-cut.
"""

from __future__ import annotations

from collections.abc import Callable
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any, Literal

from domain.errors import ValidationError
from services.project_files.models import (
    I2VCreation,
    Project,
    R2VCreation,
    Timeline,
    TimelineElement,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)

_CONTINUITY_ROOT = Path("runtime") / "continuity"
_TAIL_CLIP_SECONDS = 3.0
_CACHE_MAX_ITEMS = 64
# Disk-side GC grace: an entry evicted from the in-memory cache may still
# be mid-upload for an in-flight submit; only directories quiet for this
# long are collected.
_PRUNE_GRACE_SECONDS = 30 * 60
# In-flight anchor registry: extract registers the predecessor digest its
# result was frozen into a task payload with; the event-driven prune keeps
# registered digests so a QUEUED render older than the grace window (and
# evicted from the 64-entry cache by busier predecessors) cannot have its
# file:// anchors deleted underneath it by another extract in the same
# process. Entries expire on their own TTL instead of task-terminal
# hooks: extract does not know the Task id, and a bounded TTL keeps the
# registry from pinning directories forever.
_INFLIGHT_TTL_SECONDS = 6 * 60 * 60
_INFLIGHT_MAX_ITEMS = 512
# ffmpeg -sseof seeks relative to the container end; the epsilon keeps the
# probe off the last GOP boundary on VFR sources without drifting back a
# full second.
_LAST_FRAME_SEEK_OFFSET = -0.1
_FFMPEG_TIMEOUT_SECONDS = 120
_FFPROBE_TIMEOUT_SECONDS = 30
_VIDEO_CONTINUATION_CREATIONS = (R2VCreation, I2VCreation)

# Operator-side dial for the tail-clip channel. Empirically the Wan3.0
# "视频延长" path constrains generation harder than a plain still anchor,
# so some runs look worse with the tail clip than with the last frame
# alone. Setting CREATOR_CONTINUITY_TAIL_CLIP=0 demotes R2V to image-only
# continuity — the exact path non-continuation models already take — with
# no code change and no loss of segment linkage. On by default.
CONTINUITY_TAIL_CLIP_ENV = "CREATOR_CONTINUITY_TAIL_CLIP"
_TAIL_CLIP_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


def tail_clip_enabled() -> bool:
    """Whether R2V continuity may ship the predecessor's tail clip video.

    On unless ``CREATOR_CONTINUITY_TAIL_CLIP`` is set to a disabled value.
    This gates only the *tail clip*; the last-frame image anchor and the
    whole continuity concept stay active either way, so turning it off
    never drops linkage — it just stops using the "视频延长" request shape.
    """

    raw = os.environ.get(CONTINUITY_TAIL_CLIP_ENV, "")
    return raw.strip().casefold() not in _TAIL_CLIP_DISABLED_VALUES


_continuity_cache: "OrderedDict[tuple[str, str, bool], ContinuityBundle]" = (
    OrderedDict()
)
_continuity_cache_lock = threading.Lock()
# Per-key extraction locks let two schedulers racing for the same
# predecessor share one ffmpeg run instead of both writing to
# last_frame.png / tail_clip.mp4 concurrently. A third caller that
# arrives while a lock is held blocks briefly, then sees the cached
# bundle in the double-check below. Cache hits move the key to the
# MRU end so eviction retires the least recently *used* bundle, not
# merely the oldest inserted one.
_continuity_extract_locks: dict[tuple[str, str, bool], threading.Lock] = {}
_continuity_locks_guard = threading.Lock()
# digest -> expire_at epoch seconds, see _INFLIGHT_TTL_SECONDS.
_continuity_inflight: dict[str, float] = {}
_inflight_lock = threading.Lock()


def _register_inflight_digest(digest: str) -> None:
    """Mark one extract digest as referenced by work that may not be
    terminal yet; expired and over-cap entries are dropped here lazily."""

    now = time.time()
    with _inflight_lock:
        for stale in [k for k, v in _continuity_inflight.items() if v <= now]:
            del _continuity_inflight[stale]
        _continuity_inflight[digest] = now + _INFLIGHT_TTL_SECONDS
        while len(_continuity_inflight) > _INFLIGHT_MAX_ITEMS:
            oldest = min(_continuity_inflight, key=_continuity_inflight.get)
            del _continuity_inflight[oldest]


def _inflight_keep(now: float) -> set[str]:
    with _inflight_lock:
        return {k for k, v in _continuity_inflight.items() if v > now}


@dataclass(frozen=True, slots=True)
class ContinuityEntry:
    """One extract ready to be appended to the submit-time reference list.

    ``reference_id`` is a synthetic string (never an Asset Index version)
    that participates in ``input_refs`` and the dispatch fingerprint: a
    predecessor reroll re-qualifies parked FAILED successors for a fresh
    dispatch and invalidates in-flight submission claims, while already
    completed artifacts conservatively keep their selected version (no
    automatic paid cascade). ``media_type`` is the ``image/*`` / ``video/*``
    prefix the budget checker uses to bucket the entry alongside real
    project references. ``duration_seconds`` is only meaningful for the
    tail clip; the Wan3.0 input+output duration check consumes it because
    synthetic IDs never resolve through the Asset Index.
    """

    kind: Literal["last_frame", "tail_clip"]
    reference_id: str
    url: str
    checksum: str
    path: Path
    role_label: str
    provenance_ref: str
    media_type: str
    duration_seconds: float | None = None

    def as_read_entry(self) -> dict[str, Any]:
        """Read-set entry in the established non-indexed reference shape.

        ``fileId`` is ``None`` by the same convention as remote-URL
        references in ``_resolve_reference_versions`` and
        ``local_execution._read_set_item``: the extract is a real local
        file but never an Asset Index entry, so there is no indexed
        file id to cite. ``sourceUrl`` carries the ``file://`` URI the
        submit path actually reads, mirroring the remote-URL branch
        that also pairs ``fileId=None`` with a ``sourceUrl``.
        """

        return {
            "ref": self.provenance_ref,
            "versionId": self.reference_id,
            "fileId": None,
            "checksum": self.checksum,
            "sourceUrl": self.url,
        }


@dataclass(frozen=True, slots=True)
class ContinuityBundle:
    predecessor_element_id: str
    predecessor_video_version_id: str
    entries: tuple[ContinuityEntry, ...]

    def ids(self) -> tuple[str, ...]:
        return tuple(entry.reference_id for entry in self.entries)

    def entry(
        self,
        kind: Literal["last_frame", "tail_clip"],
    ) -> ContinuityEntry | None:
        for candidate in self.entries:
            if candidate.kind == kind:
                return candidate
        return None


def find_predecessor_video_element(
    timeline: Timeline,
    element: TimelineElement,
) -> TimelineElement | None:
    """Return the closest earlier video Element on the same timeline.

    Only R2V / I2V Elements count as video predecessors — T2V / S2V /
    overlay / audio Elements do not produce a real clip whose tail can
    anchor the next segment, and Elements marked ``enabled=False`` are
    skipped entirely. Candidates must have a strictly smaller
    ``start_tick``; two Elements starting at the same tick are treated
    as parallel siblings rather than chained neighbours, which keeps
    this lookup aligned with work_graph's own predecessor check.
    A candidate still playing when the target starts (its end tick
    overlaps the target's start) is skipped too: its last frame happens
    *after* this segment opens, so anchoring on it would tie the seam
    to a frame that has not occurred yet. When two candidates tie on
    tick, the largest ``element_id`` wins so the pick follows the same
    ``(tick, element_id)`` ordering the scheduler iterates in.
    """

    target_tick = int(element.span.start_tick)
    best_key: tuple[int, str] | None = None
    best: TimelineElement | None = None
    for candidate_id, candidate in timeline.elements_by_id.items():
        if candidate_id == element.element_id:
            continue
        if not candidate.enabled:
            continue
        if not isinstance(candidate.creation, _VIDEO_CONTINUATION_CREATIONS):
            continue
        tick = int(candidate.span.start_tick)
        if tick >= target_tick:
            continue
        if tick + int(candidate.span.duration_tick) > target_tick:
            continue
        key = (tick, candidate_id)
        if best_key is None or key > best_key:
            best_key = key
            best = candidate
    return best


def resolve_predecessor_video_version(
    project: Project,
    prev_element: TimelineElement,
) -> str | None:
    """Return the selected video version of ``prev_element`` if published."""

    slot = project.assets.artifact_slots_by_id.get(
        f"element:{prev_element.element_id}:main",
    )
    if slot is None:
        return None
    return slot.selected_version_id


def _last_frame_reference_id(prev_version: str) -> str:
    return f"continuity:last_frame:{prev_version}"


def _tail_clip_reference_id(prev_version: str) -> str:
    return f"continuity:tail_clip:{prev_version}"


def continuity_reference_ids(
    project: Project,
    timeline: Timeline,
    element: TimelineElement,
) -> tuple[str, ...]:
    """Stable synthetic IDs for fingerprint / ``input_refs`` comparison.

    Both IDs are listed regardless of the runtime model capability. That
    is deliberate and adds no extra drift: the tail clip ID carries the
    same version token as the last frame ID, so a predecessor reroll
    shifts both together or neither. And on non-continuation models the
    last frame still ships (as the image anchor) — only budget skips and
    missing ffmpeg drop anchors entirely, and the submit path excludes
    those never-injected IDs from the claim fingerprint by following the
    frozen payload. The submit path decides which of the two actually
    leaves the machine.
    """

    prev = find_predecessor_video_element(timeline, element)
    if prev is None:
        return ()
    prev_version = resolve_predecessor_video_version(project, prev)
    if not prev_version:
        return ()
    return (
        _last_frame_reference_id(prev_version),
        _tail_clip_reference_id(prev_version),
    )


def _resolve_prev_video_path(
    project: Project,
    project_root: Path,
    prev_version_id: str,
) -> Path:
    from services.media_files.r2v_execution import _indexed_path

    artifact = project.assets.artifact_versions_by_id.get(prev_version_id)
    if artifact is None:
        raise ValidationError(
            f"上一段视频 ArtifactVersion 不存在: {prev_version_id}",
        )
    indexed = project.assets.files_by_id.get(artifact.file_id)
    if indexed is None:
        raise ValidationError(
            f"上一段视频缺少 IndexedFile: {prev_version_id}",
        )
    return _indexed_path(project_root, indexed)


def _digest_for(prev_version_id: str) -> str:
    return hashlib.sha256(prev_version_id.encode("utf-8")).hexdigest()[:16]


def _work_dir_for(project_root: Path, prev_version_id: str) -> Path:
    root = project_root / _CONTINUITY_ROOT / _digest_for(prev_version_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run(
    cmd: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    # Converge every subprocess-layer failure into RuntimeError so the
    # module's single documented failure mode holds: callers treat
    # RuntimeError as "skip continuity, keep generating". Without this,
    # a hung ffmpeg (TimeoutExpired) or an unexecutable binary (OSError)
    # would escape the best-effort catches and hard-fail a paid render.
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.SubprocessError as error:
        raise RuntimeError(f"ffmpeg/ffprobe 调用失败: {error}") from error
    except OSError as error:
        raise RuntimeError(f"ffmpeg/ffprobe 无法执行: {error}") from error


def _extract_last_frame(
    source: Path,
    out_path: Path,
    ffmpeg_path: str,
) -> None:
    result = _run(
        [
            ffmpeg_path,
            "-y",
            "-sseof",
            f"{_LAST_FRAME_SEEK_OFFSET}",
            "-i",
            os.fspath(source),
            "-map",
            "v:0",
            "-frames:v",
            "1",
            "-update",
            "1",
            os.fspath(out_path),
        ],
        timeout=_FFMPEG_TIMEOUT_SECONDS,
    )
    if result.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            "末帧抽取失败: "
            + (result.stderr.strip()[:400] or result.stdout.strip()[:400]),
        )


def _probe_duration(source: Path, ffprobe_path: str) -> float:
    result = _run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            os.fspath(source),
        ],
        timeout=_FFPROBE_TIMEOUT_SECONDS,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _extract_tail_clip(
    source: Path,
    out_path: Path,
    ffmpeg_path: str,
    *,
    tail_seconds: float,
    total_duration: float,
) -> None:
    if total_duration > 0:
        start = max(0.0, total_duration - tail_seconds)
        seek_args = ["-ss", f"{start:.6f}"]
    else:
        # ffprobe could not read a duration: seek relative to the
        # container end so the cut is still the TAIL. An absolute
        # ``-ss 0`` fallback would silently anchor the successor on
        # the predecessor's OPENING frames instead of its ending.
        seek_args = ["-sseof", f"-{tail_seconds:.6f}"]
    stream_copy = _run(
        [
            ffmpeg_path,
            "-y",
            *seek_args,
            "-i",
            os.fspath(source),
            "-t",
            f"{tail_seconds:.6f}",
            "-c",
            "copy",
            os.fspath(out_path),
        ],
        timeout=_FFMPEG_TIMEOUT_SECONDS,
    )
    if stream_copy.returncode == 0 and out_path.exists():
        return
    # Stream copy can fail when -ss lands mid-GOP on some providers.
    # Re-encode as a fallback; keep audio so Wan3.0 gets the ambient bed.
    out_path.unlink(missing_ok=True)
    reencode = _run(
        [
            ffmpeg_path,
            "-y",
            *seek_args,
            "-i",
            os.fspath(source),
            "-t",
            f"{tail_seconds:.6f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            os.fspath(out_path),
        ],
        timeout=_FFMPEG_TIMEOUT_SECONDS,
    )
    if reencode.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            "尾段抽取失败: "
            + (
                reencode.stderr.strip()[:400]
                or reencode.stdout.strip()[:400]
                or stream_copy.stderr.strip()[:200]
            ),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _build_entry(
    kind: Literal["last_frame", "tail_clip"],
    *,
    path: Path,
    prev_version: str,
    prev_element_id: str,
    media_type: str,
    role_label: str,
    duration_seconds: float | None = None,
) -> ContinuityEntry:
    # Both identifiers share the ``continuity:<kind>:`` prefix with the
    # same underscore spelling; only the tail differs (version id for
    # the fingerprint-stable reference, element id for provenance).
    if kind == "last_frame":
        reference_id = _last_frame_reference_id(prev_version)
        provenance = f"continuity:last_frame:{prev_element_id}"
    else:
        reference_id = _tail_clip_reference_id(prev_version)
        provenance = f"continuity:tail_clip:{prev_element_id}"
    return ContinuityEntry(
        kind=kind,
        reference_id=reference_id,
        url=path.resolve().as_uri(),
        checksum=_sha256(path),
        path=path,
        role_label=role_label,
        provenance_ref=provenance,
        media_type=media_type,
        duration_seconds=duration_seconds,
    )


def _atomic_run(
    extract: "Callable[[Path, str], None]",
    final_path: Path,
    ffmpeg_path: str,
) -> None:
    """Run ffmpeg into a private temp file, then atomic rename on success.

    Any half-written leftover under concurrent calls would give a
    corrupted sha256; writing into a per-invocation tmp path and
    ``os.replace``-ing into place means readers only ever see a fully
    materialized file. Existing outputs are not re-cut when they are
    already present (cache-hit path), so this function is only reached
    on miss under the per-key extraction lock.

    The uniqueness markers go *before* the extension, not appended after
    it: ffmpeg picks the output muxer from the filename suffix, so a temp
    name like ``last_frame.png.tmp.123.456`` (suffix ``.456``) fails with
    "Unable to find a suitable output format". Keeping ``.png`` /
    ``.mp4`` as the trailing suffix lets the real cutter infer the format
    while the write still lands in a private, collision-free path.
    """

    tmp_path = final_path.with_name(
        f"{final_path.stem}.tmp.{os.getpid()}.{threading.get_ident()}"
        f"{final_path.suffix}",
    )
    try:
        extract(tmp_path, ffmpeg_path)
        os.replace(tmp_path, final_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_last_frame_into(
    source: Path,
    ffmpeg_path: str,
    tmp_path: Path,
) -> None:
    _extract_last_frame(source, tmp_path, ffmpeg_path)


def _extract_tail_clip_into(
    source: Path,
    ffmpeg_path: str,
    tmp_path: Path,
    *,
    tail_seconds: float,
    total_duration: float,
) -> None:
    _extract_tail_clip(
        source,
        tmp_path,
        ffmpeg_path,
        tail_seconds=tail_seconds,
        total_duration=total_duration,
    )


def _cut_both(
    *,
    source: Path,
    work_dir: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    prev_version: str,
    prev_element_id: str,
    include_tail_clip: bool,
) -> tuple[ContinuityEntry, ...]:
    """Cut last_frame (+ optional tail_clip) with atomic writes.

    Last-frame extraction is mandatory: any failure raises and the
    caller falls back to no continuity at all. Tail-clip extraction is
    attempted only when ``include_tail_clip`` is true, and its failure
    degrades softly (last_frame still returned) so I2V chains, which
    only need the last frame, are never blocked by a container-level
    tail-clip glitch on a Wan3.0-configured machine.
    """

    last_frame_path = work_dir / "last_frame.png"
    _atomic_run(
        lambda tmp, ff: _extract_last_frame_into(source, ff, tmp),
        last_frame_path,
        ffmpeg_path,
    )
    entries: list[ContinuityEntry] = [
        _build_entry(
            "last_frame",
            path=last_frame_path,
            prev_version=prev_version,
            prev_element_id=prev_element_id,
            media_type="image/png",
            role_label="上一段末帧（本段起始状态对齐此图）",
        ),
    ]
    if not include_tail_clip:
        return tuple(entries)
    tail_clip_path = work_dir / "tail_clip.mp4"
    try:
        total = _probe_duration(source, ffprobe_path)
    except RuntimeError:
        # An unreadable duration must not cost us the tail: the cutter
        # falls back to container-relative ``-sseof`` seeking below.
        total = 0.0
    tail = min(_TAIL_CLIP_SECONDS, total) if total > 0 else _TAIL_CLIP_SECONDS
    try:
        _atomic_run(
            lambda tmp, ff: _extract_tail_clip_into(
                source,
                ff,
                tmp,
                tail_seconds=tail,
                total_duration=total,
            ),
            tail_clip_path,
            ffmpeg_path,
        )
    except RuntimeError as error:
        # Soft failure: report the diagnostic but return the bundle with
        # just the last frame so the R2V path still gets image anchor.
        from services.observability import report_error

        report_error(
            component="continuity.tail_clip",
            code="TAIL_CLIP_EXTRACTION_FAILED",
            message=str(error),
            error=error,
            prev_element_id=prev_element_id,
            prev_video_version=prev_version,
        )
        return tuple(entries)
    entries.append(
        _build_entry(
            "tail_clip",
            path=tail_clip_path,
            prev_version=prev_version,
            prev_element_id=prev_element_id,
            media_type="video/mp4",
            role_label="上一段尾段视频（含音频，作为向后延长起点）",
            duration_seconds=tail,
        ),
    )
    return tuple(entries)


def _trace_skip(reason: str, **context: object) -> None:
    """Emit a design-level skip so production traces can explain why a
    segment went out without continuity anchors. Failure-driven skips
    already ``report_error`` at their decision point; this covers the
    otherwise silent ``return None`` branches (first segment, prev not
    published yet).
    """

    from services.observability import trace_event

    trace_event(
        "creator.continuity.skipped",
        component="continuity",
        status="ok",
        attributes={"reason": reason},
        **context,
    )


def _cached_digests() -> set[str]:
    """Digest directory names referenced by the in-memory cache."""

    with _continuity_cache_lock:
        keys = list(_continuity_cache.keys())
    return {_digest_for(prev_version) for prev_version, _ff, _tail in keys}


def _prune_continuity_dirs(
    project_root: Path,
    *,
    current_digest: str,
    extra_keep: "set[str] | None" = None,
) -> int:
    """Best-effort GC of extract directories nothing references anymore.

    The in-memory LRU bounds bundles but not bytes: every rerolled
    predecessor version leaves a digest directory behind (PNG + MP4,
    megabytes each). A directory goes only when it is not referenced by
    the in-process cache, not the extract in flight, not in the
    in-flight digest registry (this process's queued work), not in
    ``extra_keep`` (digests a not-yet-terminal Task froze into its
    payload), and quiet for the grace window. The registry + extra_keep
    keep in-flight submits holding an entry evicted between resolve and
    upload alive — critical at startup, when the cold cache would
    otherwise let the sweep delete the file:// anchors of queued work.
    Honours the task-scratch emergency switch and never raises.
    """

    try:
        from services.media_files.task_scratch import scratch_release_enabled

        if not scratch_release_enabled():
            return 0
        root = project_root / _CONTINUITY_ROOT
        if not root.is_dir():
            return 0
        now = time.time()
        keep = (
            _cached_digests()
            | {current_digest}
            | set(extra_keep or ())
            | _inflight_keep(now)
        )
        removed = 0
        for entry in os.scandir(root):
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name in keep:
                    continue
                info = entry.stat(follow_symlinks=False)
                if now - info.st_mtime < _PRUNE_GRACE_SECONDS:
                    continue
            except OSError:
                continue
            shutil.rmtree(entry.path, ignore_errors=True)
            removed += 1
        return removed
    except Exception:  # noqa: BLE001 - GC must never break generation
        return 0


def _frozen_continuity_digests(task: Any) -> set[str]:
    """Digest dirs a Task froze into its payload as continuity anchors.

    Reads the frozen request snapshot's synthetic ``continuity:*:<prev>``
    ids (r2v ``referenceVersionIds`` and i2v ``firstFrameVersionId``) and
    maps each predecessor version back to its digest directory, so a sweep
    can protect anchors a not-yet-submitted render still points at.
    """

    metadata = getattr(task, "metadata", None) or {}
    snapshot = metadata.get("requestSnapshot")
    if not isinstance(snapshot, dict):
        return set()
    ids: list[str] = []
    refs = snapshot.get("referenceVersionIds")
    if isinstance(refs, (list, tuple)):
        ids.extend(str(item) for item in refs)
    first_frame = snapshot.get("firstFrameVersionId")
    if first_frame:
        ids.append(str(first_frame))
    digests: set[str] = set()
    for ref in ids:
        if not ref.startswith("continuity:"):
            continue
        parts = ref.split(":", 2)
        if len(parts) == 3 and parts[2]:
            digests.add(_digest_for(parts[2]))
    return digests


def sweep_orphaned_continuity(services: Any, *, budget: Any = None) -> int:
    """Maintenance GC for continuity extracts left by idle Projects.

    Active Projects prune on every extract, so their digest directories
    stay bounded. A Project that stopped generating never runs another
    extract, so its last anchors would linger until the next submit —
    this startup/maintenance pass collects them across every Project,
    mirroring ``release_orphaned_scratch`` for task-work.

    The in-memory cache is cold at startup, so it cannot protect the
    anchors a QUEUED / ADMITTED render froze into its payload; this pass
    therefore keeps every digest referenced by work that is not
    releasably terminal — the same ``is_releasable_terminal_task``
    convention the scratch sweeper uses, which also preserves a
    QUARANTINED task's anchors as audit evidence — before pruning, so a
    restart never turns queued work into a failed submit. Surviving
    digests are registered in the in-flight table so later event-driven
    prunes keep protecting them. Reuses ``_prune_continuity_dirs``
    (grace window + emergency switch + never raises). Returns the number
    of directories collected.
    """

    from services.media_files.task_scratch import is_releasable_terminal_task
    from services.runtime_files.execution_store import ProjectExecutionStore

    total = 0
    try:
        project_ids = services.projects.discover_project_ids()
    except Exception:  # noqa: BLE001 - a sweep must never gate startup
        return 0
    try:
        executions = ProjectExecutionStore(services.root)
    except Exception:  # noqa: BLE001 - no store => cannot prove what is safe
        # Without the task ledger we cannot build the in-flight keep set,
        # so pruning could delete a queued render's anchor. Stay hands-off.
        logger.warning(
            "continuity sweep skipped: execution store unavailable",
            exc_info=True,
        )
        return 0
    for project_id in project_ids:
        if budget is not None and not budget.has_room():
            break
        try:
            root = Path(services.projects.project_root(project_id))
        except (
            Exception
        ):  # noqa: BLE001 - one bad Project cannot stop the pass
            continue
        keep: set[str] = set()
        try:
            for task in executions.list_tasks(project_id):
                # Releasably terminal (and NOT quarantined) means the
                # render is done with its anchors; anything else —
                # queued, running, or quarantined evidence — keeps them.
                if is_releasable_terminal_task(task):
                    continue
                keep |= _frozen_continuity_digests(task)
        except Exception:  # noqa: BLE001 - unreadable tasks must not gate GC
            logger.warning(
                "continuity sweep skipped unreadable tasks: project=%s",
                project_id,
                exc_info=True,
            )
        for digest in keep:
            _register_inflight_digest(digest)
        total += _prune_continuity_dirs(
            root,
            current_digest="",
            extra_keep=keep,
        )
    return total


def extract_continuity_artifacts(
    *,
    project: Project,
    project_root: Path,
    timeline: Timeline,
    element: TimelineElement,
    include_tail_clip: bool,
) -> ContinuityBundle | None:
    """Return predecessor's last_frame (+ optional tail_clip) for injection.

    Returns ``None`` when the element is the first in the lane, or when
    the predecessor's video has not been published/selected yet. Raises
    ``RuntimeError`` when ffmpeg/ffprobe is unavailable or the last-frame
    extract fails — the caller in the R2V submit path treats that as
    "skip continuity" and proceeds without anchors, rather than
    blocking generation. A tail-clip failure alone degrades softly.

    Two scheduler threads racing for the same predecessor serialize on
    a per-key lock, then the second one finds the cached bundle during
    the double-check. ffmpeg writes into a per-invocation tmp file and
    ``os.replace`` moves it into place, so a half-written PNG/MP4 can
    never be sha256'd by a concurrent reader.

    Every failure that reaches a caller is a ``RuntimeError`` (or a
    ``ValidationError`` for a broken Asset Index): ``_run`` converges
    timeouts and unexecutable binaries, and the filesystem work below
    converges disk-full / permission errors, so the best-effort contract
    cannot be bypassed by an exotic exception type.

    After publishing a fresh bundle the digest root gets a best-effort
    GC pass so rerolled predecessors do not accumulate MB-scale tail
    clips on disk forever.
    """

    # Inherently branchy: predecessor / publish checks, the two-phase
    # cache double-check under a per-key lock, and the post-publish GC.
    # Splitting it would scatter the lock/cache/GC invariant across
    # helpers without reducing real complexity.
    # pylint: disable=too-many-branches,too-many-statements
    prev = find_predecessor_video_element(timeline, element)
    if prev is None:
        _trace_skip(
            "no_predecessor",
            project_id=str(project.project_id),
            element_id=element.element_id,
        )
        return None
    prev_version = resolve_predecessor_video_version(project, prev)
    if not prev_version:
        _trace_skip(
            "predecessor_unpublished",
            project_id=str(project.project_id),
            element_id=element.element_id,
            prev_element_id=prev.element_id,
        )
        return None
    # Whatever we return here gets frozen into this dispatch's payload;
    # register the digest so neither the event-driven prune below nor a
    # later sweep can delete the anchors while that work is unfinished.
    _register_inflight_digest(_digest_for(prev_version))

    from services.runtime_files.runtime_dependencies import (
        resolve_ffmpeg,
        resolve_ffprobe,
    )

    ffmpeg_path = resolve_ffmpeg()
    ffprobe_path = resolve_ffprobe(ffmpeg_path=ffmpeg_path)
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError("ffmpeg/ffprobe 未就绪，跳过段间衔接注入")

    cache_key = (prev_version, ffmpeg_path, include_tail_clip)
    with _continuity_cache_lock:
        cached = _continuity_cache.get(cache_key)
        if cached is not None:
            _continuity_cache.move_to_end(cache_key)
    if cached is not None:
        return cached

    with _continuity_locks_guard:
        extract_lock = _continuity_extract_locks.get(cache_key)
        if extract_lock is None:
            extract_lock = threading.Lock()
            _continuity_extract_locks[cache_key] = extract_lock

    with extract_lock:
        # Double-check: a sibling that acquired the lock first has
        # already published the bundle.
        with _continuity_cache_lock:
            cached = _continuity_cache.get(cache_key)
            if cached is not None:
                _continuity_cache.move_to_end(cache_key)
        if cached is not None:
            return cached
        try:
            source = _resolve_prev_video_path(
                project,
                project_root,
                prev_version,
            )
            if not source.exists():
                raise RuntimeError(f"上一段视频文件缺失: {source}")
            work_dir = _work_dir_for(project_root, prev_version)
            entries = _cut_both(
                source=source,
                work_dir=work_dir,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                prev_version=prev_version,
                prev_element_id=prev.element_id,
                include_tail_clip=include_tail_clip,
            )
        except OSError as error:
            # Disk full, unwritable scratch, vanished mount: keep the
            # best-effort contract instead of failing the paid render.
            raise RuntimeError(
                f"段间衔接产物读写失败: {error}",
            ) from error
        bundle = ContinuityBundle(
            predecessor_element_id=prev.element_id,
            predecessor_video_version_id=prev_version,
            entries=entries,
        )
        evicted_keys: list[tuple[str, str, bool]] = []
        with _continuity_cache_lock:
            _continuity_cache[cache_key] = bundle
            _continuity_cache.move_to_end(cache_key)
            while len(_continuity_cache) > _CACHE_MAX_ITEMS:
                evicted, _ = _continuity_cache.popitem(last=False)
                evicted_keys.append(evicted)
        if evicted_keys:
            # Retire per-key locks under their own guard so the dict
            # mutation stays serialized with lock creation above; the
            # cache lock alone does not protect this map.
            with _continuity_locks_guard:
                for evicted in evicted_keys:
                    _continuity_extract_locks.pop(evicted, None)
        pruned = _prune_continuity_dirs(
            project_root,
            current_digest=_digest_for(prev_version),
        )
        if pruned:
            from services.observability import trace_event

            trace_event(
                "creator.continuity.pruned",
                component="continuity",
                status="ok",
                attributes={"removedDirs": pruned},
                project_id=str(project.project_id),
            )
        return bundle


def continuity_prompt_suffix(
    *,
    last_frame_index: int,
    tail_clip_index: int | None,
) -> str:
    """Return the prompt tail for adjacent-segment continuity.

    ``last_frame_index`` is the 1-based position of the predecessor's
    last frame within the final ``reference_image`` sequence. It is
    emitted as canonical ``[Image N]`` so ``_render_reference_markers``
    can rewrite it into whatever the active provider documents.

    ``tail_clip_index`` is the 1-based position of the tail clip
    within the ``reference_video`` sequence, or ``None`` when the model
    does not accept a reference video (HappyHorse, Veo, ...). When set,
    the suffix is written in Wan3.0's native "视频N" form using the
    real ordinal because that family is the only one this branch
    targets and no canonical video marker exists in the shared
    renderer.
    """

    if tail_clip_index is None:
        return (
            f"\n\n将 [Image {last_frame_index}] 作为本段起始状态："
            "第一帧的人物姿态、机位、构图、光线和环境应与该图保持一致，"
            "在此之上继续展开本段动作。"
        )
    return (
        f"\n\n将视频{tail_clip_index}向后延长："
        f"起始画面对齐 [Image {last_frame_index}]（上一段末帧），"
        "运镜节奏与环境声延续该尾段，随后展开本段剧本要求的新动作。"
    )


__all__ = [
    "ContinuityBundle",
    "ContinuityEntry",
    "continuity_prompt_suffix",
    "continuity_reference_ids",
    "extract_continuity_artifacts",
    "find_predecessor_video_element",
    "resolve_predecessor_video_version",
    "sweep_orphaned_continuity",
    "tail_clip_enabled",
]
