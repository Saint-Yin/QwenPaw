from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from services.format_layer import (
    ProjectionCatalogs,
    RevisionSelections,
    build_edit_workbench_view,
    build_r2v_workbench_view,
    build_workbench_view,
    milliseconds_to_seconds,
    seconds_to_milliseconds,
)


def test_r2v_projection_is_storyboard_first_and_version_explicit(projection_fixture):
    fixture = projection_fixture
    view = build_r2v_workbench_view(
        fixture.snapshot,
        "u-r2v",
        catalogs=fixture.catalogs,
        selections=fixture.selections,
        provider=fixture.provider,
    )
    assert view["kind"] == "r2v"
    assert view["readiness"]["ready"] is True
    assert view["videoInputRefs"][0] == fixture.artifacts["storyboard"].source_ref
    assert view["selectedStoryboardVersionId"] == "sb-v4"
    assert view["selectedVideoVersionId"] == "r2v-v6"
    assert view["storyboardVersions"][0]["artifactVersionId"] == "sb-v4"
    assert view["storyboardVersions"][0]["selected"] is True
    assert view["providerConstraints"] == {
        "provider": "bailian",
        "model": "wan2.7-r2v",
        "version": "2026-07-10",
        "capturedAt": "2026-07-10T02:00:00Z",
        "minDuration": 4,
        "maxDuration": 15,
        "maxReferenceImages": 5,
        "allowedDurations": [5, 10, 15],
    }


def test_r2v_without_selected_storyboard_is_visible_as_blocked(projection_fixture):
    fixture = projection_fixture
    selections = RevisionSelections(
        revision_id=fixture.selections.revision_id,
        artifact_versions={
            slot: version
            for slot, version in fixture.selections.artifact_versions.items()
            if slot != fixture.artifacts["storyboard"].slot_id
        },
    )
    view = build_r2v_workbench_view(
        fixture.snapshot,
        "u-r2v",
        catalogs=fixture.catalogs,
        selections=selections,
        provider=fixture.provider,
    )
    assert view["readiness"]["ready"] is False
    assert "STORYBOARD_VERSION_REQUIRED" in view["blockers"]
    assert "STORYBOARD_SELECTION_MISMATCH" in view["blockers"]


def test_edit_projection_preserves_frozen_envelope_and_seconds_losslessly(projection_fixture):
    fixture = projection_fixture
    frozen_before = deepcopy(dict(fixture.ai_edit_plan.workbench_envelope))
    view = build_edit_workbench_view(
        fixture.snapshot,
        "u-edit",
        catalogs=fixture.catalogs,
        selections=fixture.selections,
        plan_versions=(fixture.ai_edit_plan,),
    )
    for key, value in frozen_before.items():
        assert view[key] == value
    clip = view["plan"]["timeline"][0]
    assert (clip["start"], clip["end"], clip["duration"], clip["OS"]) == (25.3, 31.8, 6.5, "保留原声")
    assert view["plan"]["storyboard"] == frozen_before["plan"]["storyboard"]
    assert view["plan"]["audio_plan"] == frozen_before["plan"]["audio_plan"]
    assert view["workflow_trace"] == frozen_before["workflow_trace"]
    assert view["unit"]["duration"] == 45.0
    assert view["readiness"]["ready"] is True
    view["plan"]["timeline"][0]["start"] = 0
    assert fixture.ai_edit_plan.workbench_envelope["plan"]["timeline"][0]["start"] == 25.3
    assert milliseconds_to_seconds(25_300) == 25.3
    assert seconds_to_milliseconds(25.3) == 25_300


def test_edit_view_blocks_rendered_video_with_old_plan_source_fingerprint(
    projection_fixture,
):
    fixture = projection_fixture
    stale_video = replace(
        fixture.artifacts["edit_video"],
        input_fingerprint=f"sha256:{'0' * 64}",
    )
    catalogs = ProjectionCatalogs(
        assets=fixture.catalogs.assets,
        artifacts=tuple(
            stale_video if item.id == stale_video.id else item
            for item in fixture.catalogs.artifacts
        ),
    )
    view = build_edit_workbench_view(
        fixture.snapshot,
        "u-edit",
        catalogs=catalogs,
        selections=fixture.selections,
        plan_versions=(fixture.ai_edit_plan,),
    )
    assert view["readiness"]["ready"] is False
    assert "EDIT_VIDEO_INPUT_FINGERPRINT_STALE" in view["blockers"]


def test_r2v_view_blocks_selected_video_with_open_dependency_impact(
    projection_fixture,
):
    fixture = projection_fixture
    stale_video = replace(
        fixture.artifacts["r2v_video"],
        stale=True,
        stale_reason="OPEN_DEPENDENCY_IMPACT",
    )
    catalogs = ProjectionCatalogs(
        assets=fixture.catalogs.assets,
        artifacts=tuple(
            stale_video if item.id == stale_video.id else item
            for item in fixture.catalogs.artifacts
        ),
    )
    view = build_r2v_workbench_view(
        fixture.snapshot,
        "u-r2v",
        catalogs=catalogs,
        selections=fixture.selections,
        provider=fixture.provider,
    )
    assert view["readiness"]["ready"] is False
    assert "UNIT_VIDEO_STALE:OPEN_DEPENDENCY_IMPACT" in view["blockers"]


def test_single_workbench_dispatch_supports_mixed_project(projection_fixture):
    fixture = projection_fixture
    r2v = build_workbench_view(
        fixture.snapshot,
        "u-r2v",
        catalogs=fixture.catalogs,
        selections=fixture.selections,
        provider=fixture.provider,
        plan_versions=(fixture.ai_edit_plan,),
    )
    edit = build_workbench_view(
        fixture.snapshot,
        "u-edit",
        catalogs=fixture.catalogs,
        selections=fixture.selections,
        provider=fixture.provider,
        plan_versions=(fixture.ai_edit_plan,),
    )
    assert (r2v["kind"], edit["kind"]) == ("r2v", "edit")
    assert edit["unit"]["duration"] > 15
