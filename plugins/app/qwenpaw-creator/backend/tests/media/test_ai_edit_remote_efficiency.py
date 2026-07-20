from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.media.ai_edit import core


pytestmark = pytest.mark.unit

PUBLIC_URL = "https://cdn.example.com/cat-pov-1.1gb.mp4"
REMOTE_SIZE = 1_100 * 1024 * 1024


def _asset(*, version_id: str = "asset-version-current", url: str = PUBLIC_URL) -> dict[str, Any]:
    return {
        "id": "cat-video",
        "versionId": version_id,
        "name": "cat-pov.mp4",
        "category": "upload",
        "mediaType": "video",
        "url": url,
        "nativeModelUrl": PUBLIC_URL,
        "duration": 7200.0,
        "sizeBytes": REMOTE_SIZE,
    }


def _patch_execute_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        core,
        "ffmpeg_readiness",
        lambda: {"status": "ok", "path": "/usr/bin/ffmpeg", "blockers": []},
    )
    monkeypatch.setattr(core, "ensure_task_work_subdir", lambda *_parts: tmp_path)
    monkeypatch.setattr(core, "media_url_for", lambda path: f"/generated/{Path(path).name}")
    monkeypatch.setattr(core.uuid, "uuid4", lambda: SimpleNamespace(hex="1234567890abcdef"))

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **_kwargs):
        cmd = [str(value) for value in command]
        calls.append(cmd)
        output = Path(cmd[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        return Result()

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    return calls


def _execute_project(assets: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "project-cat",
        "assets": assets,
        "plan": {
            "sections": [
                {
                    "id": "section-cat",
                    "units": [{"id": "edit-cat", "taskType": "edit", "duration": 12}],
                }
            ]
        },
    }


def _execute_plan(version_id: str) -> dict[str, Any]:
    return {
        "timeline": [
            {
                "clip_id": f"clip-{index:02d}",
                "asset_id": "cat-video",
                "asset_version_id": version_id,
                "source_url": PUBLIC_URL,
                "start": float(index * 10),
                "end": float(index * 10 + 4),
                "duration": 4.0,
                "order": index,
                "transition": "cut",
            }
            for index in (1, 2)
        ]
    }


def test_execute_reuses_exact_ingest_cache_without_remote_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_cache = tmp_path / "old-cache.mp4"
    current_cache = tmp_path / "current-cache.mp4"
    old_cache.write_bytes(b"old")
    current_cache.write_bytes(b"current")
    calls = _patch_execute_runtime(monkeypatch, tmp_path)
    downloads: list[str] = []
    monkeypatch.setattr(
        core,
        "download_remote_file",
        lambda url, _destination: downloads.append(url),
    )
    assets = [
        _asset(version_id="asset-version-old", url=old_cache.as_uri()),
        _asset(version_id="asset-version-current", url=current_cache.as_uri()),
    ]

    result = asyncio.run(
        core.execute_ai_edit_plan(
            _execute_project(assets),
            "edit-cat",
            _execute_plan("asset-version-current"),
        )
    )

    assert result["success"] is True
    assert downloads == []
    trim_inputs = [cmd[cmd.index("-i") + 1] for cmd in calls if "-ss" in cmd]
    assert trim_inputs == [str(current_cache), str(current_cache)]
    assert str(old_cache) not in {part for cmd in calls for part in cmd}


def test_execute_remote_fallback_downloads_once_for_multiple_clips(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _patch_execute_runtime(monkeypatch, tmp_path)
    downloads: list[tuple[str, str]] = []

    def download_once(url: str, destination: str) -> None:
        downloads.append((url, destination))
        Path(destination).write_bytes(b"cached remote")

    monkeypatch.setattr(core, "download_remote_file", download_once)
    asset = _asset()
    result = asyncio.run(
        core.execute_ai_edit_plan(
            _execute_project([asset]),
            "edit-cat",
            _execute_plan(asset["versionId"]),
        )
    )

    assert result["success"] is True
    assert [url for url, _destination in downloads] == [PUBLIC_URL]
