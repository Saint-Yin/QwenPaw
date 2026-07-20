"""Scenario-scoped planning invariants for generated short dramas."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from services.format_layer.parsing import ParsedSection

from .base import ValidationIssue, ValidationReport


_PURE_SECONDS_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_EPSILON = 1e-6


def duration_tolerance(seconds: float) -> float:
    """Return the product-wide duration tolerance for a planned target."""

    return max(2.0, float(seconds) * 0.10)


def parse_canonical_target_duration(raw: str) -> float:
    """Parse canonical ``settings/target-duration.txt`` pure seconds.

    The general format-layer parser intentionally accepts a legacy ``s``
    suffix for reads.  New short-drama planning is stricter: the canonical
    settings leaf is one positive decimal number and nothing else.
    """

    text = raw.strip()
    if not _PURE_SECONDS_RE.fullmatch(text):
        raise ValueError("target-duration.txt 必须只包含纯秒数，例如 30")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - guarded by regex
        raise ValueError("target-duration.txt 秒数非法") from exc
    if value <= 0:
        raise ValueError("target-duration.txt 必须大于 0")
    return float(value)


def _mismatch(actual: float, expected: float) -> bool:
    return abs(float(actual) - float(expected)) > duration_tolerance(expected) + _EPSILON


def validate_short_drama_plan(
    *,
    scenario: str,
    target_duration_text: str,
    sections: Sequence[ParsedSection],
    require_units: bool = True,
) -> ValidationReport:
    """Validate short-drama duration topology without affecting other scenarios."""

    if scenario != "short_drama":
        return ValidationReport()

    # Project target duration is creative reference only. Missing, malformed,
    # or divergent values must never affect admission or terminal validation.
    del target_duration_text
    issues: list[ValidationIssue] = []

    if not sections:
        issues.append(
            ValidationIssue(
                "SHORT_DRAMA_SECTION_REQUIRED",
                "short_drama 必须至少包含一个 Section",
                "project:plan",
            )
        )
        return ValidationReport.from_iterable(issues)

    for section in sections:
        section_target = f"section:{section.id}"
        if section.duration_budget is None or section.duration_budget <= 0:
            issues.append(
                ValidationIssue(
                    "SHORT_DRAMA_SECTION_BUDGET_REQUIRED",
                    "每个 short_drama Section 必须有正数 duration-budget.txt",
                    section_target,
                )
            )
        if not require_units:
            continue
        if not section.units:
            issues.append(
                ValidationIssue(
                    "SHORT_DRAMA_SECTION_UNITS_REQUIRED",
                    "每个 short_drama Section 必须规划可生产的 Unit",
                    section_target,
                )
            )
            continue

        unit_total = sum(unit.duration for unit in section.units)
        if section.duration_budget is not None and _mismatch(
            unit_total, section.duration_budget
        ):
            issues.append(
                ValidationIssue(
                    "SHORT_DRAMA_SECTION_UNIT_DURATION_MISMATCH",
                    (
                        f"Section Unit 总时长 {unit_total:g}s 与预算 "
                        f"{section.duration_budget:g}s 超出容差 "
                        f"{duration_tolerance(section.duration_budget):g}s"
                    ),
                    section_target,
                )
            )

        for unit in section.units:
            unit_target = f"unit:{unit.id}"
            if unit.route == "r2v" and unit.duration > 15.0 + _EPSILON:
                issues.append(
                    ValidationIssue(
                        "SHORT_DRAMA_R2V_DURATION_EXCEEDS_15",
                        "short_drama 的每个 R2V Unit 必须不超过 15 秒",
                        unit_target,
                    )
                )
            shot_total = sum(shot.duration for shot in unit.shots)
            if unit.route == "r2v" and abs(shot_total - unit.duration) > _EPSILON:
                issues.append(
                    ValidationIssue(
                        "SHORT_DRAMA_SHOT_DURATION_MISMATCH",
                        (
                            f"Shot 总时长 {shot_total:g}s 必须精确等于 Unit "
                            f"时长 {unit.duration:g}s"
                        ),
                        unit_target,
                    )
                )

    return ValidationReport.from_iterable(issues)


__all__ = [
    "duration_tolerance",
    "parse_canonical_target_duration",
    "validate_short_drama_plan",
]
