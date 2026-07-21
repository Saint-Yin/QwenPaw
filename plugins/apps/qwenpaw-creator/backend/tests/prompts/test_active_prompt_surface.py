# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

import json

from domain.enums import SpecialistRole
from services.file_agent_runtime.prompts import (
    FILE_AGENT_PROMPT_SPECS,
    load_file_agent_prompt,
    render_creator_system_prompt,
)
from services.file_agent_runtime.subagents import (
    delegate_tool_manifest,
    specialist_system_prompt,
)
from services.project_files.models import Project

_INACTIVE_STATE_WORDS = {
    "已取消",
    "已禁用",
    "已删除",
    "review-disabled",
}


def _active_prompt_texts() -> list[str]:
    project = Project.new(project_id="project-prompt-test", name="Prompt Test")
    texts = [
        render_creator_system_prompt(
            project_id=project.project_id,
        ),
        json.dumps(delegate_tool_manifest(), ensure_ascii=False),
    ]
    texts.extend(
        specialist_system_prompt(
            role,
            project_id=project.project_id,
            project=project,
        )
        for role in (
            SpecialistRole.SOURCE_INTELLIGENCE,
            SpecialistRole.VISUAL_DEVELOPMENT,
            SpecialistRole.R2V_GENERATION_DIRECTOR,
            SpecialistRole.AI_EDITING_DIRECTOR,
        )
    )
    return texts


def test_active_prompts_do_not_describe_inactive_states() -> None:
    combined = "\n".join(_active_prompt_texts())
    for token in _INACTIVE_STATE_WORDS:
        assert token not in combined


def test_file_runtime_prompts_are_structured_files_with_workspace_schema() -> None:
    assert set(FILE_AGENT_PROMPT_SPECS) == {
        "creator_agent.system",
        "source_intelligence_agent.system",
        "visual_development_agent.system",
        "r2v_generation_director.system",
        "ai_editing_director.system",
    }
    for prompt_id in FILE_AGENT_PROMPT_SPECS:
        raw = load_file_agent_prompt(prompt_id)
        assert raw.startswith("# 定位")
        assert "# 核心职责" in raw
        assert "# Workspace 基础 Schema" in raw
        assert "{{workspace_schema}}" in raw
        assert "# 标准流程" in raw
        assert "# 工具使用原则" in raw
        assert "# 限制" in raw

    for rendered in _active_prompt_texts():
        if rendered.startswith("# 定位"):
            assert "./project.json" in rendered
            assert "./assets/source-intelligence/*" in rendered
            assert "PROJECT_JSON_SCHEMA=" in rendered


def test_creator_asset_flow_is_conditional_and_uses_visible_message_language() -> None:
    prompt = load_file_agent_prompt("creator_agent.system")
    assert "处理本轮上传素材（如有）" in prompt
    assert "没有该段落时" in prompt
    assert "本轮已入库素材" in prompt
    assert "CURRENT_REQUEST_ASSET_VERSION_REFS" not in prompt


def test_creator_owns_timeline_element_planning() -> None:
    prompt = load_file_agent_prompt("creator_agent.system")
    for responsibility in (
        "Timeline Element",
        "creation.type=r2v/edit/overlay/transition/audio",
        "单个 R2V Element 不超过 15 秒",
        "elements_at",
        "jq_project",
    ):
        assert responsibility in prompt
    assert "结构完成后才进入视觉和媒体生产" in prompt
    assert "完整 Project 根对象" in prompt
    assert "jsonArgs" in prompt
    assert "content_type=pet_video" in prompt
    assert "overlay_kind=pet_os" in prompt
    assert "x=0.5, y=0.5" in prompt


def test_source_prompt_requires_outer_vlm_timeline_and_controlled_commit() -> None:
    prompt = load_file_agent_prompt("source_intelligence_agent.system")
    assert "唯一 VLM 生产者" in prompt
    assert "不得把理解工作转交给另一个 VLM" in prompt
    assert "至少覆盖 90% 时长" in prompt
    assert "整数毫秒半开区间 `[startMs,endMs)`" in prompt
    assert "transcribe_source_audio" in prompt
    assert "commit_source_intelligence" in prompt
    assert "ceil(durationMs / 90000)" in prompt
    assert "跨度不超过 30000ms" in prompt
    assert "不得创建 Timeline Element" in prompt
    assert "`jq_project`" not in prompt
    assert "不得降低为一条 summary" in prompt


def test_ai_editing_director_requires_pet_inner_monologue_not_action_labels() -> None:
    prompt = load_file_agent_prompt("ai_editing_director.system")
    for field in ("overlay_kind=pet_os", "文案", "`vibe`", "绝对 span"):
        assert field in prompt
    assert "不是镜头标题、动作标签或客观摘要" in prompt
    assert "不再使用相对某个内部对象" in prompt
    assert "多个选择就是多个 Element" in prompt
    assert "round((source_out_tick - source_in_tick) / playback_rate)" in prompt
    assert "jsonArgs.elements" in prompt
    assert "不是可选项" in prompt
