"""R2V Workbench View projection."""

from __future__ import annotations

from typing import Any

from .errors import ProjectionInputError, UnsupportedViewError
from .inputs import (
    ArtifactVersionRecord,
    ProjectionCatalogs,
    ProviderConstraintSnapshot,
    RevisionSelections,
    TextWorkspaceSnapshot,
)
from .parsing import find_unit, parse_sections
from .plan_view import _unit_view
from .ref_index_view import build_ref_index, resolve_many


def _selected_artifact(
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
    *,
    owner_ref: str,
    kind: str,
) -> tuple[ArtifactVersionRecord | None, str | None, list[str]]:
    records = [item for item in catalogs.artifacts if item.owner_ref == owner_ref and item.kind == kind]
    slots = sorted({item.slot_id for item in records})
    if len(slots) > 1:
        return None, None, [f"MULTIPLE_{kind.upper()}_SLOTS"]
    if not slots:
        return None, None, []
    slot_id = slots[0]
    selected_id = selections.artifact_versions.get(slot_id)
    if selected_id is None:
        return None, slot_id, []
    selected = next((item for item in records if item.id == selected_id), None)
    if selected is None:
        return None, slot_id, [f"SELECTED_ARTIFACT_VERSION_NOT_FOUND:{selected_id}"]
    if selected.stale:
        return selected, slot_id, [f"{kind.upper()}_STALE:{selected.stale_reason or 'INPUT_CHANGED'}"]
    return selected, slot_id, []


def _artifact_view(record: ArtifactVersionRecord, *, selected: bool) -> dict[str, Any]:
    owner_kind, separator, owner_id = record.owner_ref.partition(":")
    compose_owner_ref = (
        f"project://{owner_kind}/{owner_id}"
        if separator and owner_kind in {"unit", "section"} and owner_id
        else record.owner_ref
    )
    if owner_kind == "unit" and owner_id:
        ui_locator = {"page": "workbench", "unitId": owner_id, "versionId": record.id}
    elif owner_kind == "section" and owner_id:
        ui_locator = {"page": "section-compose", "sectionId": owner_id, "versionId": record.id}
    else:
        ui_locator = {"page": "final-compose", "versionId": record.id}
    result: dict[str, Any] = {
        "id": record.id,
        "name": record.name,
        "artifactVersionId": record.id,
        "sourceRef": record.source_ref,
        "slotId": record.slot_id,
        "kind": record.kind,
        # This is a server-resolved compose source, not a browser inference
        # from Artifact provenance or slot naming.
        "ownerRef": compose_owner_ref,
        "uiLocator": ui_locator,
        "url": record.url,
        "checksum": record.checksum,
        "createdAt": record.created_at,
        "basedOnRevisionId": record.based_on_revision_id,
        "provenanceRefs": list(record.provenance_refs),
        "selected": selected,
        "freshnessStatus": "stale" if record.stale else "current",
    }
    if record.duration_seconds is not None:
        result["durationSeconds"] = record.duration_seconds
    if record.input_fingerprint is not None:
        result["inputFingerprint"] = record.input_fingerprint
    if record.stale_reason is not None:
        result["staleReason"] = record.stale_reason
    return result


def _artifact_views(
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
    *,
    owner_ref: str,
    kind: str,
) -> list[dict[str, Any]]:
    records = sorted(
        (item for item in catalogs.artifacts if item.owner_ref == owner_ref and item.kind == kind),
        key=lambda item: (item.created_at, item.id),
    )
    return [
        _artifact_view(item, selected=selections.artifact_versions.get(item.slot_id) == item.id)
        for item in records
    ]


def _production_refs(snapshot: TextWorkspaceSnapshot, prefix: str) -> list[str]:
    refs: list[str] = []
    for path in snapshot.paths(prefix):
        if path.endswith(".ref"):
            refs.append(snapshot.text(path, required=True))
    return refs


def _production_reference_bindings(
    snapshot: TextWorkspaceSnapshot,
    *,
    storyboard_prefix: str,
    video_prefix: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], set[str]] = {}
    for reference_set, prefix in (("storyboard", storyboard_prefix), ("video", video_prefix)):
        for path in snapshot.paths(prefix):
            if not path.endswith(".ref"):
                continue
            relative = path.removeprefix(prefix).lstrip("/")
            category = "scene" if relative == "scene.ref" else relative.split("/", 1)[0]
            if category not in {"scene", "characters", "props", "sources"}:
                raise ProjectionInputError(f"unknown production reference category: {path}")
            source_ref = snapshot.text(path, required=True)
            grouped.setdefault((category, source_ref), set()).add(reference_set)
    return [
        {
            "sourceRef": source_ref,
            "field": field,
            "referenceSets": sorted(reference_sets),
        }
        for (field, source_ref), reference_sets in sorted(grouped.items())
    ]


