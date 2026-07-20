# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Page object for the retained origin/main Plan and Compose surfaces."""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page


class PlanPage:
    def __init__(self, page: Page):
        self.page = page

    def open(self, project_id: str):
        self.page.goto(f"/#/project/{project_id}/plan")
        self.page.get_by_role("heading", name="视频方案", exact=True).wait_for()
        return self

    def section_card(self, section_id: str) -> Locator:
        return self.page.locator(
            f"[data-creator-module='section-card'][data-creator-module-id='{section_id}']",
        )

    def select_section(self, section_id: str):
        self.section_card(section_id).click()
        return self

    def select_unit(self, unit_id: str):
        self.page.goto(
            f"{self.page.url.split('#')[0]}#/project/"
            f"{self._project_id()}/plan?unit={unit_id}",
        )
        return self

    def add_section(self):
        self.page.get_by_role("button", name="添加结构段", exact=True).click()
        return self

    def plan_units(self):
        self.page.get_by_role("button", name="Agent 规划任务", exact=True).click()
        return self

    def open_script_generator(self):
        self.page.get_by_role("button", name="生成结构", exact=True).click()
        self.page.get_by_text("从主题生成剧本", exact=True).wait_for()
        return self

    def open_final_compose(self):
        self.page.get_by_role("button", name="最终合成", exact=True).click()
        self.page.get_by_text("最终剪辑视频合成", exact=True).wait_for()
        return self

    def open_section_compose(self, project_id: str, section_id: str):
        self.page.goto(f"/#/project/{project_id}/plan/section/{section_id}")
        self.page.get_by_role(
            "heading",
            name=re.compile(r"拼接与预览："),
        ).wait_for()
        return self

    def _project_id(self) -> str:
        match = re.search(r"/project/([^/]+)/plan", self.page.url)
        if not match:
            raise AssertionError(f"当前不是 Plan URL：{self.page.url}")
        return match.group(1)
