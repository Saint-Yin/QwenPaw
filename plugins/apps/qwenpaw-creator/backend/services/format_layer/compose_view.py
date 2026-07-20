# -*- coding: utf-8 -*-
# flake8: noqa: E501
"""Section and Final Compose View projections."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping

from .errors import ProjectionInputError, ProjectionResourceNotFoundError
from .inputs import (
    ProjectionCatalogs,
    RevisionSelections,
    TextWorkspaceSnapshot,
)
from .parsing import parse_sections
from .r2v_workbench_view import _artifact_view
from .ref_index_view import RefIndex, build_ref_index


def _parse_sequence(
    snapshot: TextWorkspaceSnapshot,
    prefix: str,
    *,
    default_source_kind: str,
    source_artifact_kinds: Mapping[str, str],
    catalogs: ProjectionCatalogs,
    index: RefIndex,
    decode_source_kind: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    selections: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    blockers: list[str] = []
    for path in snapshot.paths(prefix):
        if not path.endswith(".ref"):
            continue
        filename = PurePosixPath(path).name[:-4]
        order_text, separator, source_part = filename.partition("--")
        if not separator or not order_text.isdigit() or not source_part:
            raise ProjectionInputError(
                f"invalid compose sequence entry: {path}",
            )
        source_kind = default_source_kind
        source_id = source_part
        encoded_kind, kind_separator, encoded_id = source_part.partition("--")
        if (
            decode_source_kind
            and kind_separator
            and encoded_kind in source_artifact_kinds
        ):
            source_kind = encoded_kind
            source_id = encoded_id
        if source_kind not in source_artifact_kinds or not source_id:
            raise ProjectionInputError(
                f"invalid compose sequence source identity: {path}",
            )
        raw_ref = snapshot.text(path, required=True)
        item = index.resolve(raw_ref)
        if item is None or item["type"] != "artifact":
            blockers.append(f"COMPOSE_ARTIFACT_VERSION_NOT_FOUND:{raw_ref}")
            continue
        record = next(
            (
                candidate
                for candidate in catalogs.artifacts
                if candidate.id == item["artifactVersionId"]
                and candidate.slot_id == item["slotId"]
            ),
            None,
        )
        expected_artifact_kind = source_artifact_kinds[source_kind]
        expected_owner = f"{source_kind}:{source_id}"
        if (
            record is None
            or record.kind != expected_artifact_kind
            or record.owner_ref != expected_owner
        ):
            blockers.append(
                f"COMPOSE_ARTIFACT_OWNER_KIND_MISMATCH:{source_kind}:{source_id}:{raw_ref}",
            )
            continue
        if item.get("freshnessStatus") == "stale":
            blockers.append(f"COMPOSE_ARTIFACT_VERSION_STALE:{raw_ref}")
        resolved.append(item)
        selections.append(
            {
                "sourceRef": f"project://{source_kind}/{source_id}",
                "sourceKind": source_kind,
                "artifactRef": raw_ref,
                "artifactVersionId": item["artifactVersionId"],
                "slotId": item["slotId"],
                "order": int(order_text),
                "uiLocator": item["uiLocator"],
            },
        )
    selections.sort(key=lambda item: (item["order"], item["sourceRef"]))
    return selections, resolved, blockers


def _transition_entries(
    snapshot: TextWorkspaceSnapshot,
    prefix: str,
) -> list[dict[str, str]]:
    return [
        {"path": path, "value": snapshot.text(path, required=True)}
        for path in snapshot.paths(prefix)
        if path.endswith((".txt", ".md"))
    ]


def build_section_compose_view(
    snapshot: TextWorkspaceSnapshot,
    section_id: str,
    *,
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
) -> dict[str, Any]:
    sections = parse_sections(snapshot)
    section = next((item for item in sections if item.id == section_id), None)
    if section is None:
        raise ProjectionResourceNotFoundError(
            f"section not found in snapshot: {section_id}",
        )
    index = build_ref_index(snapshot, catalogs)
    root = f"post/sections/{section_id}"
    sequence, resolved, blockers = _parse_sequence(
        snapshot,
        f"{root}/sequence/",
        default_source_kind="unit",
        source_artifact_kinds={"unit": "unit_video"},
        catalogs=catalogs,
        index=index,
    )
    expected_sources = {f"project://unit/{unit.id}" for unit in section.units}
    selected_sources = {item["sourceRef"] for item in sequence}
    for missing in sorted(expected_sources - selected_sources):
        blockers.append(f"SECTION_COMPOSE_SOURCE_MISSING:{missing}")
    candidates = [
        _artifact_view(
            record,
            selected=selections.artifact_versions.get(record.slot_id)
            == record.id,
        )
        for record in catalogs.artifacts
        if record.kind == "unit_video"
        and record.owner_ref in {f"unit:{unit.id}" for unit in section.units}
    ]
    rendered_ref = snapshot.text(f"{root}/rendered-video.ref")
    rendered_video_url: str | None = None
    if rendered_ref:
        rendered = index.resolve(rendered_ref)
        if rendered is None:
            blockers.append(
                f"SECTION_RENDERED_VERSION_NOT_FOUND:{rendered_ref}",
            )
        else:
            resolved.append(rendered)
            rendered_video_url = rendered.get("url")
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "kind": "section",
        "sectionId": section_id,
        "sectionNumber": next(
            index + 1
            for index, item in enumerate(sections)
            if item.id == section_id
        ),
        "sectionTitle": section.title,
        "selections": sequence,
        "candidates": candidates,
        "transitions": _transition_entries(snapshot, f"{root}/transitions/"),
        "audioPlan": snapshot.text(f"{root}/audio-plan.md"),
        "subtitlesVtt": snapshot.text(f"{root}/subtitles.vtt"),
        "renderedVideoRef": rendered_ref or None,
        "renderedVideoUrl": rendered_video_url,
        "resolvedRefs": list(
            {item["ref"]: item for item in resolved}.values(),
        ),
        "relations": [
            {
                "from": item["sourceRef"],
                "to": item["artifactRef"],
                "kind": "uses_version",
            }
            for item in sequence
        ],
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": snapshot.target_version(f"post:{section_id}"),
        "uiLocator": {"page": "section-compose", "sectionId": section_id},
    }


def build_final_compose_view(
    snapshot: TextWorkspaceSnapshot,
    *,
    catalogs: ProjectionCatalogs,
    selections: RevisionSelections,
) -> dict[str, Any]:
    sections = parse_sections(snapshot)
    index = build_ref_index(snapshot, catalogs)
    root = "post/final"
    sequence, resolved, blockers = _parse_sequence(
        snapshot,
        f"{root}/sequence/",
        default_source_kind="section",
        source_artifact_kinds={
            "section": "section_video",
            "unit": "unit_video",
        },
        catalogs=catalogs,
        index=index,
        decode_source_kind=True,
    )
    section_order = {
        section.id: index for index, section in enumerate(sections)
    }
    unit_locations = {
        unit.id: (section.id, unit_index)
        for section in sections
        for unit_index, unit in enumerate(section.units)
    }
    candidates_with_order: list[
        tuple[tuple[int, int, str], dict[str, Any]]
    ] = []
    for record in catalogs.artifacts:
        if (
            record.kind not in {"section_video", "unit_video"}
            or record.stale
            or selections.artifact_versions.get(record.slot_id) != record.id
        ):
            continue
        owner_kind, separator, owner_id = record.owner_ref.partition(":")
        if not separator:
            continue
        if record.kind == "section_video" and owner_kind == "section":
            section_id = owner_id
            if section_id not in section_order:
                continue
            source_kind = "section"
            order = (section_order[section_id], 0, record.id)
        elif record.kind == "unit_video" and owner_kind == "unit":
            location = unit_locations.get(owner_id)
            if location is None:
                continue
            section_id, unit_index = location
            source_kind = "unit"
            order = (section_order[section_id], unit_index + 1, record.id)
        else:
            continue
        candidate = _artifact_view(record, selected=True)
        candidate.update({"sectionId": section_id, "sourceKind": source_kind})
        candidates_with_order.append((order, candidate))
    candidates = [
        item
        for _order, item in sorted(
            candidates_with_order,
            key=lambda pair: pair[0],
        )
    ]
    rendered_ref = snapshot.text(f"{root}/rendered-video.ref")
    rendered_video_url: str | None = None
    if rendered_ref:
        rendered = index.resolve(rendered_ref)
        if rendered is None:
            blockers.append(f"FINAL_RENDERED_VERSION_NOT_FOUND:{rendered_ref}")
        else:
            resolved.append(rendered)
            rendered_video_url = rendered.get("url")
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "kind": "final",
        "sections": [
            {"id": section.id, "number": index + 1, "title": section.title}
            for index, section in enumerate(sections)
        ],
        "selections": sequence,
        "candidates": candidates,
        "transitions": _transition_entries(snapshot, f"{root}/transitions/"),
        "audioPlan": snapshot.text(f"{root}/audio-plan.md"),
        "mix": snapshot.text(f"{root}/mix.md"),
        "subtitlesVtt": snapshot.text(f"{root}/subtitles.vtt"),
        "renderedVideoRef": rendered_ref or None,
        "renderedVideoUrl": rendered_video_url,
        "resolvedRefs": list(
            {item["ref"]: item for item in resolved}.values(),
        ),
        "relations": [
            {
                "from": item["sourceRef"],
                "to": item["artifactRef"],
                "kind": "uses_version",
            }
            for item in sequence
        ],
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": snapshot.target_version("post:final"),
        "uiLocator": {"page": "final-compose"},
    }
