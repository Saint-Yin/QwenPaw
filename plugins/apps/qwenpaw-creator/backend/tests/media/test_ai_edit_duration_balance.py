# -*- coding: utf-8 -*-
# pylint: disable=protected-access
from __future__ import annotations

from copy import deepcopy

import pytest

from services.media.ai_edit import core


pytestmark = pytest.mark.unit


def _plan_with_duration(total: float) -> dict:
    durations = [8.0] * int(total // 8)
    if total % 8:
        durations.append(total % 8)
    cursor = 0.0
    timeline = []
    for index, duration in enumerate(durations, 1):
        timeline.append(
            {
                "clip_id": f"clip-{index:02d}",
                "asset_id": "asset-1",
                "start": cursor,
                "end": cursor + duration,
                "duration": duration,
                "order": index,
            },
        )
        cursor += duration
    return {
        "summary": "highlights",
        "target_duration": total,
        "timeline": timeline,
        "storyboard": [],
    }


def test_duration_balancer_supplements_plan_below_completion_tolerance(
    monkeypatch,
) -> None:
    filler = {
        "timeline": [
            {
                "asset_id": "asset-1",
                "asset_name": "cat.mp4",
                "start": 120.0,
                "end": 128.0,
                "duration": 8.0,
                "order": 1,
                "reason": "additional highlight",
            },
        ],
    }
    monkeypatch.setattr(
        core,
        "_heuristic_plan",
        lambda *args, **kwargs: filler,
    )

    balanced = core._ensure_target_duration(
        deepcopy(_plan_with_duration(51.0)),
        {},
        {"duration": 60},
        [],
        "one-minute highlights",
    )

    assert balanced["target_duration"] == 59.0
    assert len(balanced["timeline"]) == 8


def test_duration_balancer_preserves_plan_at_completion_tolerance(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        core,
        "_heuristic_plan",
        lambda *args, **kwargs: pytest.fail("filler should not be built"),
    )
    plan = _plan_with_duration(54.0)

    assert (
        core._ensure_target_duration(
            deepcopy(plan),
            {},
            {"duration": 60},
            [],
            "one-minute highlights",
        )
        == plan
    )
