# -*- coding: utf-8 -*-
"""Whole-piece cover poster helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from services.media_files.cover_generation import (
    COVER_FILENAME,
    build_cover_prompt,
    cover_input_fingerprint,
    cover_is_current,
    poster_frame_from_video,
    render_cover_bytes,
)

_MARKER = "input_fingerprint="


def _project(**overrides):
    base = SimpleNamespace(
        name="深夜末班地铁",
        description="都市悬疑互动短剧。",
        strategy=SimpleNamespace(creative_brief="一列末班地铁，一条匿名提醒。"),
        visual=SimpleNamespace(style="写实冷调", visual_bible="金属与荧光灯"),
        interactive_presentation=SimpleNamespace(
            cover_file_id=None,
            cover_checksum=None,
            cover_fingerprint="",
        ),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_cover_filename_is_the_platform_contract() -> None:
    assert COVER_FILENAME == "cover.jpg"


def test_fingerprint_is_stable_and_input_sensitive() -> None:
    first = cover_input_fingerprint(_project())
    assert first == cover_input_fingerprint(_project())
    assert first != cover_input_fingerprint(_project(name="另一个名字"))


def test_prompt_names_the_project_and_landscape_intent() -> None:
    prompt = build_cover_prompt(_project())
    assert "深夜末班地铁" in prompt
    assert "16:9" in prompt or "横" in prompt


def test_cover_is_current_requires_matching_fingerprint() -> None:
    project = _project()
    assert cover_is_current(project) is False

    fingerprint = cover_input_fingerprint(project)
    presentation = project.interactive_presentation
    presentation.cover_file_id = "file-cover-1"
    presentation.cover_checksum = "a" * 64
    presentation.cover_fingerprint = f"{_MARKER}{fingerprint}"
    assert cover_is_current(project) is True

    presentation.cover_fingerprint = f"{_MARKER}{fingerprint}stale"
    assert cover_is_current(project) is False


def test_render_cover_bytes_raises_when_the_model_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("models.image.generate_image", _raise)
    with pytest.raises(Exception):
        asyncio.run(render_cover_bytes(_project()))


def test_poster_frame_falls_back_to_none_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "services.runtime_files.runtime_dependencies.resolve_ffmpeg",
        lambda: None,
    )
    assert poster_frame_from_video(b"not-really-a-video") is None


def test_poster_frame_requires_video_bytes() -> None:
    assert poster_frame_from_video(b"") is None
