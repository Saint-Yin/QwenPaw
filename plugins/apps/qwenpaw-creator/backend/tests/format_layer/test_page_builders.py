# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

from dataclasses import replace

from services.format_layer import (
    IngestItemRecord,
    ProjectPresentationMetadata,
    WorkspaceFile,
    build_asset_library_view,
    build_final_compose_view,
    build_plan_view,
    build_project_header_view,
    build_section_compose_view,
)
from services.format_layer.freshness import (
    ai_edit_execute_fingerprint,
    ai_edit_project_payload,
)


def test_header_and_hybrid_plan_are_deterministic(projection_fixture):
    fixture = projection_fixture
    metadata = ProjectPresentationMetadata(
        scenario="general",
        content_type="brand_video",
    )
    header = build_project_header_view(fixture.snapshot, metadata)
    assert header["name"] == "雪夜汽车短片"
    assert header["masterScript"] == "生成与实拍素材混合的品牌短片。"
    assert header["scenario"] == "general"
    assert header["targetVersion"] == "ov-header-4"
    assert header["uiLocator"] == {"page": "project"}

    first = build_plan_view(fixture.snapshot, fixture.catalogs)
    second = build_plan_view(fixture.snapshot, fixture.catalogs)
    assert first == second
    units = first["sections"][0]["units"]
    assert [unit["taskType"] for unit in units] == ["r2v", "edit"]
    assert [unit["duration"] for unit in units] == [10.0, 45.0]
    assert units[0]["shots"][0]["camera"] == "↑ 推近"
    assert units[0]["shots"][0]["framing"] == "全景"
    assert units[0]["storyboardPrompt"] == "雪夜停车场分镜图"
    assert (
        units[0]["storyboardImageUrl"] == fixture.artifacts["storyboard"].url
    )
    assert (
        units[0]["storyboardImageVersionId"]
        == fixture.artifacts["storyboard"].id
    )
    assert units[0]["videoPrompt"] == "SUV 以恒定速度驶入，保持车身一致"
    assert units[0]["videoUrl"] == fixture.artifacts["r2v_video"].url
    assert units[1]["videoUrl"] == fixture.artifacts["edit_video"].url
    assert units[1]["readiness"]["ready"] is True
    assert first["relations"][0] == {
        "from": "project://section/s1",
        "to": "project://unit/u-r2v",
        "kind": "contains",
    }
    assert first["targetVersion"] == "ov-plan-8"
    assert {item["type"] for item in first["resolvedRefs"]} == {"asset"}


def test_reference_target_duration_never_blocks_header_or_plan(
    projection_fixture,
):
    fixture = projection_fixture
    files = dict(fixture.snapshot.files)
    files["settings/target-duration.txt"] = WorkspaceFile(
        content="约 30 秒，仅供参考",
        object_version="ov-reference-duration",
    )
    snapshot = replace(fixture.snapshot, files=files)
    metadata = ProjectPresentationMetadata(scenario="short_drama")

    assert (
        build_project_header_view(snapshot, metadata)["targetDuration"] is None
    )
    assert (
        build_plan_view(snapshot, fixture.catalogs)["targetDuration"] is None
    )


def test_edit_shots_do_not_require_camera_and_guide_ai_edit_inputs(
    projection_fixture,
):
    fixture = projection_fixture
    edit_root = "story/sections/001000--s1--opening/units/002000--u-edit--demo"
    files = dict(fixture.snapshot.files)
    files.update(
        {
            f"{edit_root}/shots/001000--legacy-freeform/description.md": WorkspaceFile(
                content="保留产品操作完整动作。",
                object_version="ov-edit-shot-description",
            ),
            f"{edit_root}/shots/001000--legacy-freeform/camera.md": WorkspaceFile(
                content="低角度跟随产品移动，构图保持操作区域清晰。",
                object_version="ov-edit-shot-freeform-camera",
            ),
            f"{edit_root}/shots/001000--legacy-freeform/duration.txt": WorkspaceFile(
                content="6.5",
                object_version="ov-edit-shot-duration",
            ),
            f"{edit_root}/shots/002000--legacy-no-camera/description.md": WorkspaceFile(
                content="结尾保留完整结果展示。",
                object_version="ov-edit-shot-no-camera-description",
            ),
            f"{edit_root}/shots/002000--legacy-no-camera/duration.txt": WorkspaceFile(
                content="5",
                object_version="ov-edit-shot-no-camera-duration",
            ),
        },
    )
    snapshot = replace(
        fixture.snapshot,
        files=files,
        target_versions={
            **fixture.snapshot.target_versions,
            "shot:legacy-freeform": "ov-edit-shot-freeform",
            "shot:legacy-no-camera": "ov-edit-shot-no-camera",
        },
    )

    edit_unit = build_plan_view(snapshot, fixture.catalogs)["sections"][0][
        "units"
    ][1]
    assert len(edit_unit["shots"]) == 2
    assert edit_unit["shots"][0]["camera"] == ""
    assert edit_unit["shots"][0]["framing"] == ""
    assert edit_unit["shots"][0]["cameraDescription"] == (
        "低角度跟随产品移动，构图保持操作区域清晰。"
    )
    assert edit_unit["shots"][1]["cameraDescription"] == ""

    base_payload = ai_edit_project_payload(fixture.snapshot, fixture.catalogs)
    edit_payload = ai_edit_project_payload(snapshot, fixture.catalogs)
    assert edit_payload != base_payload
    projected_section = edit_payload["plan"]["sections"][0]
    assert "script" in projected_section
    assert [
        item["description"] for item in projected_section["units"][1]["shots"]
    ] == ["保留产品操作完整动作。", "结尾保留完整结果展示。"]
    assert projected_section["units"][1]["shots"][0]["camera"] == ""

    plan = dict(fixture.ai_edit_plan.workbench_envelope["plan"])
    assert ai_edit_execute_fingerprint(
        fixture.snapshot,
        fixture.catalogs,
        unit_id="u-edit",
        plan=plan,
    ) != ai_edit_execute_fingerprint(
        snapshot,
        fixture.catalogs,
        unit_id="u-edit",
        plan=plan,
    )


