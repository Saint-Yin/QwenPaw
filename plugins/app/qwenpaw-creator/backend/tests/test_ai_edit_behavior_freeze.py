"""P0 characterization/golden tests for the frozen AI Edit production core.

These tests intentionally exercise the current public and private seams named by
the refactor implementation guide.  They are not assertions about the future
runtime wrapper: their job is to make any model-visible prompt, batching,
fallback, envelope, timeline/storyboard, or execute-result change explicit.

All model, media, network, ffmpeg, and filesystem boundaries are deterministic
fakes.  A failing hash must be reviewed as an AI Edit behavior change rather
than updated mechanically during the architecture refactor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.media.ai_edit import core as ai_editing


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _external_creator_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATOR_DATA_ROOT", str(tmp_path / "creator-runtime"))


GOAL = "剪成 24 秒赛事高光"


def _project() -> dict[str, Any]:
    return {
        "id": "freeze-project",
        "name": "冻结剪辑",
        "description": "把素材剪成紧凑的 24 秒赛事回顾",
        "contentType": "sports",
        "assets": [
            {
                "id": "video-a",
                "name": "上半场.mp4",
                "category": "upload",
                "mediaType": "video",
                "url": "/generated/uploads/freeze/a.mp4",
                "description": "主赛场",
            },
            {
                "id": "video-b",
                "name": "下半场.mp4",
                "category": "upload",
                "mediaType": "video",
                "url": "https://cdn.example.com/freeze/b.mp4",
                "description": "领奖",
            },
        ],
        "plan": {
            "sections": [
                {
                    "id": "sec-1",
                    "units": [
                        {
                            "id": "edit-1",
                            "duration": 24,
                            "storyText": "保留进球和庆祝",
                            "materialRefs": ["video-a", "video-b"],
                            "shots": [],
                        }
                    ],
                }
            ]
        },
    }


def test_ai_edit_core_uses_basic_plan_without_source_intelligence(monkeypatch):
    project = _project()
    monkeypatch.setattr(ai_editing.model_config, "get_text_api_key", lambda: "fake-key")
    envelope = asyncio.run(ai_editing.build_ai_edit_plan(project, "edit-1", goal=GOAL))
    assert envelope["plan"]["timeline"]
    assert envelope["plan"]["model"]["provider"] == "heuristic"


def test_execute_allows_pet_clip_without_director_overlay_copy():
    assert ai_editing._validate_execution_overlay_copy(
        {"reason": "小猫在院子角落低头闻嗅"},
        expected_kind="pet_os",
        clip_index=1,
        clip_duration=3.0,
    ) is None


def test_semantic_pet_overlay_prompt_rejects_action_labels() -> None:
    prompt = ai_editing._semantic_agent_prompt(
        {"name": "猫咪冒险", "contentType": "pet_video"},
        {},
        {"duration": 12, "shots": []},
        [],
        [],
        "剪出一段有性格的猫咪冒险",
    )
    assert "禁止写成镜头标题、动作标签、旁白摘要" in prompt
    assert "‘碎石路上飞奔’→‘这条路归我巡逻’" in prompt
    assert "appearAt 和 duration 是相对 clip 入点的秒数" in prompt


def _patch_execute_environment(monkeypatch, tmp_path, readiness):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(ai_editing, "ffmpeg_readiness", lambda: readiness)
    monkeypatch.setattr(ai_editing, "ensure_task_work_subdir", lambda *parts: tmp_path)
    monkeypatch.setattr(ai_editing, "_source_local_path", lambda url, project_id: source)
    monkeypatch.setattr(
        ai_editing,
        "media_url_for",
        lambda path: f"/generated/task-work/freeze/{path.name}",
    )
    monkeypatch.setattr(ai_editing.uuid, "uuid4", lambda: SimpleNamespace(hex="1234567890abcdef"))


def _execute_plan() -> dict[str, Any]:
    return {
        "timeline": [
            {
                "clip_id": "clip-02",
                "asset_id": "video-a",
                "source_url": "/generated/uploads/freeze/a.mp4",
                "start": 8.0,
                "end": 11.0,
                "duration": 3.0,
                "order": 2,
                "transition": "fade",
                "reason": "庆祝",
            },
            {
                "clip_id": "clip-01",
                "asset_id": "video-a",
                "source_url": "/generated/uploads/freeze/a.mp4",
                "start": 1.0,
                "end": 5.0,
                "duration": 4.0,
                "order": 1,
                "transition": "cut",
                "reason": "进球",
            },
        ]
    }


def test_execute_readiness_failure_return_is_frozen(monkeypatch, tmp_path):
    readiness = {"status": "blocked", "path": None, "blockers": ["ffmpeg missing"]}
    _patch_execute_environment(monkeypatch, tmp_path, readiness)
    result = asyncio.run(ai_editing.execute_ai_edit_plan(_project(), "edit-1", _execute_plan()))
    assert result == {
        "success": False,
        "output_url": None,
        "blockers": ["ffmpeg missing"],
        "runtime_readiness": {"ffmpeg": readiness},
    }


def test_execute_trim_failure_return_is_frozen(monkeypatch, tmp_path):
    readiness = {"status": "ok", "path": "/usr/bin/ffmpeg", "blockers": []}
    _patch_execute_environment(monkeypatch, tmp_path, readiness)
    calls: list[list[str]] = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "trim failed"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(ai_editing.subprocess, "run", fake_run)
    result = asyncio.run(ai_editing.execute_ai_edit_plan(_project(), "edit-1", _execute_plan()))
    expected_work_dir = tmp_path / "edit-1-12345678"
    assert len(calls) == 1
    assert result == {
        "success": False,
        "output_url": None,
        "blockers": ["FFmpeg 裁剪失败: trim failed"],
        "runtime_readiness": {"ffmpeg": readiness},
        "work_dir": str(expected_work_dir),
    }


def test_execute_concat_failure_return_is_frozen(monkeypatch, tmp_path):
    readiness = {"status": "ok", "path": "/usr/bin/ffmpeg", "blockers": []}
    _patch_execute_environment(monkeypatch, tmp_path, readiness)
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode, stderr=""):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = stderr

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "concat" in cmd:
            return Result(1, "concat failed")
        Path(cmd[-1]).write_bytes(b"clip")
        return Result(0)

    monkeypatch.setattr(ai_editing.subprocess, "run", fake_run)
    plan = {"timeline": [_execute_plan()["timeline"][1]]}
    result = asyncio.run(ai_editing.execute_ai_edit_plan(_project(), "edit-1", plan))
    expected_work_dir = tmp_path / "edit-1-12345678"
    assert len(calls) == 2
    assert result == {
        "success": False,
        "output_url": None,
        "blockers": ["FFmpeg 拼接失败: concat failed"],
        "runtime_readiness": {"ffmpeg": readiness},
        "work_dir": str(expected_work_dir),
    }


def test_execute_success_return_commands_and_timeline_are_frozen(monkeypatch, tmp_path):
    readiness = {"status": "ok", "path": "/usr/bin/ffmpeg", "blockers": []}
    _patch_execute_environment(monkeypatch, tmp_path, readiness)
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"media")
        return Result()

    monkeypatch.setattr(ai_editing.subprocess, "run", fake_run)
    plan = _execute_plan()
    result = asyncio.run(ai_editing.execute_ai_edit_plan(_project(), "edit-1", plan))

    expected_work_dir = tmp_path / "edit-1-12345678"
    expected_output = tmp_path / "edit-1-12345678-ai-edit.mp4"
    assert len(calls) == 3
    assert all(cmd[:2] == ["/usr/bin/ffmpeg", "-y"] for cmd in calls)
    assert [calls[0][calls[0].index("-ss") + 1], calls[1][calls[1].index("-ss") + 1]] == ["1.0", "8.0"]
    assert [calls[0][calls[0].index("-t") + 1], calls[1][calls[1].index("-t") + 1]] == ["4.0", "3.0"]
    assert calls[-1][2:8] == ["-f", "concat", "-safe", "0", "-i", str(expected_work_dir / "concat.txt")]
    assert calls[-1][-3:-1] == ["-c", "copy"]
    assert result == {
        "success": True,
        "output_url": "/generated/task-work/freeze/edit-1-12345678-ai-edit.mp4",
        "output_path": str(expected_output),
        "updated_timeline": sorted(plan["timeline"], key=lambda item: item["order"]),
        "blockers": [],
        "runtime_readiness": {"ffmpeg": readiness},
        "work_dir": str(expected_work_dir),
    }
