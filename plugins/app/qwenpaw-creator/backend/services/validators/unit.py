from __future__ import annotations

from dataclasses import dataclass

from domain.enums import UnitTaskType

from .base import ValidationIssue, ValidationReport
from .unit_segments import MAX_R2V_UNIT_DURATION_SECONDS


@dataclass(frozen=True, slots=True)
class ActionBeat:
    start_seconds: float
    end_seconds: float
    description: str


@dataclass(frozen=True, slots=True)
class ShotDefinition:
    shot_id: str
    start_seconds: float
    end_seconds: float
    camera: str
    framing: str
    action_beats: tuple[ActionBeat, ...]
    dialogue: str = ""


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    unit_ref: str
    route: str
    duration_seconds: float
    shots: tuple[ShotDefinition, ...] = ()
    material_refs: tuple[str, ...] = ()


def validate_unit(unit: UnitDefinition) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if unit.route not in {UnitTaskType.R2V.value, UnitTaskType.EDIT.value}:
        return ValidationReport(
            (
                ValidationIssue(
                    "UNIT_ROUTE", "Unit route 只能是 r2v 或 edit", unit.unit_ref
                ),
            )
        )
    if unit.duration_seconds <= 0:
        issues.append(
            ValidationIssue("UNIT_DURATION", "Unit 时长必须大于 0", unit.unit_ref)
        )
    if unit.route == UnitTaskType.EDIT.value:
        return ValidationReport.from_iterable(issues)
    if unit.duration_seconds > MAX_R2V_UNIT_DURATION_SECONDS:
        issues.append(
            ValidationIssue(
                "R2V_DURATION_MAX", "R2V Unit 总时长不能超过 15 秒", unit.unit_ref
            )
        )
    if not unit.shots:
        issues.append(
            ValidationIssue(
                "R2V_SHOTS_REQUIRED", "R2V Unit 必须包含生产级 Shot", unit.unit_ref
            )
        )
        return ValidationReport.from_iterable(issues)
    return ValidationReport.from_iterable(issues)
