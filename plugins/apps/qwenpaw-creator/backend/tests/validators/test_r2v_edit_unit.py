# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from services.validators.edit_timeline import (
    EditExecutionRequest,
    EditTimelineClip,
    validate_edit_execution,
)
from services.validators.r2v import (
    ProviderCapabilitySnapshot,
    R2VExecutionRequest,
    validate_r2v_execution,
)
from services.validators.unit import (
    ActionBeat,
    ShotDefinition,
    UnitDefinition,
    validate_unit,
)


CAPABILITY = ProviderCapabilitySnapshot(
    provider="bailian",
    model="wan2.7-r2v",
    version="2026-07",
    captured_at=datetime.now(UTC),
    min_duration_seconds=4,
    max_duration_seconds=15,
    max_reference_images=5,
    allowed_durations_seconds=(5, 10, 15),
)


def test_r2v_execution_is_storyboard_first_and_at_most_15_seconds() -> None:
    valid = R2VExecutionRequest(
        unit_ref="unit:u1",
        route="r2v",
        duration_seconds=10,
        storyboard_version_ref="artifact://u1-storyboard@v2",
        storyboard_checksum="sha256:abc",
        video_prompt="人物走入雪夜",
        reference_image_refs=(
            "artifact://u1-storyboard@v2",
            "asset://hero@v3",
        ),
        transaction_active=True,
        input_fingerprint="fp",
        expected_slot_generation=2,
        observed_slot_generation=2,
        capability=CAPABILITY,
    )
    assert validate_r2v_execution(valid).valid

    invalid = replace(
        valid,
        duration_seconds=16,
        reference_image_refs=(
            "asset://hero@v3",
            "artifact://u1-storyboard@v2",
        ),
    )
    codes = {issue.code for issue in validate_r2v_execution(invalid).issues}
    assert {
        "R2V_DURATION_MAX",
        "R2V_PROVIDER_DURATION",
        "R2V_DURATION_DISCRETE",
        "R2V_STORYBOARD_FIRST",
    } <= codes


def test_r2v_storyboard_first_compares_same_exact_ref_shape() -> None:
    exact_storyboard = (
        "artifact://unit%3Afold-airplane%2Fstoryboard"
        "@artifact-version-task-storyboard"
    )
    other_reference = (
        "artifact://asset%3Agirl%2Fappearance@artifact-version-girl"
    )
    valid = R2VExecutionRequest(
        unit_ref="unit:fold-airplane",
        route="r2v",
        duration_seconds=5,
        storyboard_version_ref=exact_storyboard,
        storyboard_checksum="sha256:storyboard",
        video_prompt="女孩折叠纸飞机",
        reference_image_refs=(exact_storyboard, other_reference),
        transaction_active=True,
        input_fingerprint="fp",
        expected_slot_generation=0,
        observed_slot_generation=0,
        capability=CAPABILITY,
    )

    assert validate_r2v_execution(valid).valid
    wrong_first = replace(
        valid,
        reference_image_refs=(other_reference, exact_storyboard),
    )
    bare_id_mismatch = replace(
        valid,
        storyboard_version_ref="artifact-version-task-storyboard",
    )

    assert "R2V_STORYBOARD_FIRST" in {
        issue.code for issue in validate_r2v_execution(wrong_first).issues
    }
    assert "R2V_STORYBOARD_FIRST" in {
        issue.code for issue in validate_r2v_execution(bare_id_mismatch).issues
    }


def test_edit_over_15_seconds_is_valid_and_does_not_require_asr_or_ocr() -> (
    None
):
    request = EditExecutionRequest(
        unit_ref="unit:e1",
        route="edit",
        material_version_refs=("asset://source@v7",),
        plan_version_ref="ai-edit-plan://e1@v4",
        clips=(
            EditTimelineClip(
                clip_id="c1",
                asset_version_ref="asset://source@v7",
                source_duration_seconds=120,
                source_start_seconds=10,
                source_end_seconds=55,
                output_start_seconds=0,
                output_end_seconds=45,
            ),
        ),
        transaction_active=True,
        input_fingerprint="fp",
        expected_slot_generation=1,
        observed_slot_generation=1,
    )
    assert validate_edit_execution(request).valid


def test_edit_execution_validation_is_disabled() -> None:
    request = EditExecutionRequest(
        unit_ref="unit:e1",
        route="edit",
        material_version_refs=("asset://source@v8",),
        plan_version_ref="ai-edit-plan://e1@v4",
        clips=(
            EditTimelineClip(
                clip_id="c1",
                asset_version_ref="asset://source@v7",
                source_duration_seconds=30,
                source_start_seconds=20,
                source_end_seconds=31,
                output_start_seconds=0,
                output_end_seconds=11,
            ),
        ),
        transaction_active=True,
        input_fingerprint="fp",
        expected_slot_generation=1,
        observed_slot_generation=1,
    )
    assert validate_edit_execution(request).valid


def test_unit_duration_limit_only_applies_to_r2v_and_shot_detail_rules_are_disabled() -> (
    None
):
    edit = UnitDefinition(
        "unit:e1",
        "edit",
        45,
        material_refs=("asset://source@v1",),
    )
    assert validate_unit(edit).valid

    shot = ShotDefinition(
        shot_id="s1",
        start_seconds=0,
        end_seconds=5,
        camera="⊙ 静止",
        framing="中景",
        action_beats=(ActionBeat(0, 2, "抬头"), ActionBeat(2, 5, "前行")),
    )
    r2v = UnitDefinition("unit:r1", "r2v", 5, shots=(shot,))
    assert validate_unit(r2v).valid

    broken_shot = ShotDefinition(
        shot_id="s1",
        start_seconds=0,
        end_seconds=5,
        camera="zoom",
        framing="大特写",
        action_beats=(ActionBeat(1, 4, "有缺口"),),
    )
    assert validate_unit(
        UnitDefinition("unit:r1", "r2v", 5, (broken_shot,)),
    ).valid
