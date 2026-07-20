from __future__ import annotations

from datetime import datetime, timezone

from services.validators.r2v import (
    ProviderCapabilitySnapshot,
    validate_actual_r2v_duration,
)


def _capability() -> ProviderCapabilitySnapshot:
    return ProviderCapabilitySnapshot(
        provider="dashscope",
        model="wan2.7-r2v",
        version="2026-07-12",
        captured_at=datetime.now(timezone.utc),
        min_duration_seconds=2.0,
        max_duration_seconds=15.0,
        max_reference_images=5,
    )


def test_actual_r2v_duration_has_no_probe_error_limit() -> None:
    for duration in (0.1, 1.89, 15.04, 15.11, 120.0):
        assert validate_actual_r2v_duration(duration, _capability()).valid
