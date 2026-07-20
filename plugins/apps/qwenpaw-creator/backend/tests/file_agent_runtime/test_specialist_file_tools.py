# -*- coding: utf-8 -*-
from __future__ import annotations

from domain.enums import SpecialistRole
from services.file_agent_runtime.subagents import specialist_system_prompt
from services.project_files.facade import CreatorFileServices
from services.project_files.models import Project
from services.specialist_tools import FileSpecialistToolRegistry


def _names(manifest) -> set[str]:
    return {item["function"]["name"] for item in manifest}


def test_specialist_registry_owns_role_specific_media_tools(tmp_path) -> None:
    registry = FileSpecialistToolRegistry(
        CreatorFileServices.create(tmp_path.resolve()),
    )

    visual = _names(
        registry.manifest_for(
            SpecialistRole.VISUAL_DEVELOPMENT,
            admitted_target_refs=["asset:hero"],
        ),
    )
    r2v = _names(
        registry.manifest_for(
            SpecialistRole.R2V_GENERATION_DIRECTOR,
            admitted_target_refs=["unit:u1"],
        ),
    )
    editing = _names(
        registry.manifest_for(
            SpecialistRole.AI_EDITING_DIRECTOR,
            admitted_target_refs=["unit:u2"],
        ),
    )
    source = _names(
        registry.manifest_for(
            SpecialistRole.SOURCE_INTELLIGENCE,
            admitted_target_refs=["asset:source-1"],
        ),
    )

    assert "image_generation" in visual
    assert {"image_generation", "r2v_generation"} <= r2v
    assert "ai_edit" in editing
    assert "analyze_source_media" in source
    assert "jq_project" in source
    assert "r2v_generation" not in visual
    assert "image_generation" not in editing


def test_source_analysis_tool_explains_single_transient_retry(
    tmp_path,
) -> None:
    registry = FileSpecialistToolRegistry(
        CreatorFileServices.create(tmp_path.resolve()),
    )
    manifest = registry.manifest_for(
        SpecialistRole.SOURCE_INTELLIGENCE,
        admitted_target_refs=["asset:source-1"],
    )
    tool = next(
        item
        for item in manifest
        if item["function"]["name"] == "analyze_source_media"
    )["function"]

    assert "首次分析使用 force=false" in tool["description"]
    assert "ReadTimeout" in tool["description"]
    assert "重试一次" in tool["description"]
    force = tool["parameters"]["properties"]["arguments"]["properties"][
        "force"
    ]
    assert force["default"] is False
    assert "同一失败最多重试一次" in force["description"]


def test_project_assets_scope_admits_image_asset_children(tmp_path) -> None:
    registry = FileSpecialistToolRegistry(
        CreatorFileServices.create(tmp_path.resolve()),
    )
    manifest = registry.manifest_for(
        SpecialistRole.VISUAL_DEVELOPMENT,
        admitted_target_refs=["project:assets"],
    )
    tool = next(
        item
        for item in manifest
        if item["function"]["name"] == "image_generation"
    )["function"]
    target = tool["parameters"]["properties"]["targetRef"]
    spec = registry.spec_for(
        SpecialistRole.VISUAL_DEVELOPMENT,
        "image_generation",
    )

    assert spec is not None
    assert "enum" not in target
    assert target["pattern"] == r"^asset:.+$"
    assert "不能直接使用 project:assets" in target["description"]
    assert spec.admits_target_ref(
        role=SpecialistRole.VISUAL_DEVELOPMENT,
        target_ref="asset:char-cat",
        admitted_target_refs=["project:assets"],
    )
    assert not spec.admits_target_ref(
        role=SpecialistRole.VISUAL_DEVELOPMENT,
        target_ref="project:assets",
        admitted_target_refs=["project:assets"],
    )
    assert not spec.admits_target_ref(
        role=SpecialistRole.VISUAL_DEVELOPMENT,
        target_ref="unit:char-cat",
        admitted_target_refs=["project:assets"],
    )


def test_project_assets_scope_does_not_expand_for_r2v_image_tool(
    tmp_path,
) -> None:
    registry = FileSpecialistToolRegistry(
        CreatorFileServices.create(tmp_path.resolve()),
    )
    spec = registry.spec_for(
        SpecialistRole.R2V_GENERATION_DIRECTOR,
        "image_generation",
    )

    assert spec is not None
    assert not spec.admits_target_ref(
        role=SpecialistRole.R2V_GENERATION_DIRECTOR,
        target_ref="asset:char-cat",
        admitted_target_refs=["project:assets"],
    )


def test_ai_edit_rules_are_dynamic_specialist_prompt_not_runtime_state() -> (
    None
):
    project = Project.new(project_id="project-1", name="Interview")
    project.settings.content_type = "interview"
    project.settings.target_duration_seconds = 90

    prompt = specialist_system_prompt(
        SpecialistRole.AI_EDITING_DIRECTOR,
        project_id=project.project_id,
        project=project,
    )

    assert "当前内容类型是 `interview`" in prompt
    assert "60 至 120 秒" in prompt
    assert "interview_summary" in prompt
    assert "不超过 30 个汉字" in prompt
    assert "`ai_edit`" in prompt
    assert "operation=execute" not in prompt
    assert "本工具不生成 plan" not in prompt
