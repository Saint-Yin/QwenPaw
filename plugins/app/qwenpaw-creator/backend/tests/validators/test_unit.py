"""Unit duration and route boundaries independent of provider adapters."""

import pytest

from services.validators.unit import (
    ActionBeat,
    ShotDefinition,
    UnitDefinition,
    validate_unit,
)
from services.validators.unit_segments import MAX_R2V_UNIT_DURATION_SECONDS


pytestmark = pytest.mark.unit


def _shot(*, end: float = 5) -> ShotDefinition:
    if end >= 10:
        step = end / 6
        beats = tuple(
            ActionBeat(index * step, (index + 1) * step, f"动作{index + 1}")
            for index in range(6)
        )
    else:
        beats = (
            ActionBeat(0, end / 2, "抬头"),
            ActionBeat(end / 2, end, "前行"),
        )
    return ShotDefinition(
        shot_id="shot-1",
        start_seconds=0,
        end_seconds=end,
        camera="⊙ 静止",
        framing="中景",
        action_beats=beats,
    )


def test_r2v_unit_accepts_fifteen_seconds_and_rejects_overflow() -> None:
    assert MAX_R2V_UNIT_DURATION_SECONDS == 15
    assert validate_unit(UnitDefinition("unit:r1", "r2v", 15, (_shot(end=15),))).valid

    report = validate_unit(UnitDefinition("unit:r1", "r2v", 15.1, (_shot(end=15.1),)))
    assert report.valid is False
    assert "R2V_DURATION_MAX" in {issue.code for issue in report.issues}


def test_edit_unit_can_exceed_fifteen_seconds() -> None:
    assert validate_unit(
        UnitDefinition(
            "unit:e1",
            "edit",
            45,
            material_refs=("asset://source@v1",),
        )
    ).valid


def test_edit_unit_structure_rules_are_disabled() -> None:
    report = validate_unit(
        UnitDefinition(
            "unit:e1",
            "edit",
            45,
            shots=(_shot(),),
            material_refs=("asset://source@v1",),
        )
    )
    assert report.valid


@pytest.mark.parametrize("route", ["t2v", "hybrid", "video", ""])
def test_removed_routes_are_rejected(route: str) -> None:
    report = validate_unit(UnitDefinition("unit:u1", route, 5, (_shot(),)))
    assert report.valid is False
    assert {issue.code for issue in report.issues} == {"UNIT_ROUTE"}