def test_assets_separate_ingest_tasks_from_attached_versions(
    projection_fixture,
):
    fixture = projection_fixture
    view = build_asset_library_view(
        fixture.snapshot,
        catalogs=fixture.catalogs,
        ingest_items=(
            IngestItemRecord(
                task_id="task-new-upload",
                asset_id=None,
                asset_version_id=None,
                name="new.mov",
                status="RUNNING",
                progress=0.4,
            ),
        ),
    )
    assert {item["assetId"] for item in view["attachedSources"]} == {
        "scene-a",
        "upload-video-01",
    }
    assert view["ingestItems"] == [
        {
            "taskId": "task-new-upload",
            "assetId": None,
            "assetVersionId": None,
            "name": "new.mov",
            "status": "RUNNING",
            "progress": 0.4,
            "error": None,
        },
    ]
    assert all(
        item["assetVersionId"] != "task-new-upload"
        for item in view["attachedSources"]
    )
    assert "presentationAssets" in view
    assert isinstance(view["presentationAssets"], list)
    video = next(
        item
        for item in view["attachedSources"]
        if item["assetId"] == "upload-video-01"
    )
    assert video["referenceCount"] == 3
    assert video["sourceRef"].endswith("@av-video-7")
    assert {item["category"] for item in view["presentationAssets"]} == {
        "upload",
        "env_ref",
        "generated",
    }
    generated = [
        item
        for item in view["presentationAssets"]
        if item["category"] == "generated"
    ]
    assert {item["generatedKind"] for item in generated} == {
        "storyboard_image",
        "unit_video",
        "section_video",
    }
    assert all(item["presentationStatus"] == "accepted" for item in generated)
    visual = view["visualAssets"][0]
    assert visual["name"] == "雪夜停车场"
    assert visual["description"] == "蓝色雪夜停车场"
    assert visual["existence"] == "available"
    assert visual["url"] == fixture.assets["scene"].url
    assert visual["assetVersionId"] == "av-scene-2"
    assert visual["artifactVersionId"] is None
    assert visual["targetVersion"] == "ov-visual-scene-main-4"
    presentation = next(
        item
        for item in view["presentationAssets"]
        if item["id"] == "scene-main"
    )
    assert presentation["targetVersion"] == "ov-visual-scene-main-4"
    assert presentation["assetVersionId"] == "av-scene-2"
    assert presentation["artifactVersionId"] is None
    assert presentation["detail"] == {
        "id": "scene-main",
        "name": "雪夜停车场",
        "kind": "scene",
        "description": "蓝色雪夜停车场",
        "mediaType": "image",
        "primaryUrl": fixture.assets["scene"].url,
        "images": [
            {
                "id": "av-scene-2",
                "name": "环境基准图",
                "url": fixture.assets["scene"].url,
                "description": "蓝色雪夜停车场主视角",
                "facetKind": "unknown",
            },
        ],
        "refsNeeded": ["环境基准图"],
        "prompts": ["蓝色雪夜停车场主视角"],
        "referenceImageRefs": [[fixture.assets["video"].source_ref]],
    }
    source = next(
        item
        for item in view["presentationAssets"]
        if item["id"] == "upload-video-01"
    )
    assert source["assetVersionId"] == "av-video-7"
    assert source["checksum"] == fixture.assets["video"].checksum
    assert (
        source["durationSeconds"] == fixture.assets["video"].duration_seconds
    )
    assert source["userNotes"] == "保留 25 秒后的完整操作。"
    assert source["detail"]["kind"] == "material"
    assert source["detail"]["primaryUrl"] == fixture.assets["video"].url
    assert view["targetVersion"] == "ov-assets-6"


