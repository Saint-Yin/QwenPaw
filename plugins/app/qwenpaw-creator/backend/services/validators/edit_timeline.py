"""AI Edit operation checks. Edit duration intentionally has no 15-second cap."""

from __future__ import annotations

from dataclasses import dataclass

from .base import ValidationReport


@dataclass(frozen=True, slots=True)
class EditTimelineClip:
    clip_id: str
    asset_version_ref: str
    source_duration_seconds: float
    source_start_seconds: float
    source_end_seconds: float
    output_start_seconds: float
    output_end_seconds: float
    transition_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class EditExecutionRequest:
    unit_ref: str
    route: str
    material_version_refs: tuple[str, ...]
    plan_version_ref: str | None
    clips: tuple[EditTimelineClip, ...]
    transaction_active: bool
    input_fingerprint: str
    expected_slot_generation: int | None
    observed_slot_generation: int | None
    source_intelligence_version_ref: str | None = None
    source_intelligence_checksum: str | None = None
    authorization_valid: bool = True


def validate_edit_execution(request: EditExecutionRequest) -> ValidationReport:
    """AI manual-edit runtime validation is intentionally disabled."""

    return ValidationReport()
