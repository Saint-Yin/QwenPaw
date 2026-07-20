# -*- coding: utf-8 -*-
"""Frozen provider constraints exercised only through the new R2V path."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.validators.r2v import (
    ProviderCapabilitySnapshot,
    R2VExecutionRequest,
    validate_r2v_execution,
)
from services.validators.unit_segments import (
    normalize_storyboard_segments,
    storyboard_segments_fit_r2v_limit,
    summarize_storyboard_normalization,
)


pytestmark = pytest.mark.unit


def _capability() -> ProviderCapabilitySnapshot:
    return ProviderCapabilitySnapshot(
        provider="seedance2",
        model="doubao-seedance-2-0-260128",
        version="frozen-provider-contract-v1",
        captured_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        min_duration_seconds=4,
        max_duration_seconds=15,
        max_reference_images=5,
    )


def _request(
    *,
    duration: float = 4,
    storyboard: str | None = "artifact:storyboard-v1",
    refs: tuple[str, ...] = (
        "artifact:storyboard-v1",
        "asset:character-v1",
        "asset:scene-v1",
        "asset:prop-v1",
        "artifact:continuity-v1",
    ),
) -> R2VExecutionRequest:
    return R2VExecutionRequest(
        unit_ref="unit:u1",
        route="r2v",
        duration_seconds=duration,
        storyboard_version_ref=storyboard,
        storyboard_checksum="sha256:storyboard" if storyboard else None,
        video_prompt="镜头1中景，人物缓慢抬手。",
        reference_image_refs=refs,
        transaction_active=True,
        input_fingerprint="sha256:input",
        expected_slot_generation=2,
        observed_slot_generation=2,
        capability=_capability(),
    )


@pytest.mark.parametrize("duration", [4, 15])
def test_provider_accepts_inclusive_four_to_fifteen_second_boundary(
    duration: int,
) -> None:
    assert validate_r2v_execution(_request(duration=duration)).valid is True


@pytest.mark.parametrize(
    ("execution_request", "expected_code"),
    [
        (_request(duration=3), "R2V_PROVIDER_DURATION"),
        (_request(duration=16), "R2V_DURATION_MAX"),
        (
            _request(storyboard=None, refs=("asset:character-v1",)),
            "R2V_STORYBOARD_REQUIRED",
        ),
        (
            _request(
                refs=(
                    "asset:character-v1",
                    "artifact:storyboard-v1",
                ),
            ),
            "R2V_STORYBOARD_FIRST",
        ),
        (
            _request(
                refs=(
                    "artifact:storyboard-v1",
                    "asset:1",
                    "asset:2",
                    "asset:3",
                    "asset:4",
                    "asset:5",
                ),
            ),
            "R2V_REFERENCE_LIMIT",
        ),
    ],
)
def test_provider_rejects_out_of_range_storyboard_or_reference_manifest(
    execution_request: R2VExecutionRequest,
    expected_code: str,
) -> None:
    report = validate_r2v_execution(execution_request)
    assert report.valid is False
    assert expected_code in {issue.code for issue in report.issues}


def test_unit_normalization_golden_summary_and_renumbering() -> None:
    source = [
        {
            "segment_number": 9,
            "title": "连续动作",
            "shots": [
                {
                    "shot_number": 7,
                    "title": "起身",
                    "duration": 8,
                    "dialogue": "",
                },
                {
                    "shot_number": 8,
                    "title": "奔跑",
                    "duration": 8,
                    "dialogue": "快走",
                },
            ],
        },
    ]

    normalized = normalize_storyboard_segments(source)

    assert [segment["duration"] for segment in normalized] == [8, 8]
    assert [segment["segment_number"] for segment in normalized] == [1, 2]
    assert [segment["shots"][0]["shot_number"] for segment in normalized] == [
        1,
        1,
    ]
    assert normalized[1]["shots"][0]["dialogue"] == "快走"
    assert all(
        segment["split_reason"] == "r2v_15_second_limit"
        for segment in normalized
    )
    assert storyboard_segments_fit_r2v_limit(normalized) is True
    assert summarize_storyboard_normalization(source, normalized) == {
        "input_segment_count": 1,
        "output_clip_count": 2,
        "split_segment_count": 1,
        "split_shot_count": 0,
        "max_clip_duration_seconds": 15,
        "fits_r2v_limit": True,
    }
