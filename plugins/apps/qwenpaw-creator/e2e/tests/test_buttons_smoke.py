# -*- coding: utf-8 -*-
"""Non-destructive browser smoke tests for the current Creator shell."""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from pages.home_page import HomePage

pytestmark = pytest.mark.buttons


def test_home_loads_project_list(page, api):
    r = api.get("/projects")
    assert r.status_code == 200
    HomePage(page).open()
    expect(page.get_by_role("heading", name="我的项目")).to_be_visible()


def test_open_composer_uses_current_contract(page):
    composer = HomePage(page).open().open_composer()
    expect(
        page.get_by_role("heading", name="把目标、素材和限制交给 Agent"),
    ).to_be_visible()
    expect(
        page.get_by_text(
            "资料输入是一次性的启动动作。进入项目后，它们会变成可管理、可引用、可追踪的项目资产。",
            exact=True,
        ),
    ).to_be_visible()
    composer.select_scenario("通用")
    composer.fill_name("E2E 冒烟项目").fill_goal("只验证当前 Composer，不启动生产")
    composer.add_url("https://example.com/ref.mp4")
    expect(
        composer.attachment_chip("https://example.com/ref.mp4"),
    ).to_be_visible()
    expect(
        composer.root.get_by_role("button", name="启动 Agent", exact=True),
    ).to_be_enabled()
    expect(composer.root).to_have_css("width", "720px")


def test_model_config_single_file_values_are_visible_in_api_and_ui(page, api):
    config = api.models_config()
    assert set(config) == {
        "llm",
        "vlm",
        "asr",
        "image",
        "video",
        "oss",
        "executionAuthorization",
    }
    for model_type in ("llm", "vlm", "asr", "image", "video"):
        assert isinstance(config[model_type]["api_key"], str)
    HomePage(page).open().open_model_config()
    modal = page.locator(".model-config-modal")
    tabs = modal.locator("button.segmented-tab")
    expect(tabs).to_have_count(6)
    for index, model_type in enumerate(
        ("llm", "vlm", "asr", "image", "video"),
    ):
        tabs.nth(index).click()
        if model_type == "vlm" and config["vlm"]["use_llm"]:
            expect(
                modal.get_by_role("checkbox", name="复用 LLM 配置"),
            ).to_be_checked()
            expect(
                modal.get_by_placeholder("sk-...", exact=True),
            ).to_have_count(0)
            continue
        expect(modal.get_by_placeholder("sk-...", exact=True)).to_have_value(
            config[model_type]["api_key"],
        )


def test_create_and_delete_project_via_api(api):
    project = api.create_project(f"E2E contract {uuid4().hex[:8]}")
    pid = project["projectId"]
    assert project["creatorSessionId"]
    assert project["conversationId"]
    assert project["approvedRevisionId"]
    try:
        header = api.get_project(pid)
        assert header["projectId"] == pid
        session = api.get(f"/projects/{pid}/session")
        assert session.status_code == 200
        assert session.json()["session"]["status"] == "IDLE"
        tasks = api.get(f"/projects/{pid}/tasks")
        assert tasks.status_code == 200
        assert tasks.json()["items"] == []
    finally:
        api.delete_project(pid)
    assert api.get(f"/projects/{pid}/header").status_code == 404