def _selection_consistency_blockers(
    snapshot_ref: str,
    selected: ArtifactVersionRecord | None,
    *,
    label: str,
) -> list[str]:
    if not snapshot_ref:
        return []
    if selected is None or snapshot_ref != selected.source_ref:
        return [f"{label}_SELECTION_MISMATCH"]
    return []


def build_r2v_workbench_view(
    snapshot: TextWorkspaceSnapshot,
    unit_id: str,
    *,
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
    provider: ProviderConstraintSnapshot,
) -> dict[str, Any]:
    sections = parse_sections(snapshot)
    _, unit = find_unit(sections, unit_id)
    if unit.route != "r2v":
        raise UnsupportedViewError(f"unit is not an r2v unit: {unit_id}")
    index = build_ref_index(snapshot, catalogs)
    unit_view, blockers = _unit_view(snapshot, unit, number=1, index=index)
    owner_ref = f"unit:{unit.id}"
    storyboard, storyboard_slot, selection_blockers = _selected_artifact(
        catalogs, selections, owner_ref=owner_ref, kind="r2v_storyboard_image"
    )
    video, _, video_selection_blockers = _selected_artifact(
        catalogs, selections, owner_ref=owner_ref, kind="unit_video"
    )
    blockers.extend(selection_blockers)
    blockers.extend(video_selection_blockers)
    if storyboard is None:
        blockers.append("STORYBOARD_VERSION_REQUIRED")
    if unit.duration < provider.min_duration or unit.duration > provider.max_duration:
        blockers.append("R2V_DURATION_OUTSIDE_PROVIDER_BOUNDS")
    if provider.allowed_durations and unit.duration not in provider.allowed_durations:
        blockers.append("R2V_DURATION_NOT_SUPPORTED_BY_PROVIDER")

    root = f"{unit.root}/production/r2v"
    storyboard_snapshot_ref = snapshot.text(f"{root}/storyboard/selected.ref")
    video_snapshot_ref = snapshot.text(f"{root}/video/selected.ref")
    blockers.extend(_selection_consistency_blockers(storyboard_snapshot_ref, storyboard, label="STORYBOARD"))
    blockers.extend(_selection_consistency_blockers(video_snapshot_ref, video, label="VIDEO"))
    storyboard_prefix = f"{root}/storyboard/references/"
    video_prefix = f"{root}/video/references/"
    storyboard_inputs = _production_refs(snapshot, storyboard_prefix)
    video_references = _production_refs(snapshot, video_prefix)
    input_reference_bindings = _production_reference_bindings(
        snapshot,
        storyboard_prefix=storyboard_prefix,
        video_prefix=video_prefix,
    )
    video_input_refs = ([storyboard.source_ref] if storyboard else []) + [
        ref for ref in video_references if storyboard is None or ref != storyboard.source_ref
    ]
    if len(video_input_refs) > provider.max_reference_images:
        blockers.append("R2V_REFERENCE_IMAGE_LIMIT_EXCEEDED")
    resolved, ref_blockers = resolve_many(index, [*storyboard_inputs, *video_input_refs])
    blockers.extend(ref_blockers)
    unique_blockers = list(dict.fromkeys(blockers))
    relations = [
        {"from": f"project://unit/{unit.id}", "to": ref, "kind": "references"}
        for ref in [*storyboard_inputs, *video_input_refs]
    ]
    return {
        "kind": "r2v",
        "unit": unit_view,
        "storyboardPrompt": snapshot.text(f"{root}/storyboard/prompt.md"),
        "videoPrompt": snapshot.text(f"{root}/video/prompt.md"),
        "storyboardVersions": _artifact_views(
            catalogs, selections, owner_ref=owner_ref, kind="r2v_storyboard_image"
        ),
        "videoVersions": _artifact_views(catalogs, selections, owner_ref=owner_ref, kind="unit_video"),
        "selectedStoryboardVersionId": storyboard.id if storyboard else None,
        "selectedVideoVersionId": video.id if video else None,
        "storyboardInputRefs": storyboard_inputs,
        "videoInputRefs": video_input_refs,
        "inputReferenceBindings": input_reference_bindings,
        "providerConstraints": {
            "provider": provider.provider,
            "model": provider.model,
            "version": provider.version,
            "capturedAt": provider.captured_at,
            "minDuration": provider.min_duration,
            "maxDuration": provider.max_duration,
            "maxReferenceImages": provider.max_reference_images,
            "allowedDurations": list(provider.allowed_durations),
        },
        "continuity": unit.continuity,
        "resolvedRefs": resolved,
        "relations": relations,
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": snapshot.target_version(f"unit:{unit.id}"),
        "uiLocator": {"page": "workbench", "unitId": unit.id, "route": "r2v"},
        "selectionSource": {"revisionId": selections.revision_id, "storyboardSlotId": storyboard_slot},
    }
