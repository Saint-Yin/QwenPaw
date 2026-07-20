# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Unified origin Assets grid, Inspector media, and durable supplement upload."""
from __future__ import annotations

import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.assets, pytest.mark.cutover]


def _presentation(envelope: dict) -> dict:
    view = envelope["view"]
    return view["view"] if "presentationVersion" in view else view


def test_asset_library_origin_categories_grid_inspector_and_video_metadata(
    page,
    api,
    cutover_ids,
):
    pid = cutover_ids["asset_project"]
    view = _presentation(api.view(pid, "assets"))
    assert len(view["availableAssets"]) == 1
    asset = view["availableAssets"][0]
    assert asset["mediaType"] == "video"
    assert asset["durationSeconds"] > 1900
    assert any(
        item["id"] == asset["assetId"] for item in view["presentationAssets"]
    )

    page.goto(f"/#/project/{pid}/assets")
    expect(
        page.get_by_role("heading", name=re.compile(r"^资产库")),
    ).to_be_visible()
    category_column = page.locator("aside").filter(
        has=page.get_by_placeholder("搜索资产...", exact=True),
    )
    expect(category_column).to_be_visible()
    expect(page.get_by_test_id("asset-grid-column")).to_be_visible()
    upload_count = sum(
        item["category"] == "upload" for item in view["presentationAssets"]
    )
    category_column.get_by_role(
        "button",
        name=f"用户上传 {upload_count}",
    ).click()

    card = page.locator(
        f"[data-asset-id='{asset['assetId']}'][data-asset-version='{asset['assetVersionId']}']",
    )
    expect(card).to_be_visible()
    card.click()
    inspector = page.locator("aside.w-80")
    expect(inspector).to_be_visible()
    expect(inspector.get_by_text("来源", exact=True)).to_be_visible()
    expect(inspector.get_by_text("作用约束", exact=True)).to_be_visible()
    video = inspector.locator("video")
    expect(video).to_be_visible()
    page.wait_for_function(
        "node => node.readyState >= 1 && node.duration > 1900",
        arg=video.element_handle(),
    )


def test_origin_supplement_file_upload_sends_durable_attach_action(
    page,
    api,
    tmp_path,
):
    project = api.create_project(f"E2E supplement form {uuid4().hex[:8]}")
    pid = project["projectId"]
    source = tmp_path / "source.txt"
    source.write_text("immutable supplement source", encoding="utf-8")

    try:
        page.goto(f"/#/project/{pid}/assets")
        expect(
            page.get_by_role("heading", level=1, name=re.compile(r"^资产库")),
        ).to_be_visible()
        page.get_by_role("button", name="补充资料", exact=True).first.click()
        modal = page.locator(".ant-modal").filter(
            has=page.get_by_text("补充资料", exact=True),
        )
        expect(modal).to_be_visible()
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith(f"/projects/{pid}/assets"),
        ) as pending:
            modal.locator("input[type=file]").set_input_files(str(source))
        response = pending.value
        assert response.status == 202
        assert response.request.headers["content-type"].startswith(
            "multipart/form-data;",
        )
        accepted = response.json()
        task = api.wait_task(pid, accepted["taskId"])
        assert task["status"] == "SUCCEEDED", task
        assert task["transactionId"] is None
        assert task["result"]["followUp"]["type"] == "ATTACH_SOURCE_ASSETS"
        version_ref = next(
            ref
            for ref in task["resultRefs"]
            if ref.startswith("asset-version:")
        )
        content = api.get(
            f"/projects/{pid}/assets/{accepted['assetId']}/content",
            params={"versionId": version_ref.split(":", 1)[1]},
        )
        assert content.status_code == 200
        assert content.content == source.read_bytes()
        expect(modal).to_be_hidden()
    finally:
        stop_key = f"e2e-supplement-stop-{uuid4()}"
        api.post(
            f"/projects/{pid}/interrupt",
            json={},
            headers={"Idempotency-Key": stop_key},
        )
        api.delete_project(pid)
