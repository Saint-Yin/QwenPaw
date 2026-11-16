# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=protected-access
"""The published video's real duration drives the element span.

An s2v clip only lasts as long as its driving audio; publishing must
shrink the span to the delivered footage and ripple later elements.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from domain.enums import CreatorCommandType
from domain.errors import StorageIntegrityError
from services.media_files import keyframe_cache
from services.project_files.assets import AssetFileStore
from services.project_files.models import Project
from services.media_files.element_adapter import reconcile_candidate_span
from services.media_files.local_execution import (
    FfmpegLocalMediaRunner,
    LocalMediaExecutionSpec,
    LocalMediaInput,
    _caption_fallback_style_kwargs,
    _measured_output_seconds,
    _motion_document_matches_text,
    _trim_edit_chain,
)
from services.media_files.motion_blueprints import subtitle_pack_animation


def test_motion_copy_match_uses_browser_visible_html_entities() -> None:
    html = "<div><b>GitHub</b><i>&nbsp;</i><b>新手</b></div>"
    assert _motion_document_matches_text(html, "GitHub 新手")
    assert not _motion_document_matches_text(html, "GitHub 高手")


def _candidate(ticks_per_second: int = 1000) -> dict:
    return {
        "timelines": {
            "items": {
                "timeline:main": {
                    "ticks_per_second": ticks_per_second,
                    "elements_by_id": {
                        "el:talk": {
                            "span": {"start_tick": 0, "duration_tick": 5000},
                        },
                        "el:shot2": {
                            "span": {
                                "start_tick": 5000,
                                "duration_tick": 5000,
                            },
                        },
                        "el:narration2": {
                            "span": {
                                "start_tick": 5000,
                                "duration_tick": 5000,
                            },
                        },
                        # Starts inside the shrunk segment: stays put.
                        "el:overlap": {
                            "span": {
                                "start_tick": 1000,
                                "duration_tick": 1000,
                            },
                        },
                    },
                },
            },
        },
    }


def _reconcile(
    candidate: dict,
    seconds: float | None,
    element_id: str = "el:talk",
) -> bool:
    return reconcile_candidate_span(
        candidate,
        element_id=element_id,
        actual_duration_seconds=seconds,
    )


def _elements(candidate: dict) -> dict:
    return candidate["timelines"]["items"]["timeline:main"]["elements_by_id"]


def test_shorter_footage_shrinks_span_and_ripples_later_elements() -> None:
    candidate = _candidate()
    assert _reconcile(candidate, 2.8) is True
    elements = _elements(candidate)
    assert elements["el:talk"]["span"]["duration_tick"] == 2800
    # Everything that started at/after the old end moves forward together.
    assert elements["el:shot2"]["span"]["start_tick"] == 2800
    assert elements["el:narration2"]["span"]["start_tick"] == 2800
    # An element inside the shrunk window keeps its position.
    assert elements["el:overlap"]["span"]["start_tick"] == 1000
    # Replay is idempotent: the span is already reconciled.
    assert _reconcile(candidate, 2.8) is False
    assert elements["el:shot2"]["span"]["start_tick"] == 2800


def _filter(**kwargs: object) -> str:
    return FfmpegLocalMediaRunner._placement_filter(
        None,
        canvas_size=(1280, 720),
        duration_seconds=6.0,
        **kwargs,
    )


def test_freeze_pads_video_and_references_audio_only_when_present():
    chain = _filter(freeze_duration=2.0, freeze_audio=True)
    assert "tpad=stop_mode=clone:stop_duration=2.000000" in chain
    assert "[0:a]apad=pad_dur=2.000000[a]" in chain
    # Generated R2V footage usually has no audio track; referencing [0:a]
    # would make ffmpeg reject the whole filtergraph.
    silent = _filter(freeze_duration=2.0, freeze_audio=False)
    assert "tpad=stop_mode=clone:stop_duration=2.000000" in silent
    assert "[0:a]" not in silent


def test_playback_rate_retimes_picture_and_source_audio() -> None:
    chain = _filter(playback_rate=0.25, retime_audio=True)
    assert "setpts=(PTS-STARTPTS)/0.25" in chain
    assert "[0:a]atempo=0.5,atempo=0.5[a]" in chain


@pytest.mark.parametrize(
    "playback_rate",
    [0.0, -1.0, float("nan"), float("inf")],
)
def test_atempo_filters_reject_invalid_playback_rate(
    playback_rate: float,
) -> None:
    with pytest.raises(ValueError, match="finite and greater than zero"):
        FfmpegLocalMediaRunner._atempo_filters(playback_rate)


@pytest.mark.parametrize(
    "playback_rate",
    [
        float.fromhex("0x0.0000000000001p-1022"),
        float.fromhex("0x1.fffffffffffffp+1023"),
    ],
)
def test_atempo_filters_bound_extreme_finite_rates(
    playback_rate: float,
) -> None:
    with pytest.raises(ValueError, match="supported audio retiming range"):
        FfmpegLocalMediaRunner._atempo_filters(playback_rate)


_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")


@pytest.mark.skipif(
    _FFMPEG is None or _FFPROBE is None,
    reason="ffmpeg is not installed",
)
def test_still_image_input_renders_a_timed_segment(tmp_path) -> None:
    image = tmp_path / "backdrop.png"
    subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=640x360:d=0.1",
            "-frames:v",
            "1",
            str(image),
        ],
        check=True,
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output = tmp_path / "output.mp4"
    spec = LocalMediaExecutionSpec(
        command=CreatorCommandType.COMPOSE_FINAL_VIDEO,
        target_ref="timeline:main",
        task_id="task-still",
        work_dir=work_dir,
        output_path=output,
        inputs=(
            LocalMediaInput(
                version_id="artifact-version-still",
                file_id="file-still",
                checksum="sha256:still",
                media_type="image/png",
                path=image,
                source_ref="element:bg-1",
                start_seconds=0.0,
                end_seconds=2.0,
                duration_seconds=None,
            ),
        ),
        transitions=(),
        audio_plan="preserve",
        expected_duration_seconds=2.0,
        canvas_size=(640, 360),
    )
    runner = FfmpegLocalMediaRunner(_FFMPEG)
    result = asyncio.run(runner.render(spec))
    assert result["media_type"] == "video/mp4"

    assert output.exists()
    probe = subprocess.run(
        [
            _FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    assert duration == pytest.approx(2.0, abs=0.15)


@pytest.mark.skipif(
    _FFMPEG is None or _FFPROBE is None,
    reason="ffmpeg is not installed",
)
@pytest.mark.parametrize(
    ("playback_rate", "expected_duration"),
    ((0.5, 4.0), (2.0, 1.0)),
)
def test_video_playback_rate_controls_real_output_duration(
    tmp_path,
    playback_rate: float,
    expected_duration: float,
) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    rate_label = str(playback_rate).replace(".", "-")
    work_dir = tmp_path / f"work-{rate_label}"
    work_dir.mkdir()
    output = tmp_path / f"retimed-{rate_label}.mp4"
    spec = LocalMediaExecutionSpec(
        command=CreatorCommandType.COMPOSE_FINAL_VIDEO,
        target_ref="timeline:main",
        task_id=f"task-{rate_label}",
        work_dir=work_dir,
        output_path=output,
        inputs=(
            LocalMediaInput(
                version_id=f"asset-version-{rate_label}",
                file_id=f"file-{rate_label}",
                checksum=f"sha256:rate-{rate_label}-source-v1",
                media_type="video/mp4",
                path=source,
                source_ref=f"element:{rate_label}",
                start_seconds=0.0,
                end_seconds=2.0,
                duration_seconds=2.0,
                playback_rate=playback_rate,
            ),
        ),
        transitions=(),
        audio_plan="preserve",
        expected_duration_seconds=expected_duration,
        canvas_size=(640, 360),
    )

    asyncio.run(FfmpegLocalMediaRunner(_FFMPEG).render(spec))

    probe = subprocess.run(
        [
            _FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "csv=p=0",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    durations = {
        kind: float(duration)
        for kind, duration in (
            line.split(",") for line in probe.stdout.splitlines()
        )
    }
    assert durations["video"] == pytest.approx(expected_duration, abs=0.15)
    assert durations["audio"] == pytest.approx(expected_duration, abs=0.15)


def _materialize_keyframe(project_root: Path, source: Path, timestamp: float):
    return keyframe_cache.materialize_keyframe(
        project_root,
        source_path=source,
        source_identity="sha256:source",
        timestamp_seconds=timestamp,
        width=640,
        ffmpeg_path="/fake/ffmpeg",
    )


def test_materialize_keyframe_persists_and_reuses_deterministic_jpeg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project-1"
    project_root.mkdir()
    source = project_root / "source.mp4"
    source.write_bytes(b"source-video")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"JPEG@" + command[6].encode("ascii"))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(keyframe_cache.media_gate, "run", fake_run)
    first = _materialize_keyframe(project_root, source, 4.5004)
    replay = _materialize_keyframe(project_root, source, 4.5)

    assert first == replay
    assert first.path.parent == project_root / "runtime" / "keyframe-cache"
    assert first.path.suffix == ".jpg"
    assert first.path.read_bytes() == b"JPEG@4.500"
    assert first.timestamp_seconds == 4.5
    assert len(calls) == 1
    assert calls[0][0] == "/fake/ffmpeg"
    assert calls[0][5:7] == ["-ss", "4.500"]


def test_materialize_keyframe_rejects_symlink_source(
    tmp_path: Path,
    file_symlink,
) -> None:
    project_root = tmp_path / "project-1"
    project_root.mkdir()
    real_source = project_root / "real.mp4"
    real_source.write_bytes(b"source-video")
    symlink = project_root / "source.mp4"
    file_symlink(real_source, symlink)

    with pytest.raises(StorageIntegrityError, match="安全的普通文件"):
        _materialize_keyframe(project_root, symlink, 1)


@pytest.mark.skipif(_FFMPEG is None, reason="ffmpeg is not installed")
def test_real_keyframe_is_published_and_reused(tmp_path: Path) -> None:
    from PIL import Image

    project_root = tmp_path / "中文 project"
    project_root.mkdir()
    source = project_root / "源视频.mp4"
    subprocess.run(
        [
            _FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:s=640x360:d=1",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    kwargs = {
        "source_path": source,
        "source_identity": "test-source-v1",
        "timestamp_seconds": 0.5,
        "width": 320,
        "ffmpeg_path": _FFMPEG,
    }
    first = keyframe_cache.materialize_keyframe(project_root, **kwargs)
    with Image.open(first.path) as frame:
        assert frame.format == "JPEG"
        assert frame.size == (320, 180)
        frame.load()
    published_at = first.path.stat().st_mtime_ns
    assert keyframe_cache.materialize_keyframe(project_root, **kwargs) == first
    assert first.path.stat().st_mtime_ns == published_at
    assert not list(first.path.parent.glob("*.part"))


def test_keyframe_cache_rejects_directory_redirect(tmp_path, directory_link):
    project_root = tmp_path / "project-1"
    (project_root / "runtime").mkdir(parents=True)
    source = project_root / "source.mp4"
    source.write_bytes(b"source-video")
    outside = tmp_path / "outside"
    outside.mkdir()
    directory_link(outside, project_root / "runtime" / "keyframe-cache")
    with pytest.raises(StorageIntegrityError, match="安全的真实目录"):
        _materialize_keyframe(project_root, source, 1)
    assert not list(outside.iterdir())


def test_normalized_overlay_carries_the_caption_animation_pick() -> None:
    """The compose-time fallback must burn the user's entrance triple.

    Regression: ``_normalized_overlay`` used to drop
    ``caption_animation``, so every fallback caption silently reverted to
    the pack's signature motion (the field report: "the animation setting
    did nothing").
    """

    pick = {"entrance": "pop", "exit": "shrink", "loop": True}
    normalized = FfmpegLocalMediaRunner._normalized_overlay(
        {
            "kind": "pet_os",
            "text": "你好",
            "appear_at": 0.5,
            "duration": 2.0,
            "subtitle_template": "warm_note",
            "caption_animation": pick,
        },
        5.0,
    )
    assert normalized is not None
    assert normalized["caption_animation"] == pick
    kwargs = _caption_fallback_style_kwargs(normalized)
    assert kwargs["entrance"] == "pop"
    assert kwargs["exit"] == "shrink"
    assert kwargs["loop"] is True


def test_normalized_overlay_without_a_pick_keeps_the_pack_motion() -> None:
    normalized = FfmpegLocalMediaRunner._normalized_overlay(
        {
            "kind": "pet_os",
            "text": "你好",
            "appear_at": 0.0,
            "duration": 2.0,
            "subtitle_template": "warm_note",
        },
        5.0,
    )
    assert normalized is not None
    assert normalized["caption_animation"] is None
    kwargs = _caption_fallback_style_kwargs(normalized)
    expected = subtitle_pack_animation("warm_note")
    assert kwargs["entrance"] == expected["entrance"]
    assert kwargs["exit"] == expected["exit"]
    assert kwargs["loop"] == expected["loop"]


# ── Edit spans capped at the media that actually exists ──────────────────────
#
# Field shape: an imported comparison cut described two screen recordings as
# 180 s and 52 s. The prose was believed, the files were never measured, and
# the compose produced 29.918 + 52 = 81.9 s. The plan page then showed
# 03:00 + 00:52 in the rough-cut strip while the same artifact played as 1:21
# in the overview rail -- two numbers, both faithful to their own source.


def _edit_candidate(
    *,
    first_seconds: float | None,
    second_seconds: float | None,
) -> dict:
    def version(version_id: str, seconds: float | None) -> dict:
        row = {
            "version_id": version_id,
            "file_id": f"{version_id}-file",
            "media_kind": "video",
            "media_type": "video/mp4",
        }
        if seconds is not None:
            row["duration_seconds"] = seconds
        return row

    def cut(
        element_id: str,
        version_id: str,
        start: int,
        duration: int,
    ) -> dict:
        return {
            "element_id": element_id,
            "enabled": True,
            "span": {"start_tick": start, "duration_tick": duration},
            "creation": {
                "type": "edit",
                "intent": "pick",
                "original_sound": "preserve",
            },
            "render_source": {
                "type": "source_asset_version",
                "version_id": version_id,
                "source_in_tick": 0,
                "source_out_tick": duration,
                "playback_rate": 1.0,
            },
        }

    return {
        "assets": {
            "source_versions_by_id": {
                "v-qwen4": version("v-qwen4", first_seconds),
                "v-qoduck": version("v-qoduck", second_seconds),
            },
        },
        "timelines": {
            "items": {
                "timeline:main": {
                    "ticks_per_second": 1000,
                    "elements_by_id": {
                        "el-qwen4": cut("el-qwen4", "v-qwen4", 0, 180_000),
                        "el-qoduck": cut(
                            "el-qoduck",
                            "v-qoduck",
                            180_000,
                            52_000,
                        ),
                        # A caption anchored past the first cut's old end
                        # must ride the same shift, or it would burn onto
                        # footage that is no longer anywhere in the film.
                        "el-caption": {
                            "element_id": "el-caption",
                            "enabled": True,
                            "span": {
                                "start_tick": 200_000,
                                "duration_tick": 3_000,
                            },
                            "creation": {"type": "overlay", "text": "字幕"},
                        },
                    },
                },
            },
        },
    }


def _trim(candidate: dict, tmp_path: Path) -> bool:
    return _trim_edit_chain(
        candidate,
        project=Project.new(project_id="p-trim", name="trim"),
        file_store=AssetFileStore(tmp_path),
        target_ref="timeline:timeline:main",
    )


def _cut_elements(candidate: dict) -> dict:
    return candidate["timelines"]["items"]["timeline:main"]["elements_by_id"]


def test_edit_span_longer_than_its_media_is_capped_and_the_chain_closes_up(
    tmp_path: Path,
) -> None:
    candidate = _edit_candidate(first_seconds=29.918, second_seconds=54.153)
    assert _trim(candidate, tmp_path) is True
    elements = _cut_elements(candidate)
    first = elements["el-qwen4"]
    assert first["span"]["duration_tick"] == 29_918
    assert first["render_source"]["source_out_tick"] == 29_918
    second = elements["el-qoduck"]
    # Its own media is long enough, so only its position moves: the second
    # cut now starts where the shortened first one ends.
    assert second["span"]["start_tick"] == 29_918
    assert second["span"]["duration_tick"] == 52_000
    assert second["render_source"]["source_out_tick"] == 52_000
    assert elements["el-caption"]["span"]["start_tick"] == 49_918
    # The Timeline now measures what the rendered file measures.
    assert (
        max(
            item["span"]["start_tick"] + item["span"]["duration_tick"]
            for item in elements.values()
        )
        == 81_918
    )
    # Replaying costs nothing: nothing is over-long any more.
    assert _trim(candidate, tmp_path) is False


def test_media_that_fits_the_plan_is_left_untouched(tmp_path: Path) -> None:
    candidate = _edit_candidate(first_seconds=180.0, second_seconds=52.0)
    assert _trim(candidate, tmp_path) is False
    assert (
        _cut_elements(candidate)["el-qwen4"]["span"]["duration_tick"]
        == 180_000
    )


def test_unmeasured_source_is_probed_once_and_the_answer_is_stamped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A version row with no length gets one probe, then carries the number."""

    from services.media_files import local_execution

    class _Probe:
        duration_seconds = 29.918

    monkeypatch.setattr(
        local_execution,
        "probe_media",
        lambda *_args, **_kwargs: _Probe(),
    )
    monkeypatch.setattr(
        local_execution,
        "_indexed_version",
        lambda _project, version_id, **_kwargs: (
            SimpleNamespace(
                file_id=f"{version_id}-file",
                relative_uri="assets/sources/x.mp4",
            ),
            object(),
        ),
    )
    monkeypatch.setattr(
        AssetFileStore,
        "resolve_verified_path",
        lambda _self, indexed: Path(f"/tmp/{indexed.file_id}.mp4"),
    )
    candidate = _edit_candidate(first_seconds=None, second_seconds=54.153)
    assert _trim(candidate, tmp_path) is True
    row = candidate["assets"]["source_versions_by_id"]["v-qwen4"]
    assert row["duration_seconds"] == 29.918
    assert (
        _cut_elements(candidate)["el-qwen4"]["span"]["duration_tick"] == 29_918
    )

    # The stamped row means a later pass stays arithmetic: no second subprocess.
    def _no_more_probes(*_args, **_kwargs):
        raise AssertionError("re-probed an already measured source")

    monkeypatch.setattr(local_execution, "probe_media", _no_more_probes)
    assert _trim(candidate, tmp_path) is False


def test_composed_duration_is_measured_from_the_file_not_the_plan(
    monkeypatch,
    tmp_path,
) -> None:
    spec = LocalMediaExecutionSpec(
        command=CreatorCommandType.COMPOSE_FINAL_VIDEO,
        target_ref="timeline:timeline:main",
        task_id="task-1",
        work_dir=tmp_path,
        output_path=tmp_path / "final.mp4",
        inputs=(),
        transitions=(),
        audio_plan="preserve",
        expected_duration_seconds=232.0,
        canvas_size=(1280, 720),
    )

    from services.media_files import local_execution

    class _Probe:
        duration_seconds = 81.922

    monkeypatch.setattr(
        local_execution,
        "probe_media",
        lambda *_args, **_kwargs: _Probe(),
    )
    assert _measured_output_seconds(spec) == 81.922

    def _unreadable(*_args, **_kwargs):
        raise local_execution.MediaProbeError("no such file")

    monkeypatch.setattr(local_execution, "probe_media", _unreadable)
    # A file that cannot be probed keeps the planned number rather than
    # publishing a null duration every later reader has to guard against.
    assert _measured_output_seconds(spec) == 232.0
