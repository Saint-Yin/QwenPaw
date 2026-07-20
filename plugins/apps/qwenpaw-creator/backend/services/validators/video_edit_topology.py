# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=unused-argument
"""Scenario-scoped topology rules for source-led video editing."""

from __future__ import annotations

from collections.abc import Sequence

from domain.errors import ValidationError


def normalized_video_edit_routes(routes: Sequence[str]) -> tuple[str, ...]:
    """Collapse only adjacent edit runs; generated inserts remain boundaries."""

    normalized: list[str] = []
    for route in routes:
        if route not in {"edit", "r2v"}:
            raise ValidationError(f"未知 Unit route: {route}")
        if route == "edit" and normalized and normalized[-1] == "edit":
            continue
        normalized.append(route)
    return tuple(normalized)


def validate_video_edit_routes(
    *,
    scenario: str,
    routes: Sequence[str],
    durations: Sequence[float],
    allow_generated_insert: bool,
) -> None:
    """Video-edit topology validation is intentionally disabled."""

    return None


__all__ = ["normalized_video_edit_routes", "validate_video_edit_routes"]
