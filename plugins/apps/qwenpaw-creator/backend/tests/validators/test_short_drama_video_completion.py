# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

from copy import deepcopy

import pytest

from domain.refs import workspace_artifact_ref
from services.format_layer.inputs import TextWorkspaceSnapshot, WorkspaceFile
from services.format_layer.parsing import parse_sections
from services.validators.short_drama import validate_short_drama_plan
from services.validators.video_completion import (
    derive_missing_post_work_refs,
    derive_missing_video_work_refs,
    validate_video_project_completion,
)

pytestmark = pytest.mark.unit


SECTION_ROOT = "story/sections/001000--chase--追逐"
UNIT_1_ROOT = f"{SECTION_ROOT}/units/001000--chase-a--追逐上半段"
UNIT_2_ROOT = f"{SECTION_ROOT}/units/002000--chase-b--追逐下半段"

UNIT_1_REF = workspace_artifact_ref("unit:chase-a/video", "artifact-unit-a")
UNIT_2_REF = workspace_artifact_ref("unit:chase-b/video", "artifact-unit-b")
SECTION_REF = workspace_artifact_ref("section:chase/video", "artifact-section")
FINAL_REF = workspace_artifact_ref("project:final/video", "artifact-final")


def _files(*, target: str = "30") -> dict[str, str]:
    return {
        "settings/target-duration.txt": target,
        f"{SECTION_ROOT}/title.txt": "猫追鼠",
        f"{SECTION_ROOT}/duration-budget.txt": "30",
        f"{UNIT_1_ROOT}/title.txt": "发现与追逐",
        f"{UNIT_1_ROOT}/route.txt": "r2v",
        f"{UNIT_1_ROOT}/duration.txt": "15",
        f"{UNIT_1_ROOT}/shots/001000--spot/description.md": "猫发现老鼠",
        f"{UNIT_1_ROOT}/shots/001000--spot/camera.md": "⊙ 静止\n画幅：中景",
        f"{UNIT_1_ROOT}/shots/001000--spot/duration.txt": "7",
        f"{UNIT_1_ROOT}/shots/002000--run/description.md": "猫开始追逐",
        f"{UNIT_1_ROOT}/shots/002000--run/camera.md": "→ 横摇右\n画幅：全景",
        f"{UNIT_1_ROOT}/shots/002000--run/duration.txt": "8",
        f"{UNIT_2_ROOT}/title.txt": "反转与收束",
        f"{UNIT_2_ROOT}/route.txt": "r2v",
        f"{UNIT_2_ROOT}/duration.txt": "15",
        f"{UNIT_2_ROOT}/shots/001000--turn/description.md": "老鼠突然转向",
        f"{UNIT_2_ROOT}/shots/001000--turn/camera.md": "← 横摇左\n画幅：全景",
        f"{UNIT_2_ROOT}/shots/001000--turn/duration.txt": "10",
        f"{UNIT_2_ROOT}/shots/002000--end/description.md": "猫和老鼠停下",
        f"{UNIT_2_ROOT}/shots/002000--end/camera.md": "↑ 推近\n画幅：近景",
        f"{UNIT_2_ROOT}/shots/002000--end/duration.txt": "5",
        f"{UNIT_1_ROOT}/production/r2v/video/selected.ref": UNIT_1_REF,
        f"{UNIT_2_ROOT}/production/r2v/video/selected.ref": UNIT_2_REF,
        "post/sections/chase/sequence/001000--chase-a.ref": UNIT_1_REF,
        "post/sections/chase/sequence/002000--chase-b.ref": UNIT_2_REF,
        "post/sections/chase/rendered-video.ref": SECTION_REF,
        "post/final/sequence/001000--section--chase.ref": SECTION_REF,
        "post/final/rendered-video.ref": FINAL_REF,
    }


def _snapshot(files: dict[str, str]) -> TextWorkspaceSnapshot:
    return TextWorkspaceSnapshot(
        project_id="project-short",
        revision_id="working-1",
        files={
            path: WorkspaceFile(text, f"ov-{index}")
            for index, (path, text) in enumerate(files.items())
        },
        target_versions={},
    )


def _artifacts() -> list[dict]:
    return [
        {
            "id": "artifact-unit-a",
            "slot_id": "unit:chase-a/video",
            "slot_kind": "unit_video",
            "slot_target_ref": "unit:chase-a",
            "duration_seconds": 15.0,
            "provenance_refs": [],
            "metadata": {},
        },
        {
            "id": "artifact-unit-b",
            "slot_id": "unit:chase-b/video",
            "slot_kind": "unit_video",
            "slot_target_ref": "unit:chase-b",
            "duration_seconds": 15.0,
            "provenance_refs": [],
            "metadata": {},
        },
        {
            "id": "artifact-section",
            "slot_id": "section:chase/video",
            "slot_kind": "section_video",
            "slot_target_ref": "section:chase",
            "duration_seconds": 30.0,
            "provenance_refs": [UNIT_1_REF, UNIT_2_REF],
            "metadata": {
                "sourceSelections": [
                    {
                        "sourceRef": "project://unit/chase-a",
                        "artifactVersionId": "artifact-unit-a",
                        "order": 1,
                        "transition": "cut",
                    },
                    {
                        "sourceRef": "project://unit/chase-b",
                        "artifactVersionId": "artifact-unit-b",
                        "order": 2,
                        "transition": "cut",
                    },
                ],
            },
        },
        {
            "id": "artifact-final",
            "slot_id": "project:final/video",
            "slot_kind": "final_video",
            "slot_target_ref": "project:project-short",
            "duration_seconds": 30.0,
            "provenance_refs": [SECTION_REF],
            "metadata": {
                "sourceSelections": [
                    {
                        "sourceRef": "project://section/chase",
                        "artifactVersionId": "artifact-section",
                        "order": 1,
                        "transition": "cut",
                    },
                ],
            },
        },
    ]


