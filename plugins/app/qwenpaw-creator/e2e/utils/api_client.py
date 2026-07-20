# -*- coding: utf-8 -*-
"""Small client for the current, unique Creator REST surface."""
from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import requests

import config as e2e_config


class CreatorApiClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/") + e2e_config.API_PREFIX
        self.session = requests.Session()

    # ── 基础 ────────────────────────────────────────────────────────
    def health_ok(self, timeout: int = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self.session.get(f"{self.base}/health", timeout=5)
                payload = r.json()
                if r.status_code == 200 and payload.get("status") == "ok" and (
                    payload.get("runtime") == "creator-filesystem"
                ):
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)
        return False

    def get(self, path: str, **kw) -> requests.Response:
        return self.session.get(f"{self.base}{path}", timeout=kw.pop("timeout", 30), **kw)

    def post(self, path: str, json: dict[str, Any] | None = None, **kw) -> requests.Response:
        return self.session.post(f"{self.base}{path}", json=json, timeout=kw.pop("timeout", 60), **kw)

    def put(self, path: str, json: dict[str, Any] | None = None, **kw) -> requests.Response:
        return self.session.put(f"{self.base}{path}", json=json, timeout=kw.pop("timeout", 60), **kw)

    def delete(self, path: str, **kw) -> requests.Response:
        return self.session.delete(f"{self.base}{path}", timeout=kw.pop("timeout", 30), **kw)

    def post_file(self, path: str, files: dict, data: dict | None = None, **kw) -> requests.Response:
        return self.session.post(
            f"{self.base}{path}", files=files, data=data or {},
            timeout=kw.pop("timeout", 120), **kw,
        )

    def wait_task(
        self,
        project_id: str,
        task_id: str,
        *,
        timeout: float = 30,
        interval: float = 0.2,
    ) -> dict[str, Any]:
        """Poll only the public Task endpoint until its immutable terminal result."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = self.get(f"/projects/{project_id}/tasks/{task_id}")
            response.raise_for_status()
            task = response.json()
            if task["status"] in {
                "SUCCEEDED", "FAILED", "CANCELLED", "QUARANTINED"
            }:
                return task
            time.sleep(interval)
        raise AssertionError(f"Task {task_id} did not reach a terminal state in {timeout}s")

    def command(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> requests.Response:
        key = idempotency_key or str(payload["clientCommandId"])
        return self.post(
            f"/projects/{project_id}/commands",
            json=payload,
            headers={"Idempotency-Key": key},
        )

    # ── 项目 ────────────────────────────────────────────────────────
    def create_project(
        self,
        name: str,
        *,
        description: str = "E2E contract project; no initial Goal is created.",
        scenario: str = "general",
    ) -> dict[str, Any]:
        client_id = f"e2e-project-{uuid4()}"
        r = self.post(
            "/projects",
            json={
                "clientRequestId": client_id,
                "name": name,
                "description": description,
                "scenario": scenario,
                "aspectRatio": "16:9",
                "resolution": "720P",
                "contentType": None,
            },
            headers={"Idempotency-Key": client_id},
        )
        r.raise_for_status()
        return r.json()

    def get_project(self, project_id: str) -> dict:
        r = self.get(f"/projects/{project_id}/header")
        r.raise_for_status()
        return r.json()

    def delete_project(self, project_id: str) -> None:
        key = f"e2e-delete-{uuid4()}"
        response = self.session.delete(
            f"{self.base}/projects/{project_id}",
            headers={"Idempotency-Key": key},
            timeout=30,
        )
        if response.status_code not in (204, 404):
            response.raise_for_status()

    def view(self, project_id: str, suffix: str) -> dict[str, Any]:
        response = self.get(f"/projects/{project_id}/{suffix.lstrip('/')}")
        response.raise_for_status()
        return response.json()

    def models_config(self) -> dict[str, Any]:
        response = self.get("/models/config")
        response.raise_for_status()
        return response.json()
