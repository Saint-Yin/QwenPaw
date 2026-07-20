# -*- coding: utf-8 -*-
"""Shared fixtures for current Creator browser acceptance."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

import config as e2e_config  # noqa: E402
from utils.api_client import CreatorApiClient  # noqa: E402


@pytest.fixture(scope="session")
def base_url() -> str:
    return e2e_config.BASE_URL


@pytest.fixture(scope="session")
def api(base_url: str) -> CreatorApiClient:
    """直连前端代理的 REST 客户端（/api/creator/...），用于前置数据与断言。"""
    return CreatorApiClient(base_url)


@pytest.fixture(scope="session", autouse=True)
def require_services(api: CreatorApiClient):
    """Require the Vite proxy and current Creator runtime to be reachable."""
    if not api.health_ok(timeout=30):
        message = (
            f"Creator 服务未就绪：{e2e_config.BASE_URL}{e2e_config.API_PREFIX}/health。"
            "请先启动当前 backend 与 Vite UI。"
        )
        if e2e_config.STRICT:
            pytest.fail(message)
        pytest.skip(message, allow_module_level=True)
    yield


@pytest.fixture(scope="session")
def cutover_ids(api: CreatorApiClient) -> dict[str, str]:
    ids = {
        "r2v_project": e2e_config.R2V_PROJECT_ID,
        "r2v_unit": e2e_config.R2V_UNIT_ID,
        "r2v_section": e2e_config.R2V_SECTION_ID,
        "edit_project": e2e_config.EDIT_PROJECT_ID,
        "edit_unit": e2e_config.EDIT_UNIT_ID,
        "asset_project": e2e_config.ASSET_PROJECT_ID,
    }
    missing = [
        project_id for project_id in {
            ids["r2v_project"], ids["edit_project"], ids["asset_project"]
        }
        if api.get(f"/projects/{project_id}/header").status_code != 200
    ]
    if missing:
        message = "当前数据根不是完整 cutover rehearsal，缺少：" + ", ".join(missing)
        if e2e_config.STRICT:
            pytest.fail(message)
        pytest.skip(message)
    return ids


@pytest.fixture(scope="session")
def pending_review_target(api: CreatorApiClient) -> dict:
    """Find a public PENDING_REVIEW fixture with two independent pending groups.

    There is intentionally no test-only seal or database seed.  A release run
    must first create this state through the normal Creator API/UI, then either
    export CREATOR_E2E_PENDING_PROJECT_ID or let discovery find it.
    """
    explicit = e2e_config.PENDING_PROJECT_ID
    if explicit:
        candidates = [explicit]
    else:
        response = api.get("/projects", params={"limit": 500, "offset": 0})
        response.raise_for_status()
        candidates = [item["projectId"] for item in reversed(response.json()["items"])]

    rejection_reasons: list[str] = []
    for project_id in candidates:
        session_response = api.get(f"/projects/{project_id}/session")
        if session_response.status_code != 200:
            rejection_reasons.append(f"{project_id}: session {session_response.status_code}")
            continue
        session = session_response.json()["session"]
        if session["status"] != "PENDING_REVIEW":
            rejection_reasons.append(f"{project_id}: {session['status']}")
            continue
        transaction_id = (
            e2e_config.PENDING_TRANSACTION_ID or session.get("activeTransactionId")
        )
        if not transaction_id:
            rejection_reasons.append(f"{project_id}: missing activeTransactionId")
            continue
        review_response = api.get(
            f"/projects/{project_id}/transactions/{transaction_id}/review"
        )
        if review_response.status_code != 200:
            rejection_reasons.append(
                f"{project_id}: review {review_response.status_code}"
            )
            continue
        manifest = review_response.json()
        pending_groups = [
            item for item in manifest["decisionGroups"] if item["decision"] == "PENDING"
        ]
        if len(pending_groups) < 2:
            rejection_reasons.append(
                f"{project_id}: only {len(pending_groups)} pending decision group(s)"
            )
            continue
        return {
            "projectId": project_id,
            "transactionId": transaction_id,
            "session": session,
            "manifest": manifest,
        }

    message = (
        "缺少可由公开 API 读取的 PENDING_REVIEW 验收项目（至少两个独立 PENDING "
        "Decision Group）。请先通过真实 Creator 流程完成并 seal 修改，再设置 "
        "CREATOR_E2E_PENDING_PROJECT_ID；测试不会使用内部 DB 伪造。"
    )
    if explicit and rejection_reasons:
        message += " 当前候选：" + "; ".join(rejection_reasons[:5])
    if e2e_config.STRICT:
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture()
def browser_context_args(browser_context_args, base_url):
    """Stable desktop viewport for the three-column and workbench layouts."""
    return {**browser_context_args, "viewport": {"width": 1440, "height": 900}, "base_url": base_url}
