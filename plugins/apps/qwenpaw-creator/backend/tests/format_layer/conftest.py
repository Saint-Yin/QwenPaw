# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.format_layer import (
    AiEditPlanVersion,
    ArtifactVersionRecord,
    AssetVersionRecord,
    ProjectionCatalogs,
    ProviderConstraintSnapshot,
    RevisionSelections,
    TextWorkspaceSnapshot,
    WorkspaceFile,
)


@dataclass(frozen=True)
class ProjectionFixture:
    snapshot: TextWorkspaceSnapshot
    catalogs: ProjectionCatalogs
    selections: RevisionSelections
    provider: ProviderConstraintSnapshot
    ai_edit_plan: AiEditPlanVersion
    artifacts: dict[str, ArtifactVersionRecord]
    assets: dict[str, AssetVersionRecord]


def _file_map(contents: dict[str, str]) -> dict[str, WorkspaceFile]:
    return {
        path: WorkspaceFile(content=value, object_version=f"ov-file-{number}")
        for number, (path, value) in enumerate(contents.items(), 1)
    }


@pytest.fixture()
def projection_fixture() -> ProjectionFixture:
    assets = {
        "scene": AssetVersionRecord(
            id="av-scene-2",
            logical_asset_id="scene-a",
            name="雪夜停车场",
            checksum="sha-scene",
            media_type="image",
            url="/media/scene-a-v2.png",
            thumbnail_url="/thumbs/scene-a-v2.png",
            created_at="2026-07-10T01:00:00Z",
            provenance_refs=("upload:scene",),
            object_version="ov-asset-scene",
        ),
        "video": AssetVersionRecord(
            id="av-video-7",
            logical_asset_id="upload-video-01",
            name="product-demo.mp4",
            checksum="sha-video",
            media_type="video",
            url="/media/product-demo-v7.mp4",
            thumbnail_url="/thumbs/product-demo-v7.jpg",
            created_at="2026-07-10T01:10:00Z",
            provenance_refs=("upload:video",),
            duration_seconds=93.125,
            object_version="ov-asset-video",
        ),
    }
    artifacts = {
        "storyboard": ArtifactVersionRecord(
            id="sb-v4",
            slot_id="unit:u-r2v/storyboard",
            kind="r2v_storyboard_image",
            owner_ref="unit:u-r2v",
            name="U01 storyboard v4",
            url="/generated/u-r2v/sb-v4.png",
            thumbnail_url="/generated/u-r2v/sb-v4-thumb.png",
            checksum="sha-sb-v4",
            created_at="2026-07-10T02:00:00Z",
            based_on_revision_id="revision-17",
            provenance_refs=("asset://scene-a@av-scene-2",),
            input_fingerprint="ifp-sb-4",
        ),
        "r2v_video": ArtifactVersionRecord(
            id="r2v-v6",
            slot_id="unit:u-r2v/video",
            kind="unit_video",
            owner_ref="unit:u-r2v",
            name="U01 video v6",
            url="/generated/u-r2v/r2v-v6.mp4",
            checksum="sha-r2v-v6",
            created_at="2026-07-10T02:10:00Z",
            based_on_revision_id="revision-17",
            provenance_refs=("artifact://unit%3Au-r2v%2Fstoryboard@sb-v4",),
            duration_seconds=10.0,
            input_fingerprint="ifp-r2v-6",
        ),
        "edit_video": ArtifactVersionRecord(
            id="edit-v3",
            slot_id="unit:u-edit/video",
            kind="unit_video",
            owner_ref="unit:u-edit",
            name="U02 edit v3",
            url="/generated/u-edit/edit-v3.mp4",
            checksum="sha-edit-v3",
            created_at="2026-07-10T02:20:00Z",
            based_on_revision_id="revision-17",
            provenance_refs=("ai-edit-plan://u-edit@plan-v4",),
            duration_seconds=45.0,
            input_fingerprint="ifp-edit-3",
        ),
        "section_video": ArtifactVersionRecord(
            id="section-v2",
            slot_id="section:s1/video",
            kind="section_video",
            owner_ref="section:s1",
            name="Section 1 v2",
            url="/generated/sections/s1-v2.mp4",
            checksum="sha-section-v2",
            created_at="2026-07-10T02:30:00Z",
            based_on_revision_id="revision-17",
            provenance_refs=("artifact:r2v-v6", "artifact:edit-v3"),
            duration_seconds=55.0,
        ),
        "final_video": ArtifactVersionRecord(
            id="final-v1",
            slot_id="project:final/video",
            kind="final_video",
            owner_ref="project:p1",
            name="Final v1",
            url="/generated/final/final-v1.mp4",
            checksum="sha-final-v1",
            created_at="2026-07-10T02:40:00Z",
            based_on_revision_id="revision-17",
            provenance_refs=("artifact:section-v2",),
            duration_seconds=55.0,
        ),
    }
    storyboard_ref = artifacts["storyboard"].source_ref
    r2v_video_ref = artifacts["r2v_video"].source_ref
    edit_video_ref = artifacts["edit_video"].source_ref
    section_video_ref = artifacts["section_video"].source_ref
    final_video_ref = artifacts["final_video"].source_ref
    scene_ref = assets["scene"].source_ref
    video_ref = assets["video"].source_ref

    ai_edit_envelope: dict[str, Any] = {
        "unit_id": "u-edit",
        "plan": {
            "summary": "剪辑方案摘要",
            "target_duration": 45,
            "timeline": [
                {
                    "clip_id": "clip-01",
                    "asset_id": "upload-video-01",
                    "asset_name": "product-demo.mp4",
                    "source_url": "/media/product-demo-v7.mp4",
                    "start": 25.3,
                    "end": 31.8,
                    "duration": 6.5,
                    "order": 1,
                    "transition": "cut",
                    "OS": "保留原声",
                    "reason": "完整展示产品动作",
                },
            ],
            "storyboard": [
                {
                    "start": 25.3,
                    "end": 31.8,
                    "image_url": "/frames/clip-01.jpg",
                },
            ],
            "audio_plan": {"preserve_original": True},
            "storyboard_image_url": "/generated/edit-preview/u-edit-board-v2.png",
        },
        "storyboard_image_url": "/generated/edit-preview/u-edit-board-v2.png",
        "material_assets": [
            {"asset_id": "upload-video-01", "duration": 93.125},
        ],
        "workflow_trace": [{"step": "episode", "status": "done"}],
    }
    ai_edit_plan = AiEditPlanVersion(
        id="plan-v4",
        unit_id="u-edit",
        checksum="sha-plan-v4",
        created_at="2026-07-10T02:15:00Z",
        workbench_envelope=ai_edit_envelope,
    )

    contents = {
        "title.txt": "雪夜汽车短片",
        "description.md": "生成与实拍素材混合的品牌短片。",
        "settings/platform.txt": "抖音",
        "settings/aspect-ratio.txt": "16:9",
        "settings/resolution.txt": "720P",
        "settings/language.txt": "zh-CN",
        "settings/target-duration.txt": "55s",
        "story/outline.md": "雪夜启程与产品演示",
        "story/sections/001000--s1--opening/title.txt": "雪夜启程",
        "story/sections/001000--s1--opening/summary.md": "先生成氛围镜头，再接产品实拍。",
        "story/sections/001000--s1--opening/narrative.md": "SUV 驶入雪夜停车场。",
        "story/sections/001000--s1--opening/duration-budget.txt": "55s",
        "story/sections/001000--s1--opening/pacing.md": "由慢到快",
        "story/sections/001000--s1--opening/constraints.md": "- 保持车型一致\n- 不出现品牌竞品",
        "story/sections/001000--s1--opening/transition.md": "硬切进入实拍",
        "story/sections/001000--s1--opening/script.md": "雪夜出发，功能尽显。",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/title.txt": "雪夜驶入",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/route.txt": "r2v",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/duration.txt": "10s",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/narrative.md": "SUV 缓慢驶入雪夜停车场。",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/continuity.md": "与下一镜头保持车型和雪夜光线连续。",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/refs/scene.ref": scene_ref,
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/shots/001000--shot-1/description.md": "SUV 从远处驶入。",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/shots/001000--shot-1/camera.md": "↑ 推近\n\n画幅：全景",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/shots/001000--shot-1/duration.txt": "10s",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/storyboard/prompt.md": "雪夜停车场分镜图",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/storyboard/selected.ref": storyboard_ref,
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/storyboard/references/scene.ref": scene_ref,
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/video/prompt.md": "SUV 以恒定速度驶入，保持车身一致",
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/video/selected.ref": r2v_video_ref,
        "story/sections/001000--s1--opening/units/001000--u-r2v--arrival/production/r2v/video/references/scene.ref": scene_ref,
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/title.txt": "产品实拍",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/route.txt": "edit",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/duration.txt": "45s",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/narrative.md": "保留完整产品动作。",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/continuity.md": "从雪夜外景切入内饰演示。",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/refs/sources/main.ref": video_ref,
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/production/edit/intent.md": "保留完整产品展示语句并突出使用动作",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/production/edit/source-refs/main.ref": video_ref,
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/production/edit/plan.ref": ai_edit_plan.source_ref,
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/production/edit/timeline-summary.md": "25.3s 到 31.8s 为产品动作。",
        "story/sections/001000--s1--opening/units/002000--u-edit--demo/production/edit/rendered-video.ref": edit_video_ref,
        "sources/scene-a--snow-parking/selected-version.ref": scene_ref,
        "sources/scene-a--snow-parking/user-notes.md": "必须保留蓝色环境光。",
        "sources/upload-video-01--product-demo/selected-version.ref": video_ref,
        "sources/upload-video-01--product-demo/user-notes.md": "保留 25 秒后的完整操作。",
        "visual/scenes/scene-main--snow-parking/description.md": "蓝色雪夜停车场",
        "visual/scenes/scene-main--snow-parking/name.txt": "雪夜停车场",
        "visual/scenes/scene-main--snow-parking/prompts/001000.md": "蓝色雪夜停车场主视角",
        "visual/scenes/scene-main--snow-parking/requirements/001000.md": "环境基准图",
        "visual/scenes/scene-main--snow-parking/references/001000--001000.ref": video_ref,
        "visual/scenes/scene-main--snow-parking/selected.ref": scene_ref,
        "post/sections/s1/sequence/001000--u-r2v.ref": r2v_video_ref,
        "post/sections/s1/sequence/002000--u-edit.ref": edit_video_ref,
        "post/sections/s1/transitions/001000--002000.txt": "cut",
        "post/sections/s1/audio-plan.md": "先环境声，后保留实拍原声。",
        "post/sections/s1/subtitles.vtt": "WEBVTT\n\n00:00.000 --> 00:02.000\n雪夜出发",
        "post/sections/s1/rendered-video.ref": section_video_ref,
        "post/final/sequence/001000--s1.ref": section_video_ref,
        "post/final/audio-plan.md": "统一响度。",
        "post/final/mix.md": "-14 LUFS",
        "post/final/subtitles.vtt": "WEBVTT\n\n00:00.000 --> 00:02.000\n雪夜出发",
        "post/final/rendered-video.ref": final_video_ref,
    }
    target_versions = {
        "project:header": "ov-header-4",
        "project:plan": "ov-plan-8",
        "project:assets": "ov-assets-6",
        "section:s1": "ov-section-s1-9",
        "section:s1/narrative": "ov-section-s1-narrative-3",
        "unit:u-r2v": "ov-unit-r2v-12",
        "unit:u-edit": "ov-unit-edit-15",
        "shot:shot-1": "ov-shot-1-2",
        "asset:scene-a": "ov-asset-scene-select-2",
        "asset:upload-video-01": "ov-asset-video-select-7",
        "asset:scene-main": "ov-visual-scene-main-4",
        "post:s1": "ov-post-section-s1-5",
        "post:final": "ov-post-final-3",
    }
    snapshot = TextWorkspaceSnapshot(
        project_id="p1",
        revision_id="revision-17",
        files=_file_map(contents),
        target_versions=target_versions,
    )
    catalogs = ProjectionCatalogs(
        assets=tuple(assets.values()),
        artifacts=tuple(artifacts.values()),
    )
    selections = RevisionSelections(
        revision_id="revision-17",
        artifact_versions={
            artifacts["storyboard"].slot_id: artifacts["storyboard"].id,
            artifacts["r2v_video"].slot_id: artifacts["r2v_video"].id,
            artifacts["edit_video"].slot_id: artifacts["edit_video"].id,
            artifacts["section_video"].slot_id: artifacts["section_video"].id,
            artifacts["final_video"].slot_id: artifacts["final_video"].id,
        },
    )
    provider = ProviderConstraintSnapshot(
        provider="bailian",
        model="wan2.7-r2v",
        version="2026-07-10",
        captured_at="2026-07-10T02:00:00Z",
        min_duration=4,
        max_duration=15,
        max_reference_images=5,
        allowed_durations=(5, 10, 15),
    )
    return ProjectionFixture(
        snapshot,
        catalogs,
        selections,
        provider,
        ai_edit_plan,
        artifacts,
        assets,
    )
