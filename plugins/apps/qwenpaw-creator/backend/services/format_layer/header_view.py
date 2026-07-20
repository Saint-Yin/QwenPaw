# -*- coding: utf-8 -*-
"""Project Header View projection."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .errors import ProjectionInputError
from .inputs import ProjectPresentationMetadata, TextWorkspaceSnapshot
from .parsing import parse_reference_duration


def milliseconds_to_seconds(value: int) -> float:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProjectionInputError(
            "millisecond value must be a non-negative integer",
        )
    return float(Decimal(value) / Decimal(1000))


def seconds_to_milliseconds(value: int | float | str | Decimal) -> int:
    try:
        milliseconds = Decimal(str(value)) * Decimal(1000)
    except InvalidOperation as exc:
        raise ProjectionInputError("second value is invalid") from exc
    if milliseconds < 0 or milliseconds != milliseconds.to_integral_value():
        raise ProjectionInputError(
            "second value must have exact millisecond precision",
        )
    return int(milliseconds)


def _page_base(
    *,
    target_version: str,
    locator: Mapping[str, str],
    blockers: Sequence[str],
) -> dict[str, Any]:
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "resolvedRefs": [],
        "relations": [],
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": target_version,
        "uiLocator": dict(locator),
    }


def build_project_header_view(
    snapshot: TextWorkspaceSnapshot,
    metadata: ProjectPresentationMetadata,
) -> dict[str, Any]:
    blockers: list[str] = []
    view = _page_base(
        target_version=snapshot.target_version("project:header"),
        locator={"page": "project"},
        blockers=blockers,
    )
    view.update(
        {
            "id": snapshot.project_id,
            "name": snapshot.text("title.txt", required=True),
            "description": snapshot.text("description.md"),
            # Presentation-only mirror of the original user goal.  The
            # origin/main TopNav shows this as “原始脚本”; it is not a second
            # Workspace authority and is never writable through the View.
            "masterScript": snapshot.text("description.md"),
            "scenario": metadata.scenario,
            "aspectRatio": snapshot.text(
                "settings/aspect-ratio.txt",
                required=True,
            ),
            "resolution": snapshot.text(
                "settings/resolution.txt",
                required=True,
            ),
            "contentType": metadata.content_type,
            "platform": snapshot.text("settings/platform.txt"),
            "language": snapshot.text("settings/language.txt"),
            "targetDuration": parse_reference_duration(
                snapshot.text("settings/target-duration.txt"),
                label="project target duration",
            ),
        },
    )
    return view
