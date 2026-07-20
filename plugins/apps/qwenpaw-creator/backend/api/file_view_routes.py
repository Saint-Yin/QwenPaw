# -*- coding: utf-8 -*-
"""Read-only Creator Views projected directly from ``project.json``.

The compatibility DTOs in this module keep the existing browser contracts
while making the Project Pydantic aggregate and its file Runtime the only
authorities.  A View is always rebuilt on read; it is never persisted as a
second copy of Project data.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from domain.errors import NotFoundError, ValidationError
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    Composition,
    EditProduction,
    Project,
    R2VProduction,
    Section,
    Unit,
)
from services.project_files.store import (
    ProjectNotFound,
    ProjectSnapshot,
    ProjectStoreError,
)
from services.runtime_files.models import CreatorSessionRecord, ReviewRecord
from services.runtime_files.execution_models import TaskRecord
from services.runtime_files.execution_store import (
    ExecutionStoreError,
    ProjectExecutionStore,
)
from services.runtime_files.session_store import (
    RuntimeSessionNotFound,
    SessionStoreError,
)
from services.runtime_files.status_projection import build_agent_status_bar

from .dependencies import CreatorErrorRoute, project_file_services


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["file-project-views"],
    route_class=CreatorErrorRoute,
)


_UI_PHASES = {
    "IDLE": "idle",
    "RUNNING": "executing",
    "WAITING_RUNTIME": "executing",
    "INTERRUPT_REQUESTED": "interrupting",
    "WAITING_USER_INPUT": "waiting_input",
    "WAITING_EXECUTION_AUTH": "waiting_authorization",
    "PENDING_REVIEW": "waiting_review",
    "RESUMING": "resuming",
    "CANCELLED": "cancelled",
    "ERROR": "error",
}


@dataclass(frozen=True, slots=True)
class _ViewContext:
    snapshot: ProjectSnapshot
    session: CreatorSessionRecord | None
    review: ReviewRecord | None
    tasks: tuple[TaskRecord, ...]
    agent_status_bar: dict[str, Any]


def _target(context: _ViewContext, ref: str) -> str:
    """Opaque browser CAS token derived from the actual Project snapshot."""

    return (
        f"project:{context.snapshot.etag}:g{context.snapshot.generation}:{ref}"
    )


def _asset_ref(logical_asset_id: str, version_id: str) -> str:
    return f"asset://{logical_asset_id}@{version_id}"


def _artifact_ref(slot_id: str, version_id: str) -> str:
    return f"artifact://{slot_id}@{version_id}"


def _asset_url(version_id: str) -> str:
    return f"/media/assets/{quote(version_id, safe='')}"


def _artifact_url(version_id: str) -> str:
    return f"/media/artifacts/{quote(version_id, safe='')}"


def _artifact_media_type(kind: str) -> str:
    normalized = kind.casefold()
    if "video" in normalized:
        return "video"
    if "image" in normalized or "storyboard" in normalized:
        return "image"
    if "audio" in normalized:
        return "audio"
    return "other"


def _task_error_message(task: TaskRecord) -> str | None:
    error = task.error
    if not error:
        return None
    message = error.get("message")
    return str(message) if message else str(error.get("code") or "Asset 入库失败")


def _asset_ingest_items(context: _ViewContext) -> list[dict[str, Any]]:
    project = context.snapshot.project
    result: list[dict[str, Any]] = []
    for task in context.tasks:
        if task.kind.value != "asset_ingest":
            continue
        asset_id = str(task.metadata.get("assetId") or "") or None
        version_id = str(task.metadata.get("assetVersionId") or "") or None
        version = (
            project.assets.source_versions_by_id.get(version_id)
            if version_id is not None
            else None
        )
        result.append(
            {
                "taskId": task.task_id,
                "assetId": asset_id,
                "assetVersionId": version_id,
                "name": str(
                    task.metadata.get("requestedName")
                    or (version.name if version is not None else "Asset"),
                ),
                "status": task.status.value,
                "progress": task.progress,
                "error": _task_error_message(task),
            },
        )
    return result


def _artifact_locator(owner_ref: str, version_id: str) -> dict[str, str]:
    kind, separator, identifier = owner_ref.partition(":")
    if separator and kind == "unit":
        return {
            "page": "workbench",
            "unitId": identifier,
            "versionId": version_id,
        }
    if separator and kind == "section":
        return {
            "page": "section-compose",
            "sectionId": identifier,
            "versionId": version_id,
        }
    return {"page": "final-compose", "versionId": version_id}


def _owner_ref(owner_ref: str) -> str:
    kind, separator, identifier = owner_ref.partition(":")
    if separator and kind in {"unit", "section"} and identifier:
        return f"project://{kind}/{identifier}"
    return owner_ref


def _source_ref_view(
    project: Project,
    version_id: str,
) -> dict[str, Any] | None:
    version = project.assets.source_versions_by_id.get(version_id)
    if version is None:
        return None
    return {
        "ref": _asset_ref(version.logical_asset_id, version.version_id),
        "name": version.name,
        "type": "asset",
        "version": version.version_id,
        "thumbnailUrl": (
            _asset_url(version.version_id)
            if version.thumbnail_file_id is not None
            else None
        ),
        "url": _asset_url(version.version_id),
        "mediaType": version.media_kind,
        "checksum": version.checksum,
        "logicalAssetId": version.logical_asset_id,
        "assetVersionId": version.version_id,
        "createdAt": version.created_at.isoformat(),
        "uiLocator": {
            "page": "assets",
            "assetId": version.logical_asset_id,
            "versionId": version.version_id,
        },
    }


def _artifact_ref_view(
    project: Project,
    version_id: str,
) -> dict[str, Any] | None:
    version = project.assets.artifact_versions_by_id.get(version_id)
    if version is None:
        return None
    return {
        "ref": _artifact_ref(version.slot_id, version.version_id),
        "name": version.name,
        "type": "artifact",
        "version": version.version_id,
        "thumbnailUrl": (
            _artifact_url(version.version_id)
            if version.thumbnail_file_id is not None
            else None
        ),
        "url": _artifact_url(version.version_id),
        "mediaType": version.kind,
        "checksum": version.checksum,
        "slotId": version.slot_id,
        "artifactVersionId": version.version_id,
        "createdAt": version.created_at.isoformat(),
        "freshnessStatus": "stale" if version.stale else "current",
        "staleReason": version.stale_reason,
        "uiLocator": _artifact_locator(version.owner_ref, version.version_id),
    }


def _visual_ref_view(
    project: Project,
    entity_id: str,
) -> dict[str, Any] | None:
    entity = project.visual.entities.items.get(entity_id)
    if entity is None:
        return None
    selected = (
        _artifact_ref_view(project, entity.selected_artifact_version_id)
        if entity.selected_artifact_version_id is not None
        else None
    )
    return {
        "ref": f"project://asset/{entity.entity_id}",
        "name": entity.name,
        "type": "asset",
        "version": selected.get("version") if selected else None,
        "thumbnailUrl": selected.get("thumbnailUrl") if selected else None,
        "url": selected.get("url") if selected else None,
        "mediaType": "image",
        "artifactVersionId": (
            selected.get("artifactVersionId") if selected else None
        ),
        "uiLocator": {"page": "assets", "assetId": entity.entity_id},
    }


def _selected_source_ref(
    project: Project,
    source_id: str,
) -> dict[str, Any] | None:
    source = project.sources.sources.items.get(source_id)
    if source is None:
        return None
    return _source_ref_view(project, source.selected_asset_version_id)


def _resolve_exact_version(
    project: Project,
    version_id: str,
) -> dict[str, Any] | None:
    return _source_ref_view(project, version_id) or _artifact_ref_view(
        project,
        version_id,
    )


def _unique_refs(items: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if item is not None:
            result[str(item["ref"])] = item
    return list(result.values())


def _unit_view(
    context: _ViewContext,
    unit: Unit,
    *,
    number: int,
) -> dict[str, Any]:
    project = context.snapshot.project
    resolved: list[dict[str, Any] | None] = []
    blockers: list[str] = []
    visual_ids = [*unit.character_refs, *unit.prop_refs]
    if unit.scene_ref is not None:
        visual_ids.append(unit.scene_ref)
    for entity_id in visual_ids:
        item = _visual_ref_view(project, entity_id)
        resolved.append(item)
        entity = project.visual.entities.items.get(entity_id)
        if entity is not None and entity.selected_artifact_version_id is None:
            blockers.append(f"VISUAL_REFERENCE_NOT_SELECTED:{entity_id}")

    material_refs: list[str] = []
    for source_id in unit.source_refs:
        item = _selected_source_ref(project, source_id)
        resolved.append(item)
        if item is not None:
            material_refs.append(str(item["ref"]))

    if unit.duration_seconds <= 0:
        blockers.append("UNIT_DURATION_MUST_BE_POSITIVE")
    if unit.route.value == "r2v" and unit.duration_seconds > 15:
        blockers.append("R2V_DURATION_EXCEEDS_15_SECONDS")

    production = project.production.units_by_id.get(unit.unit_id)
    storyboard_prompt = ""
    storyboard_image_url: str | None = None
    storyboard_image_version_id: str | None = None
    video_prompt = ""
    video_url: str | None = None
    if isinstance(production, R2VProduction):
        storyboard_prompt = production.storyboard_prompt
        video_prompt = production.video_prompt
        storyboard_image_version_id = (
            production.selected_storyboard_artifact_version_id
        )
        if storyboard_image_version_id is not None:
            storyboard_image_url = _artifact_url(storyboard_image_version_id)
        if production.selected_video_artifact_version_id is not None:
            video_url = _artifact_url(
                production.selected_video_artifact_version_id,
            )
    elif isinstance(production, EditProduction):
        if production.rendered_video_artifact_version_id is not None:
            video_url = _artifact_url(
                production.rendered_video_artifact_version_id,
            )

    unique_blockers = list(dict.fromkeys(blockers))
    target = _target(context, f"unit:{unit.unit_id}")
    relations = [
        {
            "from": f"project://unit/{unit.unit_id}",
            "to": str(item["ref"]),
            "kind": "references",
        }
        for item in _unique_refs(resolved)
    ]
    return {
        "id": unit.unit_id,
        "number": number,
        "title": unit.title,
        "taskType": unit.route.value,
        "duration": unit.duration_seconds,
        "storyboardPrompt": storyboard_prompt,
        "storyboardImageUrl": storyboard_image_url,
        "storyboardImageVersionId": storyboard_image_version_id,
        "videoPrompt": video_prompt,
        "videoUrl": video_url,
        "shots": [
            {
                "id": shot.shot_id,
                "number": shot_number,
                "description": shot.description,
                "camera": shot.camera.value if shot.camera else "⊙ 静止",
                "framing": shot.framing.value if shot.framing else "中景",
                "cameraDescription": shot.camera_description,
                "dialogue": shot.dialogue,
                "duration": shot.duration_seconds,
                "targetVersion": _target(context, f"shot:{shot.shot_id}"),
            }
            for shot_number, shot_id in enumerate(unit.shots.order, 1)
            if (shot := unit.shots.items.get(shot_id)) is not None
        ],
        "sceneRef": (
            f"project://asset/{unit.scene_ref}" if unit.scene_ref else None
        ),
        "characterRefs": [
            f"project://asset/{identifier}"
            for identifier in unit.character_refs
        ],
        "propRefs": [
            f"project://asset/{identifier}" for identifier in unit.prop_refs
        ],
        "materialRefs": material_refs,
        "resolvedRefs": _unique_refs(resolved),
        "relations": relations,
        "readiness": {
            "ready": not unique_blockers,
            "blockers": unique_blockers,
        },
        "blockers": unique_blockers,
        "targetVersion": target,
        "uiLocator": {"page": "workbench", "unitId": unit.unit_id},
    }


def _section_view(
    context: _ViewContext,
    section: Section,
    *,
    number: int,
) -> dict[str, Any]:
    units = [
        _unit_view(context, section.units.items[unit_id], number=unit_number)
        for unit_number, unit_id in enumerate(section.units.order, 1)
    ]
    blockers = list(
        dict.fromkeys(
            blocker for unit in units for blocker in unit.get("blockers", [])
        ),
    )
    resolved = _unique_refs(
        [item for unit in units for item in unit.get("resolvedRefs", [])],
    )
    relations = [
        {
            "from": f"project://section/{section.section_id}",
            "to": f"project://unit/{unit['id']}",
            "kind": "contains",
        }
        for unit in units
    ]
    relations.extend(
        relation for unit in units for relation in unit.get("relations", [])
    )
    target_versions = {
        f"unit:{unit['id']}": str(unit["targetVersion"]) for unit in units
    }
    return {
        "id": section.section_id,
        "number": number,
        "title": section.title,
        "narrative": section.narrative,
        "durationBudget": section.duration_budget_seconds,
        "constraints": list(section.constraints),
        "script": section.script,
        "units": units,
        "resolvedRefs": resolved,
        "relations": relations,
        "targetVersions": target_versions,
        "targetVersion": _target(context, f"section:{section.section_id}"),
        "readiness": {"ready": not blockers, "blockers": blockers},
        "blockers": blockers,
        "uiLocator": {"page": "plan", "sectionId": section.section_id},
    }


def _plan_view(context: _ViewContext) -> dict[str, Any]:
    project = context.snapshot.project
    sections = [
        _section_view(
            context,
            project.story.sections.items[section_id],
            number=section_number,
        )
        for section_number, section_id in enumerate(
            project.story.sections.order,
            1,
        )
    ]
    blockers = list(
        dict.fromkeys(
            blocker
            for section in sections
            for blocker in section.get("blockers", [])
        ),
    )
    return {
        "title": project.story.title or project.name,
        "outline": project.story.outline,
        "aspectRatio": project.settings.aspect_ratio,
        "targetDuration": project.settings.target_duration_seconds,
        "sections": sections,
        "relations": [
            relation
            for section in sections
            for relation in section.get("relations", [])
        ],
        "resolvedRefs": _unique_refs(
            [
                item
                for section in sections
                for item in section.get("resolvedRefs", [])
            ],
        ),
        "readiness": {"ready": not blockers},
        "blockers": blockers,
        "targetVersion": _target(context, "project:plan"),
        "uiLocator": {"page": "plan"},
    }


def _artifact_view(
    context: _ViewContext,
    version_id: str,
    *,
    selected: bool,
) -> dict[str, Any]:
    version = context.snapshot.project.assets.artifact_versions_by_id[
        version_id
    ]
    result: dict[str, Any] = {
        "id": version.version_id,
        "name": version.name,
        "slotId": version.slot_id,
        "kind": version.kind,
        "url": _artifact_url(version.version_id),
        "checksum": version.checksum,
        "createdAt": version.created_at.isoformat(),
        "provenanceRefs": list(version.provenance_refs),
        "selected": selected,
        "freshnessStatus": "stale" if version.stale else "current",
        "staleReason": version.stale_reason,
        "artifactVersionId": version.version_id,
        "sourceRef": _artifact_ref(version.slot_id, version.version_id),
        "basedOnRevisionId": f"generation:{version.based_on_generation}",
        "ownerRef": _owner_ref(version.owner_ref),
        "uiLocator": _artifact_locator(version.owner_ref, version.version_id),
    }
    if version.duration_seconds is not None:
        result["durationSeconds"] = version.duration_seconds
    if version.input_fingerprint is not None:
        result["inputFingerprint"] = version.input_fingerprint
    return result


def _artifacts(
    context: _ViewContext,
    *,
    owner_ref: str | None = None,
    kinds: set[str] | None = None,
    selected_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    project = context.snapshot.project
    selected_ids = selected_ids or set()
    records = [
        version
        for version in project.assets.artifact_versions_by_id.values()
        if (owner_ref is None or version.owner_ref == owner_ref)
        and (kinds is None or version.kind in kinds)
    ]
    records.sort(key=lambda item: (item.created_at, item.version_id))
    return [
        _artifact_view(
            context,
            version.version_id,
            selected=(
                version.version_id in selected_ids
                or project.assets.artifact_slots_by_id[
                    version.slot_id
                ].selected_version_id
                == version.version_id
            ),
        )
        for version in records
    ]


def _find_unit(project: Project, unit_id: str) -> tuple[Section, Unit, int]:
    for section_id in project.story.sections.order:
        section = project.story.sections.items[section_id]
        if unit_id in section.units.items:
            return (
                section,
                section.units.items[unit_id],
                section.units.order.index(unit_id) + 1,
            )
    raise NotFoundError("Unit 不存在")


def _reference_binding(project: Project, version_id: str) -> str:
    if version_id in project.assets.source_versions_by_id:
        return "sources"
    for entity in project.visual.entities.items.values():
        if entity.selected_artifact_version_id != version_id:
            continue
        return {
            "scene": "scene",
            "character": "characters",
            "prop": "props",
        }[entity.kind]
    return "sources"


def _r2v_workbench(
    context: _ViewContext,
    unit: Unit,
    *,
    number: int,
    production: R2VProduction | None,
) -> dict[str, Any]:
    project = context.snapshot.project
    production = production or R2VProduction()
    owner_ref = f"unit:{unit.unit_id}"
    storyboard_id = production.selected_storyboard_artifact_version_id
    video_id = production.selected_video_artifact_version_id
    selected_ids = {
        item for item in (storyboard_id, video_id) if item is not None
    }
    reference_sets: dict[tuple[str, str], set[str]] = {}
    for label, version_ids in (
        ("storyboard", production.storyboard_reference_version_ids),
        ("video", production.video_reference_version_ids),
    ):
        for version_id in version_ids:
            resolved = _resolve_exact_version(project, version_id)
            if resolved is None:
                continue
            key = (
                _reference_binding(project, version_id),
                str(resolved["ref"]),
            )
            reference_sets.setdefault(key, set()).add(label)
    all_reference_ids = [
        *production.storyboard_reference_version_ids,
        *production.video_reference_version_ids,
    ]
    resolved = _unique_refs(
        [
            _resolve_exact_version(project, version_id)
            for version_id in all_reference_ids
        ],
    )
    blockers: list[str] = []
    if storyboard_id is None:
        blockers.append("STORYBOARD_VERSION_REQUIRED")
    if unit.duration_seconds > 15:
        blockers.append("R2V_DURATION_OUTSIDE_PROVIDER_BOUNDS")

    recipe = production.recipe
    preauthorized = project.settings.execution_preauthorization
    provider_scope = (
        preauthorized.provider_models[0]
        if preauthorized and preauthorized.provider_models
        else None
    )
    provider = (
        recipe.provider
        if recipe
        else (provider_scope.provider if provider_scope else "unconfigured")
    )
    model = (
        recipe.model
        if recipe
        else (provider_scope.model if provider_scope else "unconfigured")
    )
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "kind": "r2v",
        "unit": _unit_view(context, unit, number=number),
        "storyboardPrompt": production.storyboard_prompt,
        "videoPrompt": production.video_prompt,
        "storyboardVersions": _artifacts(
            context,
            owner_ref=owner_ref,
            kinds={"r2v_storyboard_image", "storyboard_image"},
            selected_ids=selected_ids,
        ),
        "videoVersions": _artifacts(
            context,
            owner_ref=owner_ref,
            kinds={"unit_video"},
            selected_ids=selected_ids,
        ),
        "selectedStoryboardVersionId": storyboard_id,
        "selectedVideoVersionId": video_id,
        "storyboardInputRefs": [
            str(item["ref"])
            for version_id in production.storyboard_reference_version_ids
            if (item := _resolve_exact_version(project, version_id))
            is not None
        ],
        "videoInputRefs": [
            str(item["ref"])
            for version_id in production.video_reference_version_ids
            if (item := _resolve_exact_version(project, version_id))
            is not None
        ],
        "inputReferenceBindings": [
            {
                "sourceRef": source_ref,
                "field": field,
                "referenceSets": sorted(labels),
            }
            for (field, source_ref), labels in sorted(reference_sets.items())
        ],
        "providerConstraints": {
            "provider": provider,
            "minDuration": 0,
            "maxDuration": 15,
            "maxReferenceImages": 8,
            "model": model,
            "version": f"project-schema-{project.schema_version}",
            "capturedAt": project.updated_at.isoformat(),
            "allowedDurations": [],
        },
        "continuity": unit.continuity,
        "resolvedRefs": resolved,
        "relations": [
            {
                "from": f"project://unit/{unit.unit_id}",
                "to": str(item["ref"]),
                "kind": "references",
            }
            for item in resolved
        ],
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": _target(context, f"unit:{unit.unit_id}"),
        "uiLocator": {
            "page": "workbench",
            "unitId": unit.unit_id,
            "route": "r2v",
        },
        "selectionSource": {
            "revisionId": context.snapshot.etag,
            "storyboardSlotId": (
                project.assets.artifact_versions_by_id[storyboard_id].slot_id
                if storyboard_id is not None
                else None
            ),
        },
    }


def _edit_plan_view(
    project: Project,
    production: EditProduction,
) -> dict[str, Any] | None:
    plan = production.plan
    if plan is None:
        return None
    timeline: list[dict[str, Any]] = []
    for order, clip_id in enumerate(plan.timeline.order, 1):
        clip = plan.timeline.items[clip_id]
        source = project.assets.source_versions_by_id[
            clip.source_asset_version_id
        ]
        timeline.append(
            {
                "clip_id": clip.clip_id,
                "asset_id": source.logical_asset_id,
                "asset_name": source.name,
                "source_url": _asset_url(source.version_id),
                "asset_version_id": source.version_id,
                "start": clip.source_in_seconds,
                "end": clip.source_out_seconds,
                "duration": clip.source_out_seconds - clip.source_in_seconds,
                "order": order,
                "transition": clip.transition,
                "reason": clip.reason,
                **(
                    {"overlay_copy": dict(clip.overlay)}
                    if clip.overlay
                    else {}
                ),
            },
        )
    storyboard: list[dict[str, Any]] = []
    timeline_positions = {
        item["clip_id"]: (item["start"], item["end"]) for item in timeline
    }
    for order, panel_id in enumerate(plan.storyboard.order, 1):
        panel = plan.storyboard.items[panel_id]
        clip = plan.timeline.items[panel.clip_id]
        source = project.assets.source_versions_by_id[
            clip.source_asset_version_id
        ]
        start, end = timeline_positions[panel.clip_id]
        item: dict[str, Any] = {
            "panel_id": panel.panel_id,
            "clip_id": panel.clip_id,
            "order": order,
            "title": panel.title,
            "description": panel.description,
            "source_asset_id": source.logical_asset_id,
            "timestamp": panel.source_timestamp_seconds,
            "timeline_start": start,
            "timeline_end": end,
        }
        if panel.frame_artifact_version_id is not None:
            item["image_url"] = _artifact_url(panel.frame_artifact_version_id)
        storyboard.append(item)
    return {
        "summary": plan.summary,
        "target_duration": plan.target_duration_seconds,
        "timeline": timeline,
        "storyboard": storyboard,
        "audio_plan": plan.audio_plan.model_dump(mode="json"),
        "model": dict(plan.model),
    }


def _adjacent_edit_boundary(
    project: Project,
    ordered_units: list[Unit],
    index: int,
    *,
    previous: bool,
) -> float | None:
    adjacent_index = index - 1 if previous else index + 1
    if adjacent_index < 0 or adjacent_index >= len(ordered_units):
        return None
    production = project.production.units_by_id.get(
        ordered_units[adjacent_index].unit_id,
    )
    if not isinstance(production, EditProduction) or production.plan is None:
        return None
    order = production.plan.timeline.order
    if not order:
        return None
    clip = production.plan.timeline.items[order[-1 if previous else 0]]
    return clip.source_out_seconds if previous else clip.source_in_seconds


def _edit_workbench(
    context: _ViewContext,
    unit: Unit,
    *,
    number: int,
    production: EditProduction | None,
) -> dict[str, Any]:
    project = context.snapshot.project
    production = production or EditProduction()
    plan = _edit_plan_view(project, production)
    selected_ids = {
        item
        for item in (
            production.storyboard_sheet_artifact_version_id,
            production.rendered_video_artifact_version_id,
        )
        if item is not None
    }
    material_assets = []
    for version_id in production.source_asset_version_ids:
        version = project.assets.source_versions_by_id[version_id]
        material_assets.append(
            {
                "id": version.version_id,
                "name": version.name,
                "url": _asset_url(version.version_id),
                "duration": version.duration_seconds,
            },
        )
    ordered_units = [
        project.story.sections.items[section_id].units.items[unit_id]
        for section_id in project.story.sections.order
        for unit_id in project.story.sections.items[section_id].units.order
    ]
    unit_index = next(
        index
        for index, candidate in enumerate(ordered_units)
        if candidate.unit_id == unit.unit_id
    )
    blockers = [] if plan is not None else ["AI_EDIT_PLAN_REQUIRED"]
    plan_record = production.plan
    return {
        "kind": "edit",
        "unit": _unit_view(context, unit, number=number),
        "goal": production.intent,
        "plan": plan,
        "storyboard_image_url": (
            _artifact_url(production.storyboard_sheet_artifact_version_id)
            if production.storyboard_sheet_artifact_version_id is not None
            else None
        ),
        "material_assets": material_assets,
        "workflow_trace": [],
        "videoVersions": _artifacts(
            context,
            owner_ref=f"unit:{unit.unit_id}",
            kinds={"unit_video"},
            selected_ids=selected_ids,
        ),
        "planVersion": (
            {
                "id": plan_record.plan_id,
                "checksum": plan_record.plan_hash,
                "createdAt": project.updated_at.isoformat(),
            }
            if plan_record is not None
            else None
        ),
        "planRef": (
            f"project://unit/{unit.unit_id}/edit-plan/{plan_record.plan_id}"
            if plan_record is not None
            else None
        ),
        "resolvedRefs": _unique_refs(
            [
                _source_ref_view(project, version_id)
                for version_id in production.source_asset_version_ids
            ],
        ),
        "relations": [
            {
                "from": f"project://unit/{unit.unit_id}",
                "to": _asset_ref(
                    project.assets.source_versions_by_id[
                        version_id
                    ].logical_asset_id,
                    version_id,
                ),
                "kind": "uses_version",
            }
            for version_id in production.source_asset_version_ids
        ],
        "readiness": {"ready": not blockers, "blockers": blockers},
        "blockers": blockers,
        "targetVersion": _target(context, f"unit:{unit.unit_id}"),
        "uiLocator": {
            "page": "workbench",
            "unitId": unit.unit_id,
            "route": "edit",
        },
        "previousUnitLastClipEnd": _adjacent_edit_boundary(
            project,
            ordered_units,
            unit_index,
            previous=True,
        ),
        "nextUnitFirstClipStart": _adjacent_edit_boundary(
            project,
            ordered_units,
            unit_index,
            previous=False,
        ),
    }


def _workbench_view(context: _ViewContext, unit_id: str) -> dict[str, Any]:
    project = context.snapshot.project
    _section, unit, number = _find_unit(project, unit_id)
    production = project.production.units_by_id.get(unit_id)
    if unit.route.value == "r2v":
        return _r2v_workbench(
            context,
            unit,
            number=number,
            production=production
            if isinstance(production, R2VProduction)
            else None,
        )
    return _edit_workbench(
        context,
        unit,
        number=number,
        production=production
        if isinstance(production, EditProduction)
        else None,
    )


def _count_occurrences(value: Any, needle: str) -> int:
    if isinstance(value, dict):
        return sum(_count_occurrences(item, needle) for item in value.values())
    if isinstance(value, list):
        return sum(_count_occurrences(item, needle) for item in value)
    return int(value == needle)


def _reference_count(project: Project, identifier: str) -> int:
    domain = project.model_dump(mode="json", exclude={"assets"})
    return _count_occurrences(domain, identifier)


def _visual_detail(project: Project, entity_id: str) -> dict[str, Any]:
    entity = project.visual.entities.items[entity_id]
    selected = (
        project.assets.artifact_versions_by_id.get(
            entity.selected_artifact_version_id,
        )
        if entity.selected_artifact_version_id is not None
        else None
    )
    images = []
    if selected is not None:
        images.append(
            {
                "id": selected.version_id,
                "name": selected.name,
                "url": _artifact_url(selected.version_id),
                "description": entity.description,
                "facetKind": "unknown",
            },
        )
    result: dict[str, Any] = {
        "id": entity.entity_id,
        "name": entity.name,
        "kind": entity.kind,
        "description": entity.description,
        "mediaType": "image",
        "images": images,
        "refsNeeded": [
            variant.requirements for variant in entity.variants.items.values()
        ],
        "prompts": [
            variant.prompt for variant in entity.variants.items.values()
        ],
        "referenceImageRefs": [
            [
                _asset_ref(
                    project.assets.source_versions_by_id[
                        version_id
                    ].logical_asset_id,
                    version_id,
                )
                for version_id in variant.reference_asset_version_ids
            ]
            + [
                _artifact_ref(
                    project.assets.artifact_versions_by_id[version_id].slot_id,
                    version_id,
                )
                for version_id in variant.reference_artifact_version_ids
            ]
            for variant in entity.variants.items.values()
        ],
    }
    if entity.kind == "character":
        result["role"] = "supporting"
    if selected is not None:
        result["primaryUrl"] = _artifact_url(selected.version_id)
    return result


def _asset_library_view(context: _ViewContext) -> dict[str, Any]:
    project = context.snapshot.project
    attached_versions = {
        source.selected_asset_version_id
        for source in project.sources.sources.items.values()
    }
    attached_sources: list[dict[str, Any]] = []
    for source_id in project.sources.sources.order:
        source = project.sources.sources.items[source_id]
        version = project.assets.source_versions_by_id[
            source.selected_asset_version_id
        ]
        attached_sources.append(
            {
                "assetId": version.logical_asset_id,
                "assetVersionId": version.version_id,
                "sourceRef": _asset_ref(
                    version.logical_asset_id,
                    version.version_id,
                ),
                "name": source.display_name or version.name,
                "category": "upload",
                "existence": "available",
                "presentationStatus": "accepted",
                "sourceLabel": source.display_name,
                "mediaType": version.media_kind,
                "checksum": version.checksum,
                "thumbnailUrl": (
                    _asset_url(version.version_id)
                    if version.thumbnail_file_id is not None
                    else None
                ),
                "userNotes": source.user_notes,
                "understandingRef": (
                    f"analysis://{version.version_id}@"
                    f"{source.current_intelligence_version_id}"
                    if source.current_intelligence_version_id is not None
                    else None
                ),
                "referenceCount": _reference_count(project, source.source_id),
                "createdAt": version.created_at.isoformat(),
                "targetVersion": _target(context, f"asset:{source.source_id}"),
                "uiLocator": {
                    "page": "assets",
                    "assetId": version.logical_asset_id,
                },
            },
        )

    available_assets = []
    for version in sorted(
        project.assets.source_versions_by_id.values(),
        key=lambda item: (item.created_at, item.version_id),
    ):
        attached = version.version_id in attached_versions
        available_assets.append(
            {
                "assetId": version.logical_asset_id,
                "assetVersionId": version.version_id,
                "sourceRef": _asset_ref(
                    version.logical_asset_id,
                    version.version_id,
                ),
                "name": version.name,
                "category": "upload",
                "existence": "available",
                "presentationStatus": "accepted" if attached else "draft",
                "mediaType": version.media_kind,
                "checksum": version.checksum,
                "url": _asset_url(version.version_id),
                "thumbnailUrl": (
                    _asset_url(version.version_id)
                    if version.thumbnail_file_id is not None
                    else None
                ),
                "durationSeconds": version.duration_seconds,
                "objectVersion": _target(
                    context,
                    f"asset-version:{version.version_id}",
                ),
                "createdAt": version.created_at.isoformat(),
                "referenceCount": _reference_count(
                    project,
                    version.version_id,
                ),
                "attached": attached,
                "uiLocator": {
                    "page": "assets",
                    "assetId": version.logical_asset_id,
                    "versionId": version.version_id,
                },
            },
        )

    visual_assets: list[dict[str, Any]] = []
    presentation_assets: list[dict[str, Any]] = []
    resolved: list[dict[str, Any] | None] = []
    for entity_id in project.visual.entities.order:
        entity = project.visual.entities.items[entity_id]
        selected = (
            project.assets.artifact_versions_by_id.get(
                entity.selected_artifact_version_id,
            )
            if entity.selected_artifact_version_id is not None
            else None
        )
        selected_ref = (
            _artifact_ref(selected.slot_id, selected.version_id)
            if selected is not None
            else None
        )
        resolved_item = (
            _artifact_ref_view(project, selected.version_id)
            if selected is not None
            else None
        )
        resolved.append(resolved_item)
        reference_refs = [
            _asset_ref(
                project.assets.source_versions_by_id[
                    version_id
                ].logical_asset_id,
                version_id,
            )
            for variant in entity.variants.items.values()
            for version_id in variant.reference_asset_version_ids
        ]
        reference_refs.extend(
            _artifact_ref(
                project.assets.artifact_versions_by_id[version_id].slot_id,
                version_id,
            )
            for variant in entity.variants.items.values()
            for version_id in variant.reference_artifact_version_ids
        )
        visual_assets.append(
            {
                "id": entity.entity_id,
                "name": entity.name,
                "category": entity.kind,
                "selectedRef": selected_ref,
                "resolvedRef": resolved_item,
                "description": entity.description,
                "existence": "available" if selected else "planned",
                "presentationStatus": "accepted" if selected else "draft",
                "mediaType": "image",
                "assetVersionId": None,
                "artifactVersionId": selected.version_id if selected else None,
                "url": _artifact_url(selected.version_id)
                if selected
                else None,
                "thumbnailUrl": (
                    _artifact_url(selected.version_id)
                    if selected and selected.thumbnail_file_id is not None
                    else None
                ),
                "referenceRefs": reference_refs,
                "referenceCount": max(
                    0,
                    _reference_count(project, entity.entity_id) - 1,
                ),
                "uiLocator": {"page": "assets", "assetId": entity.entity_id},
            },
        )
        category = {
            "character": "subject_ref",
            "scene": "env_ref",
            "prop": "brand_constraint",
        }[entity.kind]
        presentation_assets.append(
            {
                "id": entity.entity_id,
                "name": entity.name,
                "category": category,
                "existence": "available" if selected else "planned",
                "presentationStatus": "accepted" if selected else "draft",
                "mediaType": "image",
                "url": _artifact_url(selected.version_id)
                if selected
                else None,
                "thumbnailUrl": (
                    _artifact_url(selected.version_id)
                    if selected and selected.thumbnail_file_id is not None
                    else None
                ),
                "description": entity.description,
                "sourceDescription": "project.json visual entity",
                "sourceRef": selected_ref,
                "referenceCount": max(
                    0,
                    _reference_count(project, entity.entity_id) - 1,
                ),
                "artifactVersionId": selected.version_id if selected else None,
                "targetVersion": _target(
                    context,
                    f"visual:{entity.entity_id}",
                ),
                "detail": _visual_detail(project, entity.entity_id),
                "uiLocator": {"page": "assets", "assetId": entity.entity_id},
            },
        )

    for item in available_assets:
        version = project.assets.source_versions_by_id[item["assetVersionId"]]
        presentation_assets.append(
            {
                "id": version.logical_asset_id,
                "name": version.name,
                "category": "upload",
                "existence": "available",
                "presentationStatus": item["presentationStatus"],
                "mediaType": version.media_kind,
                "url": item["url"],
                "thumbnailUrl": item.get("thumbnailUrl"),
                "sourceDescription": "project.json source asset version",
                "sourceRef": item["sourceRef"],
                "referenceCount": item["referenceCount"],
                "assetVersionId": version.version_id,
                "checksum": version.checksum,
                "durationSeconds": version.duration_seconds,
                "targetVersion": item["objectVersion"],
                "uiLocator": item["uiLocator"],
            },
        )

    known_presentation_ids = {
        item.get("artifactVersionId") for item in presentation_assets
    }
    for artifact in _artifacts(context):
        if artifact["artifactVersionId"] in known_presentation_ids:
            continue
        presentation_assets.append(
            {
                "id": artifact["artifactVersionId"],
                "name": artifact["name"],
                "category": "generated",
                "existence": "available",
                "presentationStatus": (
                    "stale"
                    if artifact["freshnessStatus"] == "stale"
                    else "accepted"
                ),
                "mediaType": _artifact_media_type(artifact["kind"]),
                "url": artifact["url"],
                "description": "",
                "sourceDescription": "project.json artifact version",
                "sourceRef": artifact["sourceRef"],
                "referenceCount": _reference_count(
                    project,
                    artifact["artifactVersionId"],
                ),
                "generatedKind": artifact["kind"],
                "ownerRef": artifact["ownerRef"],
                "artifactVersionId": artifact["artifactVersionId"],
                "targetVersion": _target(
                    context,
                    f"artifact-version:{artifact['artifactVersionId']}",
                ),
                "checksum": artifact["checksum"],
                "durationSeconds": artifact.get("durationSeconds"),
                "uiLocator": artifact["uiLocator"],
            },
        )

    resolved.extend(
        _source_ref_view(project, source.selected_asset_version_id)
        for source in project.sources.sources.items.values()
    )
    return {
        "attachedSources": attached_sources,
        "ingestItems": _asset_ingest_items(context),
        "availableAssets": available_assets,
        "visualAssets": visual_assets,
        "presentationAssets": presentation_assets,
        "resolvedRefs": _unique_refs(resolved),
        "relations": [
            {
                "from": f"project://asset/{source.source_id}",
                "to": _asset_ref(
                    project.assets.source_versions_by_id[
                        source.selected_asset_version_id
                    ].logical_asset_id,
                    source.selected_asset_version_id,
                ),
                "kind": "selects_version",
            }
            for source in project.sources.sources.items.values()
        ],
        "readiness": {"ready": True},
        "blockers": [],
        "targetVersion": _target(context, "project:assets"),
        "uiLocator": {"page": "assets"},
    }


def _composition_view(
    context: _ViewContext,
    composition: Composition | None,
    *,
    kind: Literal["section", "final"],
    section: Section | None = None,
) -> dict[str, Any]:
    project = context.snapshot.project
    sequence = composition.sequence if composition is not None else None
    selected_version_ids = (
        {item.artifact_version_id for item in sequence.items.values()}
        if sequence is not None
        else set()
    )
    selections: list[dict[str, Any]] = []
    resolved: list[dict[str, Any] | None] = []
    if sequence is not None:
        for order, selection_id in enumerate(sequence.order, 1):
            item = sequence.items[selection_id]
            version = project.assets.artifact_versions_by_id[
                item.artifact_version_id
            ]
            resolved.append(_artifact_ref_view(project, version.version_id))
            selections.append(
                {
                    "sourceRef": item.source_ref,
                    "sourceKind": (
                        "unit"
                        if item.source_kind == "unit_video"
                        else "section"
                    ),
                    "artifactRef": _artifact_ref(
                        version.slot_id,
                        version.version_id,
                    ),
                    "artifactVersionId": version.version_id,
                    "slotId": version.slot_id,
                    "order": order,
                    "uiLocator": _artifact_locator(
                        version.owner_ref,
                        version.version_id,
                    ),
                },
            )

    if kind == "section" and section is not None:
        owner_refs = {f"unit:{unit_id}" for unit_id in section.units.order}
        candidate_ids = {
            version.version_id
            for version in project.assets.artifact_versions_by_id.values()
            if version.kind == "unit_video" and version.owner_ref in owner_refs
        }
    else:
        candidate_ids = {
            version.version_id
            for version in project.assets.artifact_versions_by_id.values()
            if version.kind in {"unit_video", "section_video"}
        }
    candidates = [
        _artifact_view(
            context,
            version_id,
            selected=version_id in selected_version_ids,
        )
        for version_id in sorted(candidate_ids)
    ]

    rendered_id = (
        composition.rendered_video_artifact_version_id
        if composition is not None
        else None
    )
    rendered_ref = None
    if rendered_id is not None:
        rendered = project.assets.artifact_versions_by_id[rendered_id]
        rendered_ref = _artifact_ref(rendered.slot_id, rendered.version_id)
        resolved.append(_artifact_ref_view(project, rendered.version_id))

    blockers: list[str] = []
    if kind == "section" and section is not None:
        expected = {
            f"project://unit/{unit_id}" for unit_id in section.units.order
        }
        selected_sources = {item["sourceRef"] for item in selections}
        blockers.extend(
            f"SECTION_COMPOSE_SOURCE_MISSING:{source_ref}"
            for source_ref in sorted(expected - selected_sources)
        )
    elif kind == "final":
        expected = {
            f"project://section/{section_id}"
            for section_id in project.story.sections.order
        }
        selected_sources = {item["sourceRef"] for item in selections}
        blockers.extend(
            f"FINAL_COMPOSE_SOURCE_MISSING:{source_ref}"
            for source_ref in sorted(expected - selected_sources)
        )

    transitions = [
        {
            "path": f"/post_production/{kind}/transitions/{index}",
            "value": f"{transition.kind}:{transition.duration_ms}",
        }
        for index, transition in enumerate(
            composition.transitions if composition is not None else [],
            1,
        )
    ]
    payload: dict[str, Any] = {
        "kind": kind,
        "selections": selections,
        "candidates": candidates,
        "transitions": transitions,
        "audioPlan": composition.audio_plan if composition is not None else "",
        "renderedVideoRef": rendered_ref,
        "renderedVideoUrl": _artifact_url(rendered_id)
        if rendered_id
        else None,
        "resolvedRefs": _unique_refs(resolved),
        "relations": [
            {
                "from": item["sourceRef"],
                "to": item["artifactRef"],
                "kind": "uses_version",
            }
            for item in selections
        ],
        "readiness": {"ready": not blockers},
        "blockers": blockers,
        "targetVersion": _target(
            context,
            f"post:{section.section_id}"
            if section is not None
            else "post:final",
        ),
        "uiLocator": (
            {"page": "section-compose", "sectionId": section.section_id}
            if section is not None
            else {"page": "final-compose"}
        ),
    }
    if section is not None:
        payload.update(
            {
                "sectionId": section.section_id,
                "sectionNumber": project.story.sections.order.index(
                    section.section_id,
                )
                + 1,
                "sectionTitle": section.title,
            },
        )
    else:
        payload["sections"] = [
            {
                "id": section_id,
                "number": number,
                "title": project.story.sections.items[section_id].title,
            }
            for number, section_id in enumerate(
                project.story.sections.order,
                1,
            )
        ]
    return payload


def _ref_index(project: Project) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section_id in project.story.sections.order:
        section = project.story.sections.items[section_id]
        items.append(
            {
                "ref": f"project://section/{section.section_id}",
                "name": section.title,
                "type": "section",
                "uiLocator": {
                    "page": "plan",
                    "sectionId": section.section_id,
                },
            },
        )
        for unit_id in section.units.order:
            unit = section.units.items[unit_id]
            items.append(
                {
                    "ref": f"project://unit/{unit.unit_id}",
                    "name": unit.title or unit.unit_id,
                    "type": "unit",
                    "uiLocator": {
                        "page": "workbench",
                        "unitId": unit.unit_id,
                    },
                },
            )
    items.extend(
        item
        for version_id in project.assets.source_versions_by_id
        if (item := _source_ref_view(project, version_id)) is not None
    )
    items.extend(
        item
        for entity_id in project.visual.entities.order
        if (item := _visual_ref_view(project, entity_id)) is not None
    )
    items.extend(
        item
        for version_id in project.assets.artifact_versions_by_id
        if (item := _artifact_ref_view(project, version_id)) is not None
    )
    deduplicated = {str(item["ref"]): item for item in items}
    return list(deduplicated.values())


def _phase(session: CreatorSessionRecord | None) -> str:
    return _UI_PHASES.get(session.status.value, "error") if session else "idle"


def _envelope(context: _ViewContext, view: dict[str, Any]) -> dict[str, Any]:
    session = context.session
    return {
        "projectId": context.snapshot.project.project_id,
        # Compatibility field: the ETag is the immutable identity of the
        # exact project.json bytes returned by this View, not a SQL revision.
        "approvedRevisionId": context.snapshot.etag,
        "workingBranchId": None,
        "workingHead": None,
        "reviewRevisionId": (
            context.review.candidate_etag
            if context.review is not None
            else None
        ),
        "activeTransactionId": session.active_run_id if session else None,
        "uiPhase": _phase(session),
        "manualEditOverlay": None,
        "agentStatusBar": context.agent_status_bar,
        "view": view,
    }


async def _context(
    project_id: str,
    response: Response,
    services: CreatorFileServices,
) -> _ViewContext:
    try:
        snapshot = await asyncio.to_thread(services.projects.read, project_id)
    except ProjectNotFound as error:
        raise NotFoundError("Project 不存在") from error
    except ProjectStoreError as error:
        raise ValidationError(str(error)) from error

    try:
        session = await asyncio.to_thread(
            services.sessions.get_project_session_snapshot,
            project_id,
        )
    except RuntimeSessionNotFound:
        session = None
    except SessionStoreError as error:
        raise ValidationError(str(error)) from error
    execution_store = ProjectExecutionStore(services.root)
    try:
        review, tasks, runs = await asyncio.gather(
            asyncio.to_thread(services.reviews.active, project_id),
            asyncio.to_thread(execution_store.list_tasks, project_id),
            asyncio.to_thread(
                execution_store.list_specialist_runs,
                project_id,
            ),
        )
    except ExecutionStoreError as error:
        raise ValidationError(str(error)) from error

    response.headers["ETag"] = f'"{snapshot.etag}"'
    response.headers["X-Project-Generation"] = str(snapshot.generation)
    response.headers["Cache-Control"] = "no-cache"
    return _ViewContext(
        snapshot=snapshot,
        session=session,
        review=review,
        tasks=tuple(tasks),
        agent_status_bar=build_agent_status_bar(
            session,
            tasks=tasks,
            runs=runs,
        ),
    )


@router.get("/header")
async def header_view(
    project_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    project = context.snapshot.project
    blockers = (
        []
        if project.name and project.settings.aspect_ratio
        else ["PROJECT_HEADER_INCOMPLETE"]
    )
    view = {
        "id": project.project_id,
        "name": project.name,
        "description": project.description,
        "masterScript": project.description,
        "scenario": project.scenario,
        "aspectRatio": project.settings.aspect_ratio,
        "resolution": project.settings.resolution,
        "contentType": project.settings.content_type,
        "platform": project.settings.platform,
        "language": project.settings.language,
        "targetDuration": project.settings.target_duration_seconds,
        "resolvedRefs": [],
        "relations": [],
        "readiness": {"ready": not blockers},
        "blockers": blockers,
        "targetVersion": _target(context, "project:header"),
        "uiLocator": {"page": "project"},
    }
    return _envelope(context, view)


@router.get("/plan")
async def plan_view(
    project_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    return _envelope(context, _plan_view(context))


@router.get("/sections/{section_id}")
async def section_view(
    project_id: str,
    section_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    project = context.snapshot.project
    section = project.story.sections.items.get(section_id)
    if section is None:
        raise NotFoundError("Section 不存在")
    return _envelope(
        context,
        _section_view(
            context,
            section,
            number=project.story.sections.order.index(section_id) + 1,
        ),
    )


@router.get("/units/{unit_id}/workbench")
async def workbench_view(
    project_id: str,
    unit_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    return _envelope(context, _workbench_view(context, unit_id))


@router.get("/assets")
async def assets_view(
    project_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    return _envelope(context, _asset_library_view(context))


@router.get("/post/sections/{section_id}")
async def section_compose_view(
    project_id: str,
    section_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    project = context.snapshot.project
    section = project.story.sections.items.get(section_id)
    if section is None:
        raise NotFoundError("Section 不存在")
    return _envelope(
        context,
        _composition_view(
            context,
            project.post_production.sections_by_id.get(section_id),
            kind="section",
            section=section,
        ),
    )


@router.get("/post/final")
async def final_compose_view(
    project_id: str,
    response: Response,
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    return _envelope(
        context,
        _composition_view(
            context,
            context.snapshot.project.post_production.final,
            kind="final",
        ),
    )


@router.get("/refs")
async def refs_view(
    project_id: str,
    response: Response,
    query: str = Query(""),
    types: str = Query(""),
    limit: int = Query(20, ge=1, le=100),
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    context = await _context(project_id, response, services)
    allowed = {item.strip() for item in types.split(",") if item.strip()}
    unknown = allowed - {"section", "unit", "asset", "artifact"}
    if unknown:
        raise ValidationError(f"未知 Ref 类型: {sorted(unknown)}")
    needle = query.casefold().strip()
    items = [
        item
        for item in _ref_index(context.snapshot.project)
        if (not allowed or item["type"] in allowed)
        and (
            not needle
            or needle in str(item["name"]).casefold()
            or needle in str(item["ref"]).casefold()
        )
    ]
    items.sort(
        key=lambda item: (
            str(item["type"]),
            str(item["name"]).casefold(),
            str(item["ref"]),
        ),
    )
    return {"items": items[:limit]}


__all__ = ["router"]