def test_short_drama_30_seconds_two_r2v_units_is_canonical() -> None:
    snapshot = _snapshot(_files())
    report = validate_short_drama_plan(
        scenario="short_drama",
        target_duration_text=snapshot.text("settings/target-duration.txt"),
        sections=parse_sections(snapshot),
    )
    assert report.valid


def test_short_drama_allows_edit_route_when_duration_topology_matches() -> (
    None
):
    files = _files()
    files[f"{UNIT_1_ROOT}/route.txt"] = "edit"
    snapshot = _snapshot(files)
    report = validate_short_drama_plan(
        scenario="short_drama",
        target_duration_text=snapshot.text("settings/target-duration.txt"),
        sections=parse_sections(snapshot),
    )
    assert report.valid


def test_short_drama_ignores_project_target_but_keeps_section_local_rules() -> (
    None
):
    files = _files(target="30s")
    for path in list(files):
        if UNIT_2_ROOT in path:
            del files[path]
    files[f"{UNIT_1_ROOT}/duration.txt"] = "10"
    files[f"{UNIT_1_ROOT}/shots/001000--spot/duration.txt"] = "4"
    snapshot = _snapshot(files)
    report = validate_short_drama_plan(
        scenario="short_drama",
        target_duration_text="约 30 秒，仅供参考",
        sections=parse_sections(snapshot),
    )
    assert {issue.code for issue in report.issues} == {
        "SHORT_DRAMA_SECTION_UNIT_DURATION_MISMATCH",
        "SHORT_DRAMA_SHOT_DURATION_MISMATCH",
    }


def test_short_drama_rules_do_not_touch_video_edit() -> None:
    report = validate_short_drama_plan(
        scenario="video_edit",
        target_duration_text="not-a-duration",
        sections=(),
    )
    assert report.valid


def test_video_completion_chain_is_disabled_for_empty_video_edit_tree() -> (
    None
):
    report = validate_video_project_completion(
        scenario="video_edit",
        project_id="project-edit",
        snapshot=_snapshot({"settings/target-duration.txt": "60"}),
        sections=(),
        artifact_rows=(),
    )
    assert report.valid


def test_exact_section_and_final_video_chain_passes_completion() -> None:
    snapshot = _snapshot(_files())
    report = validate_video_project_completion(
        scenario="short_drama",
        project_id="project-short",
        snapshot=snapshot,
        sections=parse_sections(snapshot),
        artifact_rows=_artifacts(),
    )
    assert report.valid
    assert (
        derive_missing_post_work_refs(
            scenario="short_drama",
            project_id="project-short",
            snapshot=snapshot,
            sections=parse_sections(snapshot),
            artifact_rows=_artifacts(),
        )
        == ()
    )


def test_disabled_video_completion_never_exposes_post_or_unit_work() -> None:
    files = _files()
    for path in (
        "post/sections/chase/sequence/001000--chase-a.ref",
        "post/sections/chase/sequence/002000--chase-b.ref",
        "post/sections/chase/rendered-video.ref",
        "post/final/sequence/001000--section--chase.ref",
        "post/final/rendered-video.ref",
    ):
        files.pop(path)
    section_missing = _snapshot(files)
    assert (
        derive_missing_post_work_refs(
            scenario="short_drama",
            project_id="project-short",
            snapshot=section_missing,
            sections=parse_sections(section_missing),
            artifact_rows=_artifacts(),
        )
        == ()
    )

    files.update(
        {
            "post/sections/chase/sequence/001000--chase-a.ref": UNIT_1_REF,
            "post/sections/chase/sequence/002000--chase-b.ref": UNIT_2_REF,
            "post/sections/chase/rendered-video.ref": SECTION_REF,
        },
    )
    final_missing = _snapshot(files)
    assert (
        derive_missing_post_work_refs(
            scenario="short_drama",
            project_id="project-short",
            snapshot=final_missing,
            sections=parse_sections(final_missing),
            artifact_rows=_artifacts(),
        )
        == ()
    )

    files.pop(f"{UNIT_2_ROOT}/production/r2v/video/selected.ref")
    upstream_missing = _snapshot(files)
    assert "post:chase" not in derive_missing_post_work_refs(
        scenario="short_drama",
        project_id="project-short",
        snapshot=upstream_missing,
        sections=parse_sections(upstream_missing),
        artifact_rows=_artifacts(),
    )
    assert (
        derive_missing_video_work_refs(
            scenario="short_drama",
            project_id="project-short",
            snapshot=upstream_missing,
            sections=parse_sections(upstream_missing),
            artifact_rows=_artifacts(),
        )
        == ()
    )


def test_disabled_completion_ignores_metadata_provenance_and_final_duration() -> (
    None
):
    artifacts = deepcopy(_artifacts())
    artifacts[2]["metadata"]["sourceSelections"][1][
        "artifactVersionId"
    ] = "old-unit"
    artifacts[2]["provenance_refs"] = [UNIT_1_REF]
    artifacts[3]["duration_seconds"] = 10.0
    report = validate_video_project_completion(
        scenario="short_drama",
        project_id="project-short",
        snapshot=_snapshot(_files()),
        sections=parse_sections(_snapshot(_files())),
        artifact_rows=artifacts,
    )
    assert report.valid

    final_only = deepcopy(_artifacts())
    final_only[3]["duration_seconds"] = 10.0
    report = validate_video_project_completion(
        scenario="short_drama",
        project_id="project-short",
        snapshot=_snapshot(_files()),
        sections=parse_sections(_snapshot(_files())),
        artifact_rows=final_only,
    )
    assert report.valid
