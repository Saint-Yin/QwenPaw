# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=consider-using-with,raise-missing-from,too-many-branches
# pylint: disable=too-many-statements
"""File-native local video execution for edit and composition commands.

The service freezes one ``project.json`` snapshot, resolves every input through
its ``IndexedFile`` and immutable version record, persists Run/Task/Attempt
facts, and executes an injectable runner in
``<project>/runtime/task-work/<task-id>`` without holding Project or Runtime
locks.  A successful output is published through :class:`AssetFileStore` and
then indexed and selected by one Project commit.  Late cancelled or stale
outputs remain immutable but unindexed and are recorded in Runtime quarantine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
from typing import Any, Protocol, TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from domain.enums import (
    CreatorCommandType,
    SpecialistRole,
    SpecialistRunStatus,
    TaskKind,
    TaskStatus,
)
from domain.errors import (
    ConflictError,
    NotFoundError,
    StorageIntegrityError,
    ValidationError,
)
from services.media_files.overlay import (
    PET_OS_VIBES,
    render_interview_summary_overlay,
    render_pet_os_overlay,
)
from services.project_files.assets import (
    AssetAlreadyExists,
    AssetFileError,
    AssetFileStore,
)
from services.project_files.models import (
    ArtifactSlot,
    ArtifactVersion,
    Composition,
    EditProduction,
    IndexedFile,
    Project,
)
from services.project_files.remote_cache import (
    public_source_url,
    resolve_remote_cache,
)
from services.project_files.store import ProjectSnapshot
from services.runtime_files.atomic_store import (
    AtomicJsonRecordStore,
    canonical_json_bytes,
)
from services.runtime_files.errors import RecordNotFoundError
from services.runtime_files.execution_models import (
    SpecialistRunRecord,
    TaskAttemptStatus,
    TaskRecord,
)
from services.runtime_files.execution_store import (
    ExecutionPayloadConflict,
    ExecutionStateConflict,
    ProjectExecutionStore,
)
from services.runtime_files.models import ChangeOrigin, ReviewPolicy
from services.runtime_files.media_probe import MediaProbeError, probe_media
from services.runtime_files.runtime_dependencies import resolve_ffmpeg
from utils.logger import setup_logger
from utils.remote_download import download_remote_file

if TYPE_CHECKING:
    from services.project_files.facade import CreatorFileServices


logger = setup_logger("services.media_files.local_execution")

_LOCAL_MEDIA_COMMANDS = frozenset(
    {
        CreatorCommandType.EXECUTE_EDIT,
        CreatorCommandType.STITCH_SECTION,
        CreatorCommandType.COMPOSE_FINAL_VIDEO,
    },
)
_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_DEFAULT_FFMPEG_TIMEOUT_SECONDS = 15 * 60.0
_DEFAULT_FFMPEG_TERMINATION_GRACE_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class LocalMediaInput:
    version_id: str
    file_id: str | None
    checksum: str
    media_type: str
    path: Path
    source_ref: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    duration_seconds: float | None = None
    original_sound: str = "preserve"
    overlay: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LocalMediaExecutionSpec:
    command: CreatorCommandType
    target_ref: str
    task_id: str
    work_dir: Path
    output_path: Path
    inputs: tuple[LocalMediaInput, ...]
    transitions: tuple[dict[str, Any], ...]
    audio_plan: Mapping[str, Any] | str
    expected_duration_seconds: float | None
    on_clip_done: Callable[[int, int], None] | None = None


class LocalMediaRunner(Protocol):
    """Runner boundary.  Implementations write exactly ``spec.output_path``."""

    async def render(self, spec: LocalMediaExecutionSpec) -> Mapping[str, Any]:
        ...


class FfmpegLocalMediaRunner:
    """Default local ffmpeg runner with no global ``/generated`` authority."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = _DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        termination_grace_seconds: float = (
            _DEFAULT_FFMPEG_TERMINATION_GRACE_SECONDS
        ),
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if (
            not math.isfinite(termination_grace_seconds)
            or termination_grace_seconds <= 0
        ):
            raise ValueError(
                "termination_grace_seconds must be finite and positive",
            )
        self.executable = executable or resolve_ffmpeg() or "ffmpeg"
        self.timeout_seconds = float(timeout_seconds)
        self.termination_grace_seconds = float(termination_grace_seconds)

    async def render(self, spec: LocalMediaExecutionSpec) -> Mapping[str, Any]:
        self._validate_supported_directives(spec)
        overlay_warnings = await asyncio.to_thread(self._render_sync, spec)
        metadata: dict[str, Any] = {"runner": "ffmpeg"}
        if overlay_warnings:
            metadata["overlayWarnings"] = overlay_warnings
        return {
            "media_type": "video/mp4",
            "duration_seconds": spec.expected_duration_seconds,
            "metadata": metadata,
        }

    def _render_sync(self, spec: LocalMediaExecutionSpec) -> list[str]:
        if not spec.inputs:
            raise ValidationError("本地媒体执行至少需要一个输入")
        concat_inputs: list[Path] = []
        overlay_warnings: list[str] = []
        if spec.command is CreatorCommandType.EXECUTE_EDIT:
            segment_dir = _ensure_real_directory_chain(
                spec.work_dir,
                "segments",
            )
            for index, item in enumerate(spec.inputs):
                if item.start_seconds is None or item.end_seconds is None:
                    raise ValidationError("AI Edit clip 缺少 source range")
                segment = segment_dir / f"{index:06d}.mp4"
                self._run(
                    [
                        "-y",
                        "-ss",
                        f"{item.start_seconds:.6f}",
                        "-t",
                        f"{item.end_seconds - item.start_seconds:.6f}",
                        "-i",
                        os.fspath(item.path),
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a?",
                        "-vf",
                        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        os.fspath(segment),
                    ],
                    cwd=spec.work_dir,
                )
                warning = self._apply_overlay(item, segment)
                if warning is not None:
                    overlay_warnings.append(
                        f"{item.source_ref or item.version_id}: {warning}",
                    )
                concat_inputs.append(segment)
                if spec.on_clip_done is not None:
                    spec.on_clip_done(index + 1, len(spec.inputs))
        else:
            concat_inputs.extend(item.path for item in spec.inputs)
        self._concat(concat_inputs, spec.output_path, work_dir=spec.work_dir)
        return overlay_warnings

    def _apply_overlay(
        self,
        item: LocalMediaInput,
        segment: Path,
    ) -> str | None:
        overlay = self._normalized_overlay(item)
        if overlay is None:
            return None
        video_size = self._probe_video_size(segment)
        rendered = segment.with_name(f"{segment.stem}-overlay.mp4")
        if overlay["kind"] == "pet_os":
            result = render_pet_os_overlay(
                ffmpeg_path=self.executable,
                input_path=segment,
                output_path=rendered,
                text=overlay["text"],
                vibe=overlay["vibe"],
                video_size=video_size,
                appear_at=overlay["appear_at"],
                duration=overlay["duration"],
            )
        else:
            result = render_interview_summary_overlay(
                ffmpeg_path=self.executable,
                input_path=segment,
                output_path=rendered,
                text=overlay["text"],
                video_size=video_size,
                appear_at=overlay["appear_at"],
                duration=overlay["duration"],
            )
        if not result.success:
            rendered.unlink(missing_ok=True)
            return result.error or f"{overlay['kind']} overlay 渲染失败"
        os.replace(rendered, segment)
        return None

    @staticmethod
    def _normalized_overlay(item: LocalMediaInput) -> dict[str, Any] | None:
        raw = item.overlay
        if not isinstance(raw, Mapping):
            return None
        kind = str(raw.get("kind") or "").strip().casefold()
        text = str(raw.get("text") or "").strip()
        if kind not in {"pet_os", "interview_summary"} or not text:
            return None
        clip_duration = (
            item.end_seconds - item.start_seconds
            if item.start_seconds is not None and item.end_seconds is not None
            else item.duration_seconds
        )
        if clip_duration is None or not math.isfinite(clip_duration):
            return None
        try:
            appear_at = float(raw.get("appear_at", 0.0))
        except (TypeError, ValueError):
            appear_at = 0.0
        if not math.isfinite(appear_at):
            appear_at = 0.0
        appear_at = max(0.0, appear_at)
        if appear_at >= clip_duration:
            return None
        try:
            duration = float(raw.get("duration", clip_duration - appear_at))
        except (TypeError, ValueError):
            duration = clip_duration - appear_at
        if not math.isfinite(duration) or duration <= 0:
            duration = clip_duration - appear_at
        duration = min(duration, clip_duration - appear_at)
        vibe = str(raw.get("vibe") or "chill").strip().casefold()
        return {
            "kind": kind,
            "text": text,
            "vibe": vibe if vibe in PET_OS_VIBES else "chill",
            "appear_at": appear_at,
            "duration": duration,
        }

    def _probe_video_size(self, path: Path) -> tuple[int, int]:
        try:
            metadata = probe_media(
                os.fspath(path),
                ffmpeg_path=self.executable,
                timeout=min(self.timeout_seconds, 30.0),
            )
            if metadata.width and metadata.height:
                return metadata.width, metadata.height
        except MediaProbeError:
            pass
        return 1280, 720

    @staticmethod
    def _validate_supported_directives(spec: LocalMediaExecutionSpec) -> None:
        unsupported_transitions: list[str] = []
        for transition in spec.transitions:
            kind = str(transition.get("kind") or "cut").strip().casefold()
            raw_duration = transition.get("duration_ms", 0)
            duration_ms = (
                int(raw_duration)
                if isinstance(raw_duration, (int, float))
                and not isinstance(raw_duration, bool)
                else 0
            )
            if kind != "cut" or duration_ms != 0:
                unsupported_transitions.append(
                    f"{kind or '<empty>'}:{duration_ms}ms",
                )
        if unsupported_transitions:
            raise ValidationError(
                "默认 ffmpeg runner 尚不支持非硬切 transition: "
                + ", ".join(unsupported_transitions),
            )

        unsupported_original_sound = sorted(
            {
                item.original_sound.strip()
                for item in spec.inputs
                if item.original_sound.strip().casefold()
                not in {"", "preserve"}
            },
        )
        if unsupported_original_sound:
            raise ValidationError(
                "默认 ffmpeg runner 尚不支持 original_sound 指令: "
                + ", ".join(unsupported_original_sound),
            )

        if isinstance(spec.audio_plan, Mapping):
            preserve_original = spec.audio_plan.get("preserve_original", True)
            instructions = [
                str(spec.audio_plan.get(key) or "").strip()
                for key in ("music_prompt", "voiceover", "notes")
            ]
            if preserve_original is not True or any(instructions):
                raise ValidationError(
                    "默认 ffmpeg runner 仅支持保留原声且无配乐、旁白或备注的 audio_plan",
                )
        elif str(spec.audio_plan or "").strip():
            # Planning agents record free-text audio ideas on the
            # composition (e.g. "轻快节奏背景音乐").  The string form carries no
            # structured directive the local pipeline could execute, and
            # neither the UI nor any command lets users clear the field, so
            # failing here would dead-end COMPOSE_FINAL_VIDEO for every
            # agent-driven project.  Preserve the original audio and surface
            # the note in the log instead.
            logger.warning(
                "默认 ffmpeg runner 忽略自由文本 audio_plan（保留原声）: %s",
                str(spec.audio_plan).strip(),
            )

    def _concat(
        self,
        inputs: Sequence[Path],
        output: Path,
        *,
        work_dir: Path,
    ) -> None:
        manifest = work_dir / "concat.txt"
        manifest.write_text(
            "".join(f"file '{_ffconcat_path(path)}'\n" for path in inputs),
            encoding="utf-8",
        )
        self._run(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                os.fspath(manifest),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                os.fspath(output),
            ],
            cwd=work_dir,
        )

    def _run(self, arguments: Sequence[str], *, cwd: Path) -> None:
        try:
            process = subprocess.Popen(
                [self.executable, *arguments],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ValidationError("本机未安装 ffmpeg") from exc
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.communicate(timeout=self.termination_grace_seconds)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.communicate(timeout=self.termination_grace_seconds)
                except subprocess.TimeoutExpired:
                    # The child has already received the strongest portable
                    # signal.  Never turn cleanup into another unbounded wait.
                    pass
            raise ConflictError(
                f"ffmpeg 执行超时（{self.timeout_seconds:g} 秒）",
            ) from exc
        if process.returncode != 0:
            detail = (stderr or stdout or "ffmpeg failed")[-4000:]
            raise ConflictError(f"ffmpeg 执行失败: {detail}")


@dataclass(frozen=True, slots=True)
class FileLocalMediaExecutionResult:
    task_id: str
    run_id: str
    transaction_id: str
    artifact_version_id: str
    project_etag: str
    project_generation: int
    replayed: bool

    def command_response(self, command_id: str) -> dict[str, Any]:
        return {
            "commandId": command_id,
            "status": "APPLIED",
            "eventSeq": 0,
            "transactionId": self.transaction_id,
            "workingHead": self.project_etag,
        }


@dataclass(frozen=True, slots=True)
class _FrozenInput:
    version_id: str
    indexed: IndexedFile | None
    checksum: str
    source_ref: str
    media_type: str
    source_url: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    duration_seconds: float | None = None
    original_sound: str = "preserve"
    overlay: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class _ResolvedExecution:
    command: CreatorCommandType
    target_ref: str
    task_kind: TaskKind
    inputs: tuple[_FrozenInput, ...]
    transitions: tuple[dict[str, Any], ...]
    audio_plan: Mapping[str, Any] | str
    expected_duration_seconds: float | None
    slot_id: str
    slot_kind: str
    owner_ref: str
    artifact_name: str
    read_set: tuple[dict[str, Any], ...]
    source_selections: tuple[dict[str, Any], ...]
    edit_plan_id: str | None = None
    edit_plan_hash: str | None = None


def _stable_id(prefix: str, project_id: str, key: str) -> str:
    digest = uuid5(
        NAMESPACE_URL,
        f"qwenpaw-creator:file-local-media:{prefix}:{project_id}:{key}",
    ).hex
    return f"{prefix}-{digest}"


def _fingerprint(value: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def _target_id(target_ref: str, prefix: str) -> str:
    expected = f"{prefix}:"
    if not target_ref.startswith(expected) or not target_ref[len(expected) :]:
        raise ValidationError(f"targetRef 必须是 {expected}<id>")
    return target_ref[len(expected) :]


def _ffconcat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def _require_real_directory(path: Path) -> None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError as exc:
        raise StorageIntegrityError(
            f"Runtime task-work 父目录不存在: {path}",
        ) from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise StorageIntegrityError(f"Runtime task-work 路径不安全: {path}")


def _ensure_real_directory_chain(root: Path, *segments: str) -> Path:
    """Create one descendant chain without ever following a symlink parent."""

    _require_real_directory(root)
    current = root
    for segment in segments:
        if (
            not segment
            or segment in {".", ".."}
            or "/" in segment
            or "\\" in segment
        ):
            raise StorageIntegrityError(
                f"Runtime task-work 路径段不安全: {segment!r}",
            )
        child = current / segment
        try:
            child.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _require_real_directory(child)
        current = child
    return current


def _find_section(project: Project, section_id: str):
    section = project.story.sections.items.get(section_id)
    if section is None:
        raise NotFoundError("Section 不存在")
    return section


def _find_unit(project: Project, unit_id: str):
    for section in project.story.sections.items.values():
        unit = section.units.items.get(unit_id)
        if unit is not None:
            return unit
    raise NotFoundError("Unit 不存在")


def _indexed_version(
    project: Project,
    version_id: str,
    *,
    require_artifact: bool,
) -> tuple[IndexedFile | None, Any]:
    version = (
        project.assets.artifact_versions_by_id.get(version_id)
        if require_artifact
        else project.assets.source_versions_by_id.get(version_id)
    )
    if version is None:
        label = "ArtifactVersion" if require_artifact else "AssetVersion"
        raise NotFoundError(f"{label} 不存在: {version_id}")
    indexed = (
        project.assets.files_by_id.get(version.file_id)
        if version.file_id is not None
        else None
    )
    if indexed is None and not (
        not require_artifact and public_source_url(version) is not None
    ):
        raise StorageIntegrityError(f"版本缺少 IndexedFile: {version_id}")
    media_type = (
        indexed.media_type if indexed is not None else version.media_type
    )
    if not media_type.casefold().startswith("video/"):
        raise ValidationError(f"媒体输入不是视频: {version_id}")
    return indexed, version


def _read_set_item(
    kind: str,
    version_id: str,
    indexed: IndexedFile | None,
    checksum: str,
) -> dict[str, Any]:
    return {
        "ref": f"{kind}:{version_id}",
        "versionId": version_id,
        "fileId": indexed.file_id if indexed is not None else None,
        "checksum": checksum,
    }


def _composition_execution(
    *,
    project: Project,
    command: CreatorCommandType,
    target_ref: str,
    composition: Composition | None,
    owner_ref: str,
    slot_id: str,
    slot_kind: str,
    artifact_name: str,
) -> _ResolvedExecution:
    if composition is None or not composition.sequence.order:
        raise ConflictError("Compose 必须先保存明确 ArtifactVersion selections")
    inputs: list[_FrozenInput] = []
    read_set: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    durations: list[float | None] = []
    for order, selection_id in enumerate(composition.sequence.order, 1):
        selection = composition.sequence.items[selection_id]
        indexed, version = _indexed_version(
            project,
            selection.artifact_version_id,
            require_artifact=True,
        )
        inputs.append(
            _FrozenInput(
                version_id=version.version_id,
                indexed=indexed,
                checksum=version.checksum,
                source_ref=selection.source_ref,
                media_type=indexed.media_type,
                duration_seconds=version.duration_seconds,
            ),
        )
        read_set.append(
            _read_set_item(
                "artifact-version",
                version.version_id,
                indexed,
                version.checksum,
            ),
        )
        selections.append(
            {
                "sourceRef": selection.source_ref,
                "artifactVersionId": version.version_id,
                "order": order,
                "sourceKind": selection.source_kind,
            },
        )
        durations.append(version.duration_seconds)
    duration = (
        sum(item for item in durations if item is not None)
        if all(item is not None for item in durations)
        else None
    )
    return _ResolvedExecution(
        command=command,
        target_ref=target_ref,
        task_kind=TaskKind.COMPOSE,
        inputs=tuple(inputs),
        transitions=tuple(
            transition.model_dump(mode="json")
            for transition in composition.transitions
        ),
        audio_plan=composition.audio_plan,
        expected_duration_seconds=duration,
        slot_id=slot_id,
        slot_kind=slot_kind,
        owner_ref=owner_ref,
        artifact_name=artifact_name,
        read_set=tuple(read_set),
        source_selections=tuple(selections),
    )


def _resolve_execution(
    *,
    snapshot: ProjectSnapshot,
    command: CreatorCommandType,
    target_ref: str,
    arguments: Mapping[str, Any],
) -> _ResolvedExecution:
    project = snapshot.project
    if command is CreatorCommandType.EXECUTE_EDIT:
        unit_id = _target_id(target_ref, "unit")
        unit = _find_unit(project, unit_id)
        production = project.production.units_by_id.get(unit_id)
        if unit.route.value != "edit" or not isinstance(
            production,
            EditProduction,
        ):
            raise ConflictError("EXECUTE_EDIT 只能执行 edit Unit")
        plan = production.plan
        if plan is None or not plan.timeline.order:
            raise ConflictError("Unit 缺少可执行 AI Edit Plan")
        requested_plan_id = str(arguments.get("planVersionId") or "").strip()
        if requested_plan_id and requested_plan_id != plan.plan_id:
            raise ConflictError("planVersionId 不是当前嵌入式 AI Edit Plan")
        inputs: list[_FrozenInput] = []
        read_set: list[dict[str, Any]] = []
        duration = 0.0
        content_type = getattr(project, "content_type", None) or ""
        for clip_id in plan.timeline.order:
            clip = plan.timeline.items[clip_id]
            indexed, version = _indexed_version(
                project,
                clip.source_asset_version_id,
                require_artifact=False,
            )
            overlay = clip.overlay
            if (
                content_type == "interview"
                and (not overlay or not overlay.get("text"))
                and clip.reason
            ):
                clip_dur = clip.source_out_seconds - clip.source_in_seconds
                overlay = {
                    "kind": "interview_summary",
                    "text": clip.reason[:30],
                    "appear_at": 0.2,
                    "duration": min(3.0, max(0.5, clip_dur - 0.3)),
                }
            inputs.append(
                _FrozenInput(
                    version_id=version.version_id,
                    indexed=indexed,
                    checksum=version.checksum,
                    source_ref=f"clip:{clip.clip_id}",
                    media_type=version.media_type,
                    source_url=public_source_url(version),
                    start_seconds=clip.source_in_seconds,
                    end_seconds=clip.source_out_seconds,
                    duration_seconds=clip.source_out_seconds
                    - clip.source_in_seconds,
                    original_sound=clip.original_sound,
                    overlay=overlay,
                ),
            )
            read_set.append(
                _read_set_item(
                    "asset-version",
                    version.version_id,
                    indexed,
                    version.checksum,
                ),
            )
            duration += clip.source_out_seconds - clip.source_in_seconds
        return _ResolvedExecution(
            command=command,
            target_ref=f"unit:{unit_id}",
            task_kind=TaskKind.AI_EDIT_EXECUTE,
            inputs=tuple(inputs),
            transitions=tuple(
                {
                    "clipId": clip_id,
                    "kind": plan.timeline.items[clip_id].transition,
                }
                for clip_id in plan.timeline.order
            ),
            audio_plan=plan.audio_plan.model_dump(mode="json"),
            expected_duration_seconds=round(duration, 6),
            slot_id=f"unit:{unit_id}:video",
            slot_kind="unit_video",
            owner_ref=f"unit:{unit_id}",
            artifact_name=f"{unit.title or unit_id} AI 剪辑成片",
            read_set=tuple(read_set),
            source_selections=(),
            edit_plan_id=plan.plan_id,
            edit_plan_hash=plan.plan_hash,
        )
    if command is CreatorCommandType.STITCH_SECTION:
        section_id = _target_id(target_ref, "post")
        section = _find_section(project, section_id)
        return _composition_execution(
            project=project,
            command=command,
            target_ref=f"post:{section_id}",
            composition=project.post_production.sections_by_id.get(section_id),
            owner_ref=f"section:{section_id}",
            slot_id=f"section:{section_id}:video",
            slot_kind="section_video",
            artifact_name=f"{section.title or section_id} 合成视频",
        )
    if command is CreatorCommandType.COMPOSE_FINAL_VIDEO:
        if target_ref != "post:final":
            raise ValidationError(
                "COMPOSE_FINAL_VIDEO targetRef 必须是 post:final",
            )
        return _composition_execution(
            project=project,
            command=command,
            target_ref="post:final",
            composition=project.post_production.final,
            owner_ref=f"project:{project.project_id}",
            slot_id="project:final:video",
            slot_kind="final_video",
            artifact_name=f"{project.name} 最终成片",
        )
    raise ValidationError(f"不支持的本地媒体命令: {command.value}")


def _resolved_fingerprint(
    resolved: _ResolvedExecution,
    *,
    generation: int,
    etag: str,
) -> str:
    return _fingerprint(
        {
            "command": resolved.command.value,
            "targetRef": resolved.target_ref,
            "inputs": [
                {
                    "versionId": item.version_id,
                    "fileId": (
                        item.indexed.file_id
                        if item.indexed is not None
                        else None
                    ),
                    "checksum": item.checksum,
                    "sourceUrl": item.source_url,
                    "sourceRef": item.source_ref,
                    "start": item.start_seconds,
                    "end": item.end_seconds,
                    "originalSound": item.original_sound,
                    "overlay": item.overlay,
                }
                for item in resolved.inputs
            ],
            "transitions": list(resolved.transitions),
            "audioPlan": resolved.audio_plan,
            "editPlanId": resolved.edit_plan_id,
            "editPlanHash": resolved.edit_plan_hash,
            "inputGeneration": generation,
            "inputEtag": etag,
        },
    )


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _terminal_task_message(task: TaskRecord) -> str:
    message = f"本地媒体 Task 已终止: {task.status.value}"
    if isinstance(task.error, Mapping):
        detail = str(task.error.get("message") or "").strip()
        if detail and detail != message:
            message = f"{message}: {detail}"
    return message


class FileLocalMediaExecutionService:
    """Convergent Run/Task worker for local edit and compose execution."""

    def __init__(
        self,
        services: CreatorFileServices,
        *,
        runner: LocalMediaRunner | None = None,
        max_output_bytes: int = _MAX_VIDEO_BYTES,
    ) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.services = services
        self.runner = runner or FfmpegLocalMediaRunner()
        self.executions = ProjectExecutionStore(services.root)
        self.max_output_bytes = max_output_bytes
        self._closed = False

    async def execute(
        self,
        *,
        project_id: str,
        command: CreatorCommandType | str,
        target_ref: str,
        arguments: Mapping[str, Any],
        idempotency_key: str,
        expected_object_versions: Sequence[str] = (),
    ) -> FileLocalMediaExecutionResult:
        if self._closed:
            raise ConflictError("本地媒体执行服务正在关闭")
        command_value = CreatorCommandType(command)
        if command_value not in _LOCAL_MEDIA_COMMANDS:
            raise ValidationError(f"不支持的文件本地媒体命令: {command_value.value}")
        ids = self._ids(project_id, idempotency_key)
        command_request_hash = _fingerprint(
            {
                "command": command_value.value,
                "targetRef": target_ref,
                "arguments": dict(arguments),
            },
        )
        try:
            existing_task = await asyncio.to_thread(
                self.executions.get_task,
                project_id,
                ids["task_id"],
            )
        except RecordNotFoundError:
            existing_task = None
        if existing_task is not None:
            self._assert_command_replay(
                existing_task,
                command=command_value,
                target_ref=target_ref,
                command_request_hash=command_request_hash,
            )
            if existing_task.status is TaskStatus.SUCCEEDED:
                return self._result_from_task(existing_task, replayed=True)
            if existing_task.status in {
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.QUARANTINED,
            }:
                raise ConflictError(_terminal_task_message(existing_task))
            if existing_task.status is TaskStatus.RUNNING:
                if existing_task.result is None:
                    raise ConflictError("本地媒体 Task 已由另一个执行者领取")
                return await self._converge(
                    task=existing_task,
                    ids=ids,
                    replayed=True,
                )

        base = await asyncio.to_thread(self.services.projects.read, project_id)
        if any(
            f"project:{base.etag}:" not in value
            for value in expected_object_versions
        ):
            raise ConflictError("本地媒体命令目标已被其他写者修改")
        resolved = await asyncio.to_thread(
            _resolve_execution,
            snapshot=base,
            command=command_value,
            target_ref=target_ref,
            arguments=dict(arguments),
        )
        request_fingerprint = _resolved_fingerprint(
            resolved,
            generation=base.generation,
            etag=base.etag,
        )
        run, task = await self._admit(
            base=base,
            resolved=resolved,
            request_fingerprint=request_fingerprint,
            command_request_hash=command_request_hash,
            idempotency_key=idempotency_key,
            ids=ids,
        )
        if task.status is TaskStatus.SUCCEEDED:
            return self._result_from_task(task, replayed=True)
        if task.status in {
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.QUARANTINED,
        }:
            raise ConflictError(_terminal_task_message(task))
        if task.status is TaskStatus.RUNNING and task.result is not None:
            return await self._converge(task=task, ids=ids, replayed=True)

        task = await self._start(
            run=run,
            task=task,
            resolved=resolved,
            ids=ids,
        )
        if not await self._claim_runner(task):
            raise ConflictError("本地媒体 Task 已由另一个执行者领取")
        try:
            spec = await asyncio.to_thread(
                self._prepare_spec,
                base,
                resolved,
                task,
            )
            runner_output = await self.runner.render(spec)
            published_result = await asyncio.to_thread(
                self._materialize_and_publish,
                base,
                resolved,
                task,
                ids,
                spec,
                runner_output,
            )
            latest = await asyncio.to_thread(
                self.executions.get_task,
                project_id,
                task.task_id,
            )
            if latest.status is TaskStatus.CANCELLED:
                await self._quarantine(
                    task=latest,
                    ids=ids,
                    reason="TASK_CANCELLED_BEFORE_IMPORT",
                    result=published_result,
                    run_status=SpecialistRunStatus.CANCELLED,
                )
                raise ConflictError("本地媒体 Task 已取消，迟到结果已隔离")
            try:
                task = await asyncio.to_thread(
                    self.executions.transition_task,
                    project_id,
                    task.task_id,
                    expected_status=TaskStatus.RUNNING,
                    status=TaskStatus.RUNNING,
                    updates={
                        "progress": max(0.9, latest.progress or 0.0),
                        "result": published_result,
                        "output_refs": [
                            f"artifact-version:{ids['artifact_version_id']}",
                        ],
                    },
                )
            except ExecutionStateConflict:
                latest = await asyncio.to_thread(
                    self.executions.get_task,
                    project_id,
                    task.task_id,
                )
                if latest.status is not TaskStatus.CANCELLED:
                    raise
                await self._quarantine(
                    task=latest,
                    ids=ids,
                    reason="TASK_CANCELLED_BEFORE_IMPORT",
                    result=published_result,
                    run_status=SpecialistRunStatus.CANCELLED,
                )
                raise ConflictError("本地媒体 Task 已取消，迟到结果已隔离")
            return await self._converge(task=task, ids=ids, replayed=False)
        except (ConflictError, ValidationError, StorageIntegrityError) as exc:
            await self._fail_if_running(
                project_id,
                ids,
                "LOCAL_MEDIA_EXECUTION_FAILED",
                message=str(exc),
            )
            raise
        except AssetFileError as exc:
            await self._fail_if_running(
                project_id,
                ids,
                "LOCAL_MEDIA_EXECUTION_FAILED",
                message=str(exc),
            )
            raise StorageIntegrityError(str(exc)) from exc
        except Exception as exc:
            await self._fail_if_running(
                project_id,
                ids,
                "LOCAL_MEDIA_EXECUTION_FAILED",
                message=str(exc),
            )
            raise StorageIntegrityError(f"本地媒体执行失败: {exc}") from exc

    @staticmethod
    def _ids(project_id: str, key: str) -> dict[str, str]:
        return {
            "run_id": _stable_id("run", project_id, key),
            "round_id": _stable_id("round", project_id, key),
            "task_id": _stable_id("task", project_id, key),
            "attempt_id": _stable_id("attempt", project_id, key),
            "attempt_started_event_id": _stable_id(
                "attempt-started",
                project_id,
                key,
            ),
            "attempt_succeeded_event_id": _stable_id(
                "attempt-succeeded",
                project_id,
                key,
            ),
            "attempt_failed_event_id": _stable_id(
                "attempt-failed",
                project_id,
                key,
            ),
            "attempt_quarantined_event_id": _stable_id(
                "attempt-quarantined",
                project_id,
                key,
            ),
            "file_id": _stable_id("file", project_id, key),
            "artifact_version_id": _stable_id(
                "artifact-version",
                project_id,
                key,
            ),
            "transaction_id": _stable_id("media-transaction", project_id, key),
            "quarantine_id": _stable_id("quarantine", project_id, key),
        }

    async def _admit(
        self,
        *,
        base: ProjectSnapshot,
        resolved: _ResolvedExecution,
        request_fingerprint: str,
        command_request_hash: str,
        idempotency_key: str,
        ids: Mapping[str, str],
    ) -> tuple[SpecialistRunRecord, TaskRecord]:
        metadata = {
            "commandType": resolved.command.value,
            "targetRef": resolved.target_ref,
            "commandRequestHash": command_request_hash,
            "slotId": resolved.slot_id,
            "artifactVersionId": ids["artifact_version_id"],
            "fileId": ids["file_id"],
        }
        run_candidate = SpecialistRunRecord(
            run_id=ids["run_id"],
            project_id=base.project.project_id,
            round_id=ids["round_id"],
            role=SpecialistRole.AI_EDITING_DIRECTOR,
            target_refs=[resolved.target_ref],
            input_generation=base.generation,
            input_etag=base.etag,
            request_fingerprint=request_fingerprint,
            read_set=list(resolved.read_set),
            caused_by_request_id=idempotency_key,
            review_policy=ReviewPolicy.AUTO_FIX,
            metadata=metadata,
        )
        try:
            run = await asyncio.to_thread(
                self.executions.get_run,
                base.project.project_id,
                ids["run_id"],
            )
        except RecordNotFoundError:
            run = await asyncio.to_thread(
                self.executions.create_run,
                run_candidate,
            )
        if (
            run.request_fingerprint != request_fingerprint
            or run.input_etag != base.etag
            or run.target_refs != [resolved.target_ref]
        ):
            raise ConflictError("Idempotency-Key 已用于不同的本地媒体 Run")
        task_candidate = TaskRecord(
            task_id=ids["task_id"],
            project_id=base.project.project_id,
            round_id=ids["round_id"],
            run_id=ids["run_id"],
            kind=resolved.task_kind,
            request_fingerprint=request_fingerprint,
            idempotency_key=idempotency_key,
            input_generation=base.generation,
            input_etag=base.etag,
            expected_target_version=base.etag,
            input_refs=[
                resolved.target_ref,
                *(item.version_id for item in resolved.inputs),
            ],
            read_set=list(resolved.read_set),
            caused_by_request_id=idempotency_key,
            review_policy=ReviewPolicy.AUTO_FIX,
            metadata=metadata,
        )
        try:
            task = await asyncio.to_thread(
                self.executions.get_task,
                base.project.project_id,
                ids["task_id"],
            )
        except RecordNotFoundError:
            try:
                task = await asyncio.to_thread(
                    self.executions.create_task,
                    task_candidate,
                )
            except (ExecutionPayloadConflict, ExecutionStateConflict) as exc:
                raise ConflictError(str(exc)) from exc
        if (
            task.request_fingerprint != request_fingerprint
            or task.input_etag != base.etag
            or task.input_refs != task_candidate.input_refs
        ):
            raise ConflictError("Idempotency-Key 已用于不同的本地媒体 Task")
        return run, task

    @staticmethod
    def _assert_command_replay(
        task: TaskRecord,
        *,
        command: CreatorCommandType,
        target_ref: str,
        command_request_hash: str,
    ) -> None:
        if (
            task.metadata.get("commandType") != command.value
            or task.metadata.get("targetRef") != target_ref
            or task.metadata.get("commandRequestHash") != command_request_hash
        ):
            raise ConflictError("Idempotency-Key 已用于不同的本地媒体命令")

    async def _claim_runner(self, task: TaskRecord) -> bool:
        claim = {
            "taskId": task.task_id,
            "requestFingerprint": task.request_fingerprint,
            "claimedAt": datetime.now(UTC).isoformat(),
        }

        def claim_sync():
            with self.services.projects.lifecycle_lock(task.project_id):
                self.services.projects.read(task.project_id)
                project_root = self.services.projects.project_root(
                    task.project_id,
                )
                task_root = _ensure_real_directory_chain(
                    project_root,
                    "runtime",
                    "tasks",
                    task.task_id,
                )
                claim_store = AtomicJsonRecordStore(
                    task_root / "runner-claim.json",
                )
                created = claim_store.try_create(claim)
                existing = None if created is not None else claim_store.read()
                return created, existing

        created, existing = await asyncio.to_thread(claim_sync)
        if created is not None:
            return True
        assert isinstance(existing, dict)
        if (
            existing.get("taskId") != task.task_id
            or existing.get("requestFingerprint") != task.request_fingerprint
        ):
            raise StorageIntegrityError("本地媒体 runner claim 内容损坏")
        return False

    async def _start(
        self,
        *,
        run: SpecialistRunRecord,
        task: TaskRecord,
        resolved: _ResolvedExecution,
        ids: Mapping[str, str],
    ) -> TaskRecord:
        project_id = task.project_id
        if run.status in {
            SpecialistRunStatus.QUEUED,
            SpecialistRunStatus.QUEUED_CAPACITY,
        }:
            run = await asyncio.to_thread(
                self.executions.transition_run,
                project_id,
                run.run_id,
                expected_status=run.status,
                status=SpecialistRunStatus.RUNNING_MODEL,
            )
        if task.status is TaskStatus.QUEUED:
            await asyncio.to_thread(
                self.executions.append_attempt,
                project_id,
                task.task_id,
                event_id=ids["attempt_started_event_id"],
                attempt_id=ids["attempt_id"],
                status=TaskAttemptStatus.RUNNING,
                input={
                    "command": resolved.command.value,
                    "targetRef": resolved.target_ref,
                    "inputs": [
                        {
                            "versionId": item.version_id,
                            "fileId": (
                                item.indexed.file_id
                                if item.indexed is not None
                                else None
                            ),
                            "checksum": item.checksum,
                            "sourceUrl": item.source_url,
                            "start": item.start_seconds,
                            "end": item.end_seconds,
                        }
                        for item in resolved.inputs
                    ],
                    "artifactVersionId": ids["artifact_version_id"],
                },
            )
            task = await asyncio.to_thread(
                self.executions.get_task,
                project_id,
                task.task_id,
            )
        if run.status is SpecialistRunStatus.RUNNING_MODEL:
            await asyncio.to_thread(
                self.executions.transition_run,
                project_id,
                run.run_id,
                expected_status=SpecialistRunStatus.RUNNING_MODEL,
                status=SpecialistRunStatus.WAITING_RUNTIME,
            )
        return task

    def _prepare_spec(
        self,
        base: ProjectSnapshot,
        resolved: _ResolvedExecution,
        task: TaskRecord,
    ) -> LocalMediaExecutionSpec:
        project_root = self.services.projects.project_root(
            base.project.project_id,
        )
        work_dir = _ensure_real_directory_chain(
            project_root,
            "runtime",
            "task-work",
            task.task_id,
        )
        input_dir = _ensure_real_directory_chain(work_dir, "inputs")
        file_store = AssetFileStore(project_root)
        local_inputs: list[LocalMediaInput] = []
        prepared_paths: dict[tuple[str, str, str], Path] = {}
        runtime_tasks = (
            self.executions.list_tasks(base.project.project_id)
            if any(item.source_url is not None for item in resolved.inputs)
            else []
        )
        for frozen in resolved.inputs:
            location_identity = (
                frozen.indexed.file_id
                if frozen.indexed is not None
                else str(frozen.source_url or "")
            )
            input_identity = (
                frozen.version_id,
                frozen.checksum,
                location_identity,
            )
            destination = prepared_paths.get(input_identity)
            suffix = mimetypes.guess_extension(frozen.media_type) or ".mp4"
            if not suffix.startswith(".") or len(suffix) > 12:
                suffix = ".mp4"
            if destination is None:
                destination = input_dir / (
                    f"{len(prepared_paths):06d}-{frozen.version_id}{suffix}"
                )
                if destination.exists():
                    raise StorageIntegrityError("Task input scratch 已存在")
                if frozen.indexed is not None:
                    with (
                        file_store.open_verified(frozen.indexed) as source,
                        destination.open("xb") as target,
                    ):
                        shutil.copyfileobj(source, target, length=1024 * 1024)
                        target.flush()
                        os.fsync(target.fileno())
                elif frozen.source_url is not None:
                    source_version = (
                        base.project.assets.source_versions_by_id.get(
                            frozen.version_id,
                        )
                    )
                    cached = (
                        resolve_remote_cache(
                            project_root,
                            source_version,
                            runtime_tasks,
                        )
                        if source_version is not None
                        else None
                    )
                    if cached is not None:
                        destination = cached.path
                    else:
                        download_remote_file(
                            frozen.source_url,
                            str(destination),
                        )
                else:
                    raise StorageIntegrityError(
                        f"媒体输入缺少本地文件与公网 URL: {frozen.version_id}",
                    )
                prepared_paths[input_identity] = destination
            local_inputs.append(
                LocalMediaInput(
                    version_id=frozen.version_id,
                    file_id=(
                        frozen.indexed.file_id
                        if frozen.indexed is not None
                        else None
                    ),
                    checksum=frozen.checksum,
                    media_type=frozen.media_type,
                    path=destination,
                    source_ref=frozen.source_ref,
                    start_seconds=frozen.start_seconds,
                    end_seconds=frozen.end_seconds,
                    duration_seconds=frozen.duration_seconds,
                    original_sound=frozen.original_sound,
                    overlay=frozen.overlay,
                ),
            )
        output_path = work_dir / "output.mp4"
        if output_path.exists():
            raise StorageIntegrityError("Task output scratch 已存在")

        def on_clip_done(done: int, total: int) -> None:
            if total <= 0:
                return
            try:
                self.executions.transition_task(
                    base.project.project_id,
                    task.task_id,
                    expected_status=TaskStatus.RUNNING,
                    status=TaskStatus.RUNNING,
                    updates={"progress": done / total},
                )
            except ExecutionStateConflict:
                # Cancellation or another terminal transition won the Runtime
                # lock; the renderer will observe that state before import.
                return

        spec = LocalMediaExecutionSpec(
            command=resolved.command,
            target_ref=resolved.target_ref,
            task_id=task.task_id,
            work_dir=work_dir,
            output_path=output_path,
            inputs=tuple(local_inputs),
            transitions=resolved.transitions,
            audio_plan=resolved.audio_plan,
            expected_duration_seconds=resolved.expected_duration_seconds,
            on_clip_done=(
                on_clip_done
                if resolved.command is CreatorCommandType.EXECUTE_EDIT
                else None
            ),
        )
        AtomicJsonRecordStore(work_dir / "spec.json").write(
            {
                "taskId": task.task_id,
                "command": resolved.command.value,
                "targetRef": resolved.target_ref,
                "inputGeneration": base.generation,
                "inputEtag": base.etag,
                "inputs": [
                    {
                        "versionId": item.version_id,
                        "fileId": item.file_id,
                        "checksum": item.checksum,
                        "path": item.path.relative_to(project_root).as_posix(),
                        "start": item.start_seconds,
                        "end": item.end_seconds,
                        "originalSound": item.original_sound,
                        "overlay": item.overlay,
                    }
                    for item in local_inputs
                ],
                "outputPath": output_path.relative_to(project_root).as_posix(),
            },
        )
        return spec

    def _materialize_and_publish(
        self,
        base: ProjectSnapshot,
        resolved: _ResolvedExecution,
        task: TaskRecord,
        ids: Mapping[str, str],
        spec: LocalMediaExecutionSpec,
        runner_output: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            output_stat = spec.output_path.lstat()
        except FileNotFoundError as exc:
            raise ValidationError("本地媒体 runner 未生成 output.mp4") from exc
        if spec.output_path.is_symlink() or not stat.S_ISREG(
            output_stat.st_mode,
        ):
            raise StorageIntegrityError("本地媒体输出不是普通文件")
        resolved_output = spec.output_path.resolve(strict=True)
        if not resolved_output.is_relative_to(
            spec.work_dir.resolve(strict=True),
        ):
            raise StorageIntegrityError("本地媒体输出逃逸 task-work")
        if (
            output_stat.st_size <= 0
            or output_stat.st_size > self.max_output_bytes
        ):
            raise ValidationError("本地媒体输出为空或超过大小限制")
        file_store = AssetFileStore(
            self.services.projects.project_root(base.project.project_id),
        )
        with spec.output_path.open("rb") as stream:
            staged = file_store.stage_stream(
                stream,
                staging_id=task.task_id[:80],
            )
        relative_uri = PurePosixPath(
            "assets",
            "artifacts",
            f"{ids['file_id']}.mp4",
        ).as_posix()
        indexed = IndexedFile(
            file_id=ids["file_id"],
            kind="artifact_payload",
            relative_uri=relative_uri,
            sha256=staged.sha256,
            size_bytes=staged.size_bytes,
            media_type="video/mp4",
            created_at=datetime.now(UTC),
        )
        try:
            file_store.publish(
                staged,
                relative_uri,
                expected_sha256=staged.sha256,
                expected_size_bytes=staged.size_bytes,
            )
        except AssetAlreadyExists:
            file_store.abandon(staged)
            if not file_store.inspect(indexed).available:
                raise StorageIntegrityError("稳定本地媒体输出路径已存在但内容不同")
        metadata = {
            "taskId": task.task_id,
            "runId": task.run_id,
            "commandType": resolved.command.value,
            "sourceSelections": list(resolved.source_selections),
            "runner": _json_mapping(runner_output.get("metadata")),
        }
        if resolved.edit_plan_id is not None:
            metadata.update(
                {
                    "editPlanId": resolved.edit_plan_id,
                    "editPlanHash": resolved.edit_plan_hash,
                },
            )
        reported_duration = runner_output.get("duration_seconds")
        duration = (
            float(reported_duration)
            if isinstance(reported_duration, (int, float))
            and not isinstance(reported_duration, bool)
            and float(reported_duration) >= 0
            else resolved.expected_duration_seconds
        )
        artifact = ArtifactVersion(
            version_id=ids["artifact_version_id"],
            slot_id=resolved.slot_id,
            kind=resolved.slot_kind,
            owner_ref=resolved.owner_ref,
            name=resolved.artifact_name,
            file_id=indexed.file_id,
            checksum=indexed.sha256,
            based_on_generation=task.input_generation or base.generation,
            provenance_refs=[str(item["ref"]) for item in resolved.read_set],
            duration_seconds=duration,
            input_fingerprint=task.request_fingerprint,
            created_at=indexed.created_at,
            metadata=metadata,
        )
        return {
            "taskId": task.task_id,
            "runId": task.run_id,
            "transactionId": ids["transaction_id"],
            "commandType": resolved.command.value,
            "targetRef": resolved.target_ref,
            "indexedFile": indexed.model_dump(mode="json"),
            "artifactVersion": artifact.model_dump(mode="json"),
            "outputRef": f"artifact-version:{artifact.version_id}",
        }

    async def _converge(
        self,
        *,
        task: TaskRecord,
        ids: Mapping[str, str],
        replayed: bool,
    ) -> FileLocalMediaExecutionResult:
        if not isinstance(task.result, dict):
            raise StorageIntegrityError("RUNNING 本地媒体 Task 缺少可重放 result")
        result = dict(task.result)

        def commit_if_live() -> tuple[str, TaskRecord, ProjectSnapshot | None]:
            # Cancellation and Project import share this lifecycle boundary.
            # A cancel that wins the lock leaves Project untouched; once this
            # finalizer wins, Project commit and Task success become one
            # indivisible decision from every other Project-scoped writer's
            # point of view.
            with self.services.projects.lifecycle_lock(task.project_id):
                latest = self.executions.get_task(
                    task.project_id,
                    task.task_id,
                    _lifecycle_lock_held=True,
                )
                if latest.status is TaskStatus.CANCELLED:
                    return "CANCELLED", latest, None
                if latest.status in {
                    TaskStatus.FAILED,
                    TaskStatus.QUARANTINED,
                }:
                    return latest.status.value, latest, None
                current = self.services.projects.read(task.project_id)
                if self._result_is_converged(current.project, result):
                    snapshot = current
                elif (
                    current.etag != latest.input_etag
                    or current.generation != latest.input_generation
                ):
                    return "STALE", latest, current
                else:
                    candidate = current.project.model_dump(mode="json")
                    self._apply_result(candidate, result)
                    commit = self.services.commits.commit(
                        base=current,
                        candidate=candidate,
                        origin=ChangeOrigin.RUNTIME_TASK,
                        review_policy=ReviewPolicy.AUTO_FIX,
                        caused_by_request_id=latest.caused_by_request_id,
                        round_id=ids["round_id"],
                        transaction_id=ids["transaction_id"],
                        advance_accepted_baseline=True,
                        _lifecycle_lock_held=True,
                    )
                    snapshot = commit.snapshot
                success = {
                    **result,
                    "projectEtag": snapshot.etag,
                    "projectGeneration": snapshot.generation,
                }
                if latest.status is TaskStatus.RUNNING:
                    self.executions.append_attempt(
                        task.project_id,
                        task.task_id,
                        event_id=ids["attempt_succeeded_event_id"],
                        attempt_id=ids["attempt_id"],
                        status=TaskAttemptStatus.SUCCEEDED,
                        output=success,
                        output_refs=[str(success["outputRef"])],
                        _lifecycle_lock_held=True,
                    )
                    latest = self.executions.get_task(
                        task.project_id,
                        task.task_id,
                        _lifecycle_lock_held=True,
                    )
                return "SUCCEEDED", latest, snapshot

        outcome, current_task, snapshot = await asyncio.to_thread(
            commit_if_live,
        )
        if outcome == "CANCELLED":
            await self._quarantine(
                task=current_task,
                ids=ids,
                reason="TASK_CANCELLED_BEFORE_IMPORT",
                result=result,
                run_status=SpecialistRunStatus.CANCELLED,
            )
            raise ConflictError("本地媒体 Task 已取消，迟到结果已隔离")
        if outcome == "STALE":
            await self._quarantine(
                task=current_task,
                ids=ids,
                reason="PROJECT_INPUT_SNAPSHOT_STALE",
                result=result,
                run_status=SpecialistRunStatus.STALE,
            )
            raise ConflictError("本地媒体执行期间 Project 已变化，结果已隔离")
        if outcome != "SUCCEEDED" or snapshot is None:
            raise ConflictError(f"本地媒体 Task 已终止: {outcome}")
        await asyncio.to_thread(self.services.poller.note_commit, snapshot)
        success = (
            current_task.result
            if isinstance(current_task.result, dict)
            else {
                **result,
                "projectEtag": snapshot.etag,
                "projectGeneration": snapshot.generation,
            }
        )
        artifact = ArtifactVersion.model_validate(success["artifactVersion"])
        await self._finish_run(
            task.project_id,
            ids["run_id"],
            SpecialistRunStatus.SUCCEEDED,
            summary=f"已生成并选择 {artifact.name}",
        )
        return self._result_from_task(current_task, replayed=replayed)

    @staticmethod
    def _result_is_converged(
        project: Project,
        result: Mapping[str, Any],
    ) -> bool:
        try:
            indexed = IndexedFile.model_validate(result["indexedFile"])
            artifact = ArtifactVersion.model_validate(
                result["artifactVersion"],
            )
            command = CreatorCommandType(str(result["commandType"]))
            target_ref = str(result["targetRef"])
        except (KeyError, TypeError, ValueError):
            return False
        slot = project.assets.artifact_slots_by_id.get(artifact.slot_id)
        if (
            project.assets.files_by_id.get(indexed.file_id) != indexed
            or project.assets.artifact_versions_by_id.get(artifact.version_id)
            != artifact
            or slot is None
            or slot.selected_version_id != artifact.version_id
        ):
            return False
        if command is CreatorCommandType.EXECUTE_EDIT:
            unit_id = _target_id(target_ref, "unit")
            production = project.production.units_by_id.get(unit_id)
            return (
                isinstance(production, EditProduction)
                and production.rendered_video_artifact_version_id
                == artifact.version_id
            )
        if command is CreatorCommandType.STITCH_SECTION:
            section_id = _target_id(target_ref, "post")
            composition = project.post_production.sections_by_id.get(
                section_id,
            )
        else:
            composition = project.post_production.final
        return (
            composition is not None
            and composition.rendered_video_artifact_version_id
            == artifact.version_id
        )

    @staticmethod
    def _apply_result(
        candidate: dict[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        indexed = IndexedFile.model_validate(result["indexedFile"])
        artifact = ArtifactVersion.model_validate(result["artifactVersion"])
        assets = candidate["assets"]
        indexed_json = indexed.model_dump(mode="json")
        artifact_json = artifact.model_dump(mode="json")
        existing_file = assets["files_by_id"].get(indexed.file_id)
        if existing_file is not None and existing_file != indexed_json:
            raise ConflictError("本地媒体 IndexedFile 稳定 ID 内容冲突")
        existing_version = assets["artifact_versions_by_id"].get(
            artifact.version_id,
        )
        if existing_version is not None and existing_version != artifact_json:
            raise ConflictError("本地媒体 ArtifactVersion 稳定 ID 内容冲突")
        assets["files_by_id"][indexed.file_id] = indexed_json
        assets["artifact_versions_by_id"][artifact.version_id] = artifact_json
        raw_slot = assets["artifact_slots_by_id"].get(artifact.slot_id)
        if raw_slot is None:
            raw_slot = ArtifactSlot(
                slot_id=artifact.slot_id,
                kind=artifact.kind,
                owner_ref=artifact.owner_ref,
                version_ids=[artifact.version_id],
                selected_version_id=artifact.version_id,
            ).model_dump(mode="json")
            assets["artifact_slots_by_id"][artifact.slot_id] = raw_slot
        else:
            if (
                raw_slot["kind"] != artifact.kind
                or raw_slot["owner_ref"] != artifact.owner_ref
            ):
                raise ConflictError("本地媒体 ArtifactSlot 归属冲突")
            if artifact.version_id not in raw_slot["version_ids"]:
                raw_slot["version_ids"].append(artifact.version_id)
            raw_slot["selected_version_id"] = artifact.version_id
        command = CreatorCommandType(str(result["commandType"]))
        target_ref = str(result["targetRef"])
        if command is CreatorCommandType.EXECUTE_EDIT:
            unit_id = _target_id(target_ref, "unit")
            production = candidate["production"]["units_by_id"].get(unit_id)
            if production is None or production.get("route") != "edit":
                raise ConflictError("EditProduction 已不存在")
            production[
                "rendered_video_artifact_version_id"
            ] = artifact.version_id
            return
        if command is CreatorCommandType.STITCH_SECTION:
            section_id = _target_id(target_ref, "post")
            composition = candidate["post_production"]["sections_by_id"].get(
                section_id,
            )
        else:
            composition = candidate["post_production"].get("final")
        if composition is None:
            raise ConflictError("Composition 已不存在")
        composition["rendered_video_artifact_version_id"] = artifact.version_id

    async def _quarantine(
        self,
        *,
        task: TaskRecord,
        ids: Mapping[str, str],
        reason: str,
        result: Mapping[str, Any],
        run_status: SpecialistRunStatus,
    ) -> None:
        latest = await asyncio.to_thread(
            self.executions.get_task,
            task.project_id,
            task.task_id,
        )
        if latest.status is TaskStatus.RUNNING:
            try:
                await asyncio.to_thread(
                    self.executions.append_attempt,
                    task.project_id,
                    task.task_id,
                    event_id=ids["attempt_quarantined_event_id"],
                    attempt_id=ids["attempt_id"],
                    status=TaskAttemptStatus.QUARANTINED,
                    output=dict(result),
                    output_refs=[str(result.get("outputRef") or "")],
                    error={"code": reason, "message": reason},
                )
            except ExecutionStateConflict:
                pass
        await asyncio.to_thread(
            self.executions.quarantine_task_result,
            task.project_id,
            task.task_id,
            reason=reason,
            result=dict(result),
            quarantine_id=ids["quarantine_id"],
            transition_task=False,
        )
        await self._finish_run(task.project_id, ids["run_id"], run_status)

    async def _fail_if_running(
        self,
        project_id: str,
        ids: Mapping[str, str],
        code: str,
        *,
        message: str | None = None,
    ) -> None:
        try:
            task = await asyncio.to_thread(
                self.executions.get_task,
                project_id,
                ids["task_id"],
            )
        except RecordNotFoundError:
            return
        if task.status is TaskStatus.RUNNING:
            try:
                await asyncio.to_thread(
                    self.executions.append_attempt,
                    project_id,
                    task.task_id,
                    event_id=ids["attempt_failed_event_id"],
                    attempt_id=ids["attempt_id"],
                    status=TaskAttemptStatus.FAILED,
                    error={"code": code, "message": message or code},
                )
            except ExecutionStateConflict:
                pass
        await self._finish_run(
            project_id,
            ids["run_id"],
            SpecialistRunStatus.FAILED,
        )

    async def _finish_run(
        self,
        project_id: str,
        run_id: str,
        status: SpecialistRunStatus,
        *,
        summary: str | None = None,
    ) -> None:
        try:
            run = await asyncio.to_thread(
                self.executions.get_run,
                project_id,
                run_id,
            )
        except RecordNotFoundError:
            return
        if run.status in {
            SpecialistRunStatus.SUCCEEDED,
            SpecialistRunStatus.BLOCKED,
            SpecialistRunStatus.FAILED,
            SpecialistRunStatus.STALE,
            SpecialistRunStatus.CANCELLED,
        }:
            return
        try:
            await asyncio.to_thread(
                self.executions.transition_run,
                project_id,
                run_id,
                expected_status=run.status,
                status=status,
                updates={"final_summary_text": summary} if summary else None,
            )
        except ExecutionStateConflict:
            return

    async def recover_project(self, project_id: str) -> list[str]:
        """Recover local-media Tasks after process restart.

        A RUNNING Task with a durable published result converges normally (or
        quarantines if its frozen Project input is stale).  A RUNNING Task
        without a result, and any never-started QUEUED Task, is failed closed:
        restarting ffmpeg implicitly could duplicate side effects or consume a
        partial scratch output.  A new command/idempotency key is then required.
        """

        recovered: list[str] = []
        for task in await asyncio.to_thread(
            self.executions.list_tasks,
            project_id,
        ):
            command_name = str(task.metadata.get("commandType") or "")
            try:
                command = CreatorCommandType(command_name)
            except ValueError:
                continue
            if command not in _LOCAL_MEDIA_COMMANDS or task.status not in {
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
            }:
                continue
            key = str(task.idempotency_key or "")
            if not key:
                continue
            ids = self._ids(project_id, key)
            if ids["task_id"] != task.task_id:
                raise StorageIntegrityError("本地媒体 Task 稳定 ID 与 key 不一致")
            if task.status is TaskStatus.RUNNING and task.result is not None:
                try:
                    await self._converge(task=task, ids=ids, replayed=True)
                except ConflictError:
                    # Stale/cancel convergence already persisted quarantine.
                    pass
                recovered.append(task.task_id)
                continue
            error = {
                "code": "LOCAL_MEDIA_PROCESS_RESTARTED",
                "message": "进程重启前本地媒体执行未形成可收敛结果",
            }
            if task.status is TaskStatus.RUNNING:
                try:
                    await asyncio.to_thread(
                        self.executions.append_attempt,
                        project_id,
                        task.task_id,
                        event_id=ids["attempt_failed_event_id"],
                        attempt_id=ids["attempt_id"],
                        status=TaskAttemptStatus.FAILED,
                        error=error,
                    )
                except ExecutionStateConflict:
                    pass
            else:
                await asyncio.to_thread(
                    self.executions.transition_task,
                    project_id,
                    task.task_id,
                    expected_status=TaskStatus.QUEUED,
                    status=TaskStatus.FAILED,
                    updates={"error": error},
                )
            await self._finish_run(
                project_id,
                ids["run_id"],
                SpecialistRunStatus.FAILED,
            )
            recovered.append(task.task_id)
        return recovered

    async def shutdown(self) -> None:
        """Stop admitting new work; in-flight request ownership stays explicit."""

        self._closed = True

    @staticmethod
    def _result_from_task(
        task: TaskRecord,
        *,
        replayed: bool,
    ) -> FileLocalMediaExecutionResult:
        result = task.result if isinstance(task.result, dict) else {}
        try:
            artifact = ArtifactVersion.model_validate(
                result["artifactVersion"],
            )
            transaction_id = str(result["transactionId"])
            project_etag = str(result["projectEtag"])
            project_generation = int(result["projectGeneration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageIntegrityError(
                "SUCCEEDED 本地媒体 Task 缺少可重放结果",
            ) from exc
        return FileLocalMediaExecutionResult(
            task_id=task.task_id,
            run_id=str(task.run_id or ""),
            transaction_id=transaction_id,
            artifact_version_id=artifact.version_id,
            project_etag=project_etag,
            project_generation=project_generation,
            replayed=replayed,
        )


async def execute_file_local_media_command(
    services: CreatorFileServices,
    *,
    project_id: str,
    command: CreatorCommandType | str,
    target_ref: str,
    arguments: Mapping[str, Any],
    idempotency_key: str,
    expected_object_versions: Sequence[str] = (),
    runner: LocalMediaRunner | None = None,
) -> FileLocalMediaExecutionResult:
    return await FileLocalMediaExecutionService(
        services,
        runner=runner,
    ).execute(
        project_id=project_id,
        command=command,
        target_ref=target_ref,
        arguments=arguments,
        idempotency_key=idempotency_key,
        expected_object_versions=expected_object_versions,
    )


async def recover_file_local_media_project(
    services: CreatorFileServices,
    project_id: str,
) -> list[str]:
    """Lifecycle hook for startup recovery of one Project's local tasks."""

    return await FileLocalMediaExecutionService(services).recover_project(
        project_id,
    )


__all__ = [
    "FileLocalMediaExecutionResult",
    "FileLocalMediaExecutionService",
    "FfmpegLocalMediaRunner",
    "LocalMediaExecutionSpec",
    "LocalMediaInput",
    "LocalMediaRunner",
    "execute_file_local_media_command",
    "recover_file_local_media_project",
]
