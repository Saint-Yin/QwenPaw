# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-return-statements,too-many-statements
"""AI Edit Workbench View projection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .errors import ProjectionInputError, UnsupportedViewError
from .freshness import ai_edit_execute_fingerprint
from .inputs import (
    AiEditPlanVersion,
    ProjectPresentationMetadata,
    ProjectionCatalogs,
    ProviderConstraintSnapshot,
    RevisionSelections,
    TextWorkspaceSnapshot,
)
from .parsing import find_unit, parse_sections
from .plan_view import _unit_view
from .r2v_workbench_view import (
    _artifact_views,
    _production_refs,
    _selected_artifact,
    _selection_consistency_blockers,
    build_r2v_workbench_view,
)
from .ref_index_view import build_ref_index, resolve_many


def _parse_ai_edit_plan_ref(raw_ref: str) -> tuple[str, str]:
    parsed = urlparse(raw_ref)
    unit_id, separator, version_id = parsed.netloc.rpartition("@")
    if (
        parsed.scheme != "ai-edit-plan"
        or parsed.path not in {"", "/"}
        or not separator
    ):
        raise ProjectionInputError(f"invalid AI Edit Plan ref: {raw_ref!r}")
    return unquote(unit_id), unquote(version_id)


_EDIT_DERIVED_KEYS = frozenset(
    {
        "kind",
        "unit",
        "goal",
        "planVersion",
        "planRef",
        "videoVersions",
        "resolvedRefs",
        "relations",
        "readiness",
        "blockers",
        "targetVersion",
        "uiLocator",
        "previousUnitLastClipEnd",
        "nextUnitFirstClipStart",
    },
)


def build_edit_workbench_view(
    snapshot: TextWorkspaceSnapshot,
    unit_id: str,
    *,
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
    plan_versions: Iterable[AiEditPlanVersion],
    project_metadata: ProjectPresentationMetadata | None = None,
) -> dict[str, Any]:
    sections = parse_sections(snapshot)
    plan_versions = tuple(plan_versions)
    _, unit = find_unit(sections, unit_id)
    if unit.route != "edit":
        raise UnsupportedViewError(f"unit is not an edit unit: {unit_id}")
    index = build_ref_index(snapshot, catalogs)
    unit_view, blockers = _unit_view(snapshot, unit, number=1, index=index)
    root = f"{unit.root}/production/edit"
    raw_plan_ref = snapshot.text(f"{root}/plan.ref")
    selected_plan: AiEditPlanVersion | None = None
    payload: dict[str, Any] = {
        "unit_id": unit.id,
        "plan": None,
        "storyboard_image_url": None,
        "material_assets": [],
        "workflow_trace": [],
    }
    if raw_plan_ref:
        plan_unit_id, plan_version_id = _parse_ai_edit_plan_ref(raw_plan_ref)
        if plan_unit_id != unit.id:
            blockers.append("AI_EDIT_PLAN_UNIT_MISMATCH")
        selected_plan = next(
            (item for item in plan_versions if item.id == plan_version_id),
            None,
        )
        if selected_plan is None:
            blockers.append(
                f"AI_EDIT_PLAN_VERSION_NOT_FOUND:{plan_version_id}",
            )
        elif (
            selected_plan.unit_id != unit.id
            or selected_plan.source_ref != raw_plan_ref
        ):
            blockers.append("AI_EDIT_PLAN_REFERENCE_MISMATCH")
        else:
            payload = deepcopy(dict(selected_plan.workbench_envelope))
            collisions = sorted(_EDIT_DERIVED_KEYS.intersection(payload))
            if collisions:
                raise ProjectionInputError(
                    f"AI Edit envelope uses reserved projection keys: {collisions}",
                )
    else:
        blockers.append("AI_EDIT_PLAN_VERSION_REQUIRED")

    source_refs = _production_refs(snapshot, f"{root}/source-refs/")
    resolved, ref_blockers = resolve_many(index, source_refs)
    blockers.extend(ref_blockers)
    owner_ref = f"unit:{unit.id}"
    video, _, video_blockers = _selected_artifact(
        catalogs,
        selections,
        owner_ref=owner_ref,
        kind="unit_video",
    )
    blockers.extend(video_blockers)
    rendered_ref = snapshot.text(f"{root}/rendered-video.ref")
    blockers.extend(
        _selection_consistency_blockers(
            rendered_ref,
            video,
            label="EDIT_VIDEO",
        ),
    )
    if (
        selected_plan is not None
        and video is not None
        and str(video.input_fingerprint or "").startswith("sha256:")
    ):
        expected_fingerprint = ai_edit_execute_fingerprint(
            snapshot,
            catalogs,
            unit_id=unit.id,
            plan=dict(selected_plan.workbench_envelope.get("plan") or {}),
            project_metadata=project_metadata,
        )
        if video.input_fingerprint != expected_fingerprint:
            blockers.append("EDIT_VIDEO_INPUT_FINGERPRINT_STALE")
    unique_blockers = list(dict.fromkeys(blockers))
    payload.update(
        {
            "kind": "edit",
            "unit": unit_view,
            "goal": snapshot.text(f"{root}/intent.md"),
            "planVersion": (
                {
                    "id": selected_plan.id,
                    "checksum": selected_plan.checksum,
                    "createdAt": selected_plan.created_at,
                }
                if selected_plan
                else None
            ),
            "planRef": raw_plan_ref or None,
            "videoVersions": _artifact_views(
                catalogs,
                selections,
                owner_ref=owner_ref,
                kind="unit_video",
            ),
            "resolvedRefs": resolved,
            "relations": [
                {
                    "from": f"project://unit/{unit.id}",
                    "to": ref,
                    "kind": "uses_version",
                }
                for ref in source_refs
            ],
            "readiness": {"ready": not unique_blockers},
            "blockers": unique_blockers,
            "targetVersion": snapshot.target_version(f"unit:{unit.id}"),
            "uiLocator": {
                "page": "workbench",
                "unitId": unit.id,
                "route": "edit",
            },
            "previousUnitLastClipEnd": None,
            "nextUnitFirstClipStart": None,
        },
    )

    # origin/main constrained the first/last clip with the adjacent Unit's
    # selected edit plan, including across Section boundaries. Project those
    # two read-only bounds so the refactored browser keeps the same inputs and
    # validation without reconstructing the Project aggregate.
    ordered_units = [
        candidate for section in sections for candidate in section.units
    ]
    unit_index = next(
        index
        for index, candidate in enumerate(ordered_units)
        if candidate.id == unit.id
    )

    def adjacent_boundary(candidate: Any, *, first: bool) -> float | None:
        if candidate is None or candidate.route != "edit":
            return None
        adjacent_ref = snapshot.text(
            f"{candidate.root}/production/edit/plan.ref",
        )
        if not adjacent_ref:
            return None
        try:
            adjacent_unit_id, adjacent_version_id = _parse_ai_edit_plan_ref(
                adjacent_ref,
            )
        except ProjectionInputError:
            return None
        adjacent = next(
            (
                version
                for version in plan_versions
                if version.id == adjacent_version_id
                and version.unit_id == adjacent_unit_id
            ),
            None,
        )
        if adjacent is None:
            return None
        adjacent_plan = adjacent.workbench_envelope.get("plan")
        if not isinstance(adjacent_plan, dict):
            return None
        timeline = adjacent_plan.get("timeline", [])
        if not isinstance(timeline, list) or not timeline:
            return None
        clip = timeline[0] if first else timeline[-1]
        if not isinstance(clip, dict):
            return None
        value = clip.get("start" if first else "end")
        return float(value) if isinstance(value, (int, float)) else None

    previous = ordered_units[unit_index - 1] if unit_index > 0 else None
    following = (
        ordered_units[unit_index + 1]
        if unit_index + 1 < len(ordered_units)
        else None
    )
    payload["previousUnitLastClipEnd"] = adjacent_boundary(
        previous,
        first=False,
    )
    payload["nextUnitFirstClipStart"] = adjacent_boundary(
        following,
        first=True,
    )
    return payload


def build_workbench_view(
    snapshot: TextWorkspaceSnapshot,
    unit_id: str,
    *,
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
    provider: ProviderConstraintSnapshot | None = None,
    plan_versions: Iterable[AiEditPlanVersion] = (),
    project_metadata: ProjectPresentationMetadata | None = None,
) -> dict[str, Any]:
    _, unit = find_unit(parse_sections(snapshot), unit_id)
    if unit.route == "r2v":
        if provider is None:
            raise ProjectionInputError(
                "r2v projection requires a provider capability snapshot",
            )
        return build_r2v_workbench_view(
            snapshot,
            unit_id,
            catalogs=catalogs,
            selections=selections,
            provider=provider,
        )
    return build_edit_workbench_view(
        snapshot,
        unit_id,
        catalogs=catalogs,
        selections=selections,
        plan_versions=plan_versions,
        project_metadata=project_metadata,
    )
