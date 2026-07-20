# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import subprocess

import pytest

from services.project_files import jq_transform as jq_transform_module
from services.project_files.jq_transform import (
    JqProjectTransformer,
    JqTransformError,
)
from services.project_files.json_pointer import (
    JsonCasConflict,
    diff_json,
    merge_candidate,
)


def test_disjoint_object_changes_merge_without_losing_latest() -> None:
    base = {"story": {"title": "old", "outline": "v1"}, "generation": 1}
    candidate = {"story": {"title": "agent", "outline": "v1"}, "generation": 1}
    latest = {"story": {"title": "old", "outline": "user"}, "generation": 2}

    merged, changes = merge_candidate(
        base=base,
        candidate=candidate,
        latest=latest,
    )

    assert merged["story"] == {"title": "agent", "outline": "user"}
    assert [item.pointer for item in changes] == ["/story/title"]


def test_same_field_change_is_a_deterministic_conflict() -> None:
    base = {"story": {"title": "old"}}
    candidate = {"story": {"title": "agent"}}
    latest = {"story": {"title": "user"}}

    with pytest.raises(JsonCasConflict) as caught:
        merge_candidate(base=base, candidate=candidate, latest=latest)

    assert caught.value.conflicts[0]["pointer"] == "/story/title"


def test_order_array_is_one_explicit_reorder_change() -> None:
    changes = diff_json(
        {"items": {"a": {}, "b": {}}, "order": ["a", "b"]},
        {"items": {"a": {}, "b": {}}, "order": ["b", "a"]},
    )
    assert len(changes) == 1
    assert changes[0].kind == "reorder"
    assert changes[0].pointer == "/order"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_jq_uses_args_and_returns_one_object() -> None:
    result = JqProjectTransformer().transform(
        {"name": "before", "story": {"title": ""}},
        ".name = $name | .story.title = $title",
        string_args={"name": 'A "quoted" name', "title": "中文\n标题"},
    )
    assert result["name"] == 'A "quoted" name'
    assert result["story"]["title"] == "中文\n标题"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_jq_does_not_depend_on_a_mutable_sidecar_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_module = (
        tmp_path
        / "installed"
        / "services"
        / "project_files"
        / "jq_transform.py"
    )
    monkeypatch.setattr(jq_transform_module, "__file__", str(missing_module))

    result = JqProjectTransformer().transform(
        {"name": "before"},
        '.name = "after"',
    )

    assert result == {"name": "after"}


def test_jq_process_starts_at_the_system_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = "/opt/tools/bin/jq"
    recorded_command: list[str] = []

    def run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[bytes]:
        recorded_command.extend(command)
        kwargs["stdout"].write(b'{"name":"after"}\n')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(jq_transform_module.subprocess, "run", run)

    result = JqProjectTransformer(executable=executable).transform(
        {"name": "before"},
        '.name = "after"',
    )

    assert result == {"name": "after"}
    assert recorded_command == [
        executable,
        "--compact-output",
        "--exit-status",
        '.name = "after"',
    ]


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_jq_rejects_multiple_outputs() -> None:
    with pytest.raises(JqTransformError, match="exactly one"):
        JqProjectTransformer().transform({"name": "x"}, "., .")
