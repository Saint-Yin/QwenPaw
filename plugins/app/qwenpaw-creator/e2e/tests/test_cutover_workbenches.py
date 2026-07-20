# -*- coding: utf-8 -*-
"""Cutover data rendered in the retained origin/main Plan/Workbench surfaces."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from pages.plan_page import PlanPage
from pages.workbench import WorkbenchPage

pytestmark = pytest.mark.cutover


def _presentation(envelope: dict) -> dict:
    view = envelope["view"]
    return view["view"] if "presentationVersion" in view else view


def test_r2v_cutover_view_and_origin_media_surface(page, api, cutover_ids):
    pid = cutover_ids["r2v_project"]
    unit_id = cutover_ids["r2v_unit"]
    plan = _presentation(api.view(pid, "plan"))
    units = [unit for section in plan["sections"] for unit in section["units"]]
    assert len(plan["sections"]) == 1
    assert len(units) == 4
    assert sum(unit["duration"] for unit in units) == 28

    workbench = _presentation(api.view(pid, f"units/{unit_id}/workbench"))
    assert workbench["kind"] == "r2v"
    assert workbench["storyboardVersions"]
    assert workbench["storyboardPrompt"]
    assert workbench["videoPrompt"]

    surface = WorkbenchPage(page).open(pid, unit_id).wait_kind("R2V")
    for action in ("生成分镜 Prompt", "生成分镜图", "生成视频 Prompt", "生成视频"):
        expect(page.get_by_role("button", name=action, exact=True)).to_be_visible()
    for panel in ("分镜文本", "分镜Prompt与分镜图", "视频结果", "资产绑定"):
        expect(page.get_by_role("heading", name=panel, exact=True)).to_be_visible()

    image = page.get_by_role("img", name="分镜图", exact=True)
    expect(image).to_be_visible()
    page.wait_for_function("node => node.naturalWidth > 0", arg=image.element_handle())
    video = surface.panel("视频结果").locator("video")
    if workbench["videoVersions"]:
        expect(video).to_be_visible()
        page.wait_for_function("node => node.readyState >= 1", arg=video.element_handle())


def test_edit_cutover_nested_plan_in_origin_vlm_and_timeline_panels(page, api, cutover_ids):
    pid = cutover_ids["edit_project"]
    unit_id = cutover_ids["edit_unit"]
    workbench = _presentation(api.view(pid, f"units/{unit_id}/workbench"))
    assert workbench["kind"] == "edit"
    assert set(workbench) >= {
        "plan", "storyboard_image_url", "material_assets", "workflow_trace",
        "videoVersions", "targetVersion", "uiLocator",
    }
    plan = workbench["plan"]
    assert plan is not None
    assert len(plan["timeline"]) == 7
    assert len(plan["storyboard"]) == 7
    assert plan["target_duration"] == 56
    assert workbench["videoVersions"]

    surface = WorkbenchPage(page).open(pid, unit_id).wait_kind("AI Edit")
    expect(page.get_by_role("button", name="生成剪辑方案", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="执行剪辑", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="剪辑目标", exact=True)).to_be_visible()
    storyboard_panel = surface.panel("VLM 关键帧分镜")
    expect(storyboard_panel.get_by_text("7 panels", exact=True)).to_be_visible()
    expect(storyboard_panel.locator("input[type=number]")).to_have_count(14)
    preview_videos = storyboard_panel.locator("video")
    expect(preview_videos).to_have_count(7)
    for index in range(7):
        page.wait_for_function(
            "node => node.readyState >= 1",
            arg=preview_videos.nth(index).element_handle(),
        )
    expect(page.get_by_role("heading", name="剪辑时间线（7）", exact=True)).to_be_visible()
    expect(page.get_by_text("56s", exact=True).first).to_be_visible()

    rendered = surface.panel("剪辑成片").locator("video")
    expect(rendered).to_be_visible()
    page.wait_for_function("node => node.readyState >= 1", arg=rendered.element_handle())


def test_plan_section_and_final_compose_keep_origin_surfaces_and_truthful_blockers(
    page, api, cutover_ids
):
    pid = cutover_ids["r2v_project"]
    section_id = cutover_ids["r2v_section"]
    plan_page = PlanPage(page).open(pid)
    expect(page.get_by_text("28s", exact=True).first).to_be_visible()
    section_card = plan_page.section_card(section_id)
    expect(section_card).to_be_visible()
    expect(section_card.get_by_text("R2V生成", exact=True)).to_have_count(4)

    section = _presentation(api.view(pid, f"post/sections/{section_id}"))
    final = _presentation(api.view(pid, "post/final"))
    assert section["readiness"]["ready"] is False and section["blockers"]
    # origin/main Final Compose accepts any valid non-empty Section/Unit
    # subset; absence of a pre-persisted full-Section sequence is not a
    # blocker. The modal initializes the accepted Unit fallback locally.
    assert final["readiness"]["ready"] is True
    assert final["blockers"] == []

    plan_page.open_section_compose(pid, section_id)
    expect(page.get_by_text("拼接前置条件未满足", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name=re.compile(r"^单元视频清单（\d+ 个）$"))).to_be_visible()

    page.goto(f"/#/project/{pid}/plan?finalCompose=1")
    expect(page.get_by_text("最终剪辑视频合成", exact=True)).to_be_visible()
    if final["candidates"]:
        source_label = "单元成片" if final["candidates"][0].get("sourceKind") == "unit" else "整段成片"
        expect(page.get_by_text(source_label, exact=True).first).to_be_visible()
    else:
        expect(page.get_by_text(
            "暂无可用成片：请先生成并接受 Unit 视频，或先完成 Section 拼接",
            exact=True,
        )).to_be_visible()
        expect(page.get_by_role("button", name=re.compile(r"执行合成$"))).to_be_disabled()
    expect(page.get_by_text("存在阻断项", exact=True)).to_have_count(0)


def test_removed_canvas_route_is_not_resurrected(page, cutover_ids):
    page.goto(f"/#/project/{cutover_ids['r2v_project']}/canvas")
    expect(page.get_by_text("页面未找到", exact=True)).to_be_visible()
