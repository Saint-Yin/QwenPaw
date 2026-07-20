from __future__ import annotations

from pathlib import Path

import pytest

from services.media_files import overlay as overlay_tools

pytestmark = pytest.mark.unit


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def _install_render_fakes(monkeypatch, commands: list[list[str]]) -> None:
    def render_png(*args) -> bool:
        output_path = args[-1]
        Path(output_path).write_bytes(b"png")
        return True

    def run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"video")
        return _Completed()

    monkeypatch.setattr(overlay_tools, "_render_pet_os_png", render_png)
    monkeypatch.setattr(overlay_tools, "_render_interview_summary_png", render_png)
    monkeypatch.setattr(overlay_tools.subprocess, "run", run)


def test_pet_os_renderer_uses_bubble_tool_and_requested_timing(
    monkeypatch,
    tmp_path,
) -> None:
    commands: list[list[str]] = []
    _install_render_fakes(monkeypatch, commands)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "pet.mp4"

    result = overlay_tools.render_pet_os_overlay(
        ffmpeg_path="ffmpeg",
        input_path=source,
        output_path=output,
        text="今天也好困啊",
        vibe="chill",
        video_size=(1280, 720),
        appear_at=0.5,
        duration=2.5,
    )

    assert result.success is True
    expression = commands[0][commands[0].index("-filter_complex") + 1]
    assert "between(t,0.5,3.0)" in expression
    assert not output.with_suffix(".overlay.png").exists()


def test_interview_renderer_uses_title_tool_and_requested_timing(
    monkeypatch,
    tmp_path,
) -> None:
    commands: list[list[str]] = []
    _install_render_fakes(monkeypatch, commands)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "interview.mp4"

    result = overlay_tools.render_interview_summary_overlay(
        ffmpeg_path="ffmpeg",
        input_path=source,
        output_path=output,
        text="讲述海边成长的记忆",
        video_size=(1280, 720),
        appear_at=0.0,
        duration=4.0,
    )

    assert result.success is True
    expression = commands[0][commands[0].index("-filter_complex") + 1]
    assert "between(t,0.0,4.0)" in expression
    assert not output.with_suffix(".overlay.png").exists()