def test_compose_views_use_explicit_immutable_version_selections(
    projection_fixture,
):
    fixture = projection_fixture
    section = build_section_compose_view(
        fixture.snapshot,
        "s1",
        catalogs=fixture.catalogs,
        selections=fixture.selections,
    )
    assert section["readiness"]["ready"] is True
    assert [
        (item["sourceRef"], item["artifactVersionId"], item["order"])
        for item in section["selections"]
    ] == [
        ("project://unit/u-r2v", "r2v-v6", 1000),
        ("project://unit/u-edit", "edit-v3", 2000),
    ]
    assert section["targetVersion"] == "ov-post-section-s1-5"
    assert section["sectionNumber"] == 1
    assert section["sectionTitle"] == "雪夜启程"
    assert (
        section["renderedVideoUrl"] == fixture.artifacts["section_video"].url
    )
    assert {item["name"] for item in section["candidates"]} == {
        "U01 video v6",
        "U02 edit v3",
    }
    assert all(
        item["sourceRef"].startswith("artifact://")
        for item in section["candidates"]
    )

    final = build_final_compose_view(
        fixture.snapshot,
        catalogs=fixture.catalogs,
        selections=fixture.selections,
    )
    assert final["readiness"]["ready"] is True
    assert final["selections"][0]["sourceRef"] == "project://section/s1"
    assert final["selections"][0]["artifactVersionId"] == "section-v2"
    assert (
        final["renderedVideoRef"]
        == fixture.artifacts["final_video"].source_ref
    )
    assert final["renderedVideoUrl"] == fixture.artifacts["final_video"].url
    assert final["sections"] == [{"id": "s1", "number": 1, "title": "雪夜启程"}]
    assert [item["artifactVersionId"] for item in final["candidates"]] == [
        "section-v2",
        "r2v-v6",
        "edit-v3",
    ]
    assert {item["sectionId"] for item in final["candidates"]} == {"s1"}
    assert [item["sourceKind"] for item in final["candidates"]] == [
        "section",
        "unit",
        "unit",
    ]
    assert all(item["selected"] is True for item in final["candidates"])
    assert all(
        item["freshnessStatus"] == "current" for item in final["candidates"]
    )
    assert final["targetVersion"] == "ov-post-final-3"


def test_final_compose_uses_selected_unit_videos_when_section_video_is_absent(
    projection_fixture,
):
    fixture = projection_fixture
    files = dict(fixture.snapshot.files)
    files.pop("post/final/sequence/001000--s1.ref")
    files.pop("post/sections/s1/rendered-video.ref")
    files["post/final/sequence/001000--unit--u-r2v.ref"] = WorkspaceFile(
        content=fixture.artifacts["r2v_video"].source_ref,
        object_version="ov-final-unit-r2v",
    )
    files["post/final/sequence/002000--unit--u-edit.ref"] = WorkspaceFile(
        content=fixture.artifacts["edit_video"].source_ref,
        object_version="ov-final-unit-edit",
    )
    snapshot = replace(fixture.snapshot, files=files)
    old_r2v = replace(
        fixture.artifacts["r2v_video"],
        id="r2v-old",
        url="/generated/u-r2v/r2v-old.mp4",
        checksum="sha-r2v-old",
        created_at="2026-07-09T02:10:00Z",
    )
    catalogs = replace(
        fixture.catalogs,
        artifacts=tuple(
            item
            for item in fixture.catalogs.artifacts
            if item.kind != "section_video"
        )
        + (old_r2v,),
    )
    selected_versions = dict(fixture.selections.artifact_versions)
    selected_versions.pop(fixture.artifacts["section_video"].slot_id)
    selections = replace(
        fixture.selections,
        artifact_versions=selected_versions,
    )

    final = build_final_compose_view(
        snapshot,
        catalogs=catalogs,
        selections=selections,
    )

    assert final["readiness"]["ready"] is True
    assert final["blockers"] == []
    assert [item["sourceRef"] for item in final["selections"]] == [
        "project://unit/u-r2v",
        "project://unit/u-edit",
    ]
    assert [item["sourceKind"] for item in final["selections"]] == [
        "unit",
        "unit",
    ]
    assert [item["artifactVersionId"] for item in final["candidates"]] == [
        "r2v-v6",
        "edit-v3",
    ]
    assert all(item["sectionId"] == "s1" for item in final["candidates"])


def test_final_compose_partial_section_or_unit_subset_is_ready(
    projection_fixture,
):
    fixture = projection_fixture
    files = dict(fixture.snapshot.files)
    files.pop("post/final/sequence/001000--s1.ref")
    files["post/final/sequence/001000--unit--u-r2v.ref"] = WorkspaceFile(
        content=fixture.artifacts["r2v_video"].source_ref,
        object_version="ov-final-partial-unit",
    )
    snapshot = replace(fixture.snapshot, files=files)

    final = build_final_compose_view(
        snapshot,
        catalogs=fixture.catalogs,
        selections=fixture.selections,
    )

    assert final["readiness"]["ready"] is True
    assert final["blockers"] == []
    assert [item["sourceRef"] for item in final["selections"]] == [
        "project://unit/u-r2v",
    ]
    assert not any(
        "FINAL_COMPOSE_SOURCE_MISSING" in item for item in final["blockers"]
    )
