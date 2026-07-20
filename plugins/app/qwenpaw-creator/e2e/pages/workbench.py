# -*- coding: utf-8 -*-
"""Page object for the retained origin/main R2V and AI Edit workbenches."""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page


class WorkbenchPage:
    def __init__(self, page: Page):
        self.page = page

    def open(self, project_id: str, unit_id: str):
        self.page.goto(f"/#/project/{project_id}/plan/unit/{unit_id}/workbench")
        return self

    def wait_kind(self, kind: str):
        action = {
            "R2V": "生成分镜 Prompt",
            "AI Edit": "生成剪辑方案",
            "edit": "生成剪辑方案",
        }.get(kind)
        if action is None:
            raise ValueError(f"未知 Workbench 类型：{kind}")
        self.page.get_by_role("button", name=action, exact=True).wait_for()
        return self

    def panel(self, title: str | re.Pattern[str]) -> Locator:
        heading = self.page.get_by_role("heading", name=title)
        return heading.locator("xpath=ancestor::section[1]")

    def generate_storyboard_prompt(self):
        self.page.get_by_role("button", name="生成分镜 Prompt", exact=True).click()
        return self

    def submit_r2v(self):
        self.page.get_by_role("button", name="生成视频", exact=True).click()
        return self

    def generate_edit_plan(self):
        self.page.get_by_role("button", name="生成剪辑方案", exact=True).click()
        return self

    def execute_edit(self):
        self.page.get_by_role("button", name="执行剪辑", exact=True).click()
        return self
