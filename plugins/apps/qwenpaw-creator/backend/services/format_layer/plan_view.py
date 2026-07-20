# -*- coding: utf-8 -*-
"""Plan View projection."""

from __future__ import annotations

from typing import Any

from .inputs import ProjectionCatalogs, TextWorkspaceSnapshot
from .parsing import ParsedUnit, parse_reference_duration, parse_sections
from .ref_index_view import RefIndex, build_ref_index, resolve_many


def _unit_ref_groups(unit: ParsedUnit) -> dict[str, list[str]]:
    groups = {"scene": [], "characters": [], "props": [], "materials": []}
    for relative, raw_ref in unit.refs:
        if relative == "scene.ref":
            groups["scene"].append(raw_ref)
        elif relative.startswith("characters/"):
            groups["characters"].append(raw_ref)
        elif relative.startswith("props/"):
            groups["props"].append(raw_ref)
        elif relative.startswith("sources/"):
            groups["materials"].append(raw_ref)
    return groups


def _unit_view(
    snapshot: TextWorkspaceSnapshot,
    unit: ParsedUnit,
    *,
    number: int,
    index: RefIndex,
) -> tuple[dict[str, Any], list[str]]:
    refs = _unit_ref_groups(unit)
    raw_refs = [raw for _, raw in unit.refs]
    resolved, blockers = resolve_many(index, raw_refs)
    if unit.duration <= 0:
        blockers.append("UNIT_DURATION_MUST_BE_POSITIVE")
    if unit.route == "r2v" and unit.duration > 15:
        blockers.append("R2V_DURATION_EXCEEDS_15_SECONDS")
    target_ref = f"unit:{unit.id}"
    storyboard_prompt = ""
    storyboard_image_url: str | None = None
    storyboard_image_version_id: str | None = None
    video_prompt = ""
    video_url: str | None = None
    if unit.route == "r2v":
        r2v_root = f"{unit.root}/production/r2v"
        storyboard_prompt = snapshot.text(f"{r2v_root}/storyboard/prompt.md")
        video_prompt = snapshot.text(f"{r2v_root}/video/prompt.md")
        selected_storyboard_ref = snapshot.text(
            f"{r2v_root}/storyboard/selected.ref",
        )
        if selected_storyboard_ref:
            selected_storyboard = index.resolve(selected_storyboard_ref)
            if selected_storyboard is not None:
                storyboard_image_url = selected_storyboard.get("url")
                storyboard_image_version_id = selected_storyboard.get(
                    "artifactVersionId",
                )
        selected_video_ref = snapshot.text(f"{r2v_root}/video/selected.ref")
        if selected_video_ref:
            selected_video = index.resolve(selected_video_ref)
            if selected_video is not None:
                video_url = selected_video.get("url")
    elif unit.route == "edit":
        selected_video_ref = snapshot.text(
            f"{unit.root}/production/edit/rendered-video.ref",
        )
        if selected_video_ref:
            selected_video = index.resolve(selected_video_ref)
            if selected_video is not None:
                video_url = selected_video.get("url")
    view = {
        "id": unit.id,
        "number": number,
        "title": unit.title,
        "taskType": unit.route,
        "duration": unit.duration,
        # Presentation fields retained for the origin/main Unit detail.  They
        # are derived from canonical R2V Workspace files and the immutable
        # Artifact registry; the View remains read-only and non-authoritative.
        "storyboardPrompt": storyboard_prompt,
        "storyboardImageUrl": storyboard_image_url,
        "storyboardImageVersionId": storyboard_image_version_id,
        "videoPrompt": video_prompt,
        "videoUrl": video_url,
        "shots": [
            {
                "id": shot.id,
                "number": shot_number,
                "description": shot.description,
                "camera": shot.camera,
                "framing": shot.framing,
                "cameraDescription": shot.camera_description,
                "dialogue": shot.dialogue,
                "duration": shot.duration,
                "targetVersion": snapshot.target_version(f"shot:{shot.id}"),
            }
            for shot_number, shot in enumerate(unit.shots, 1)
        ],
        "sceneRef": refs["scene"][0] if refs["scene"] else None,
        "characterRefs": refs["characters"],
        "propRefs": refs["props"],
        "materialRefs": refs["materials"],
        "resolvedRefs": resolved,
        "relations": [
            {
                "from": f"project://unit/{unit.id}",
                "to": raw_ref,
                "kind": "references",
            }
            for raw_ref in raw_refs
        ],
        "readiness": {
            "ready": not blockers,
            "blockers": list(dict.fromkeys(blockers)),
        },
        "blockers": list(dict.fromkeys(blockers)),
        "targetVersion": snapshot.target_version(target_ref),
        "uiLocator": {"page": "workbench", "unitId": unit.id},
    }
    return view, blockers


def build_plan_view(
    snapshot: TextWorkspaceSnapshot,
    catalogs: ProjectionCatalogs = ProjectionCatalogs(),
) -> dict[str, Any]:
    sections = parse_sections(snapshot)
    index = build_ref_index(snapshot, catalogs)
    section_views: list[dict[str, Any]] = []
    page_blockers: list[str] = []
    page_relations: list[dict[str, str]] = []
    page_resolved: dict[str, dict[str, Any]] = {}
    for section_number, section in enumerate(sections, 1):
        unit_views: list[dict[str, Any]] = []
        section_blockers: list[str] = []
        for unit_number, unit in enumerate(section.units, 1):
            unit_view, blockers = _unit_view(
                snapshot,
                unit,
                number=unit_number,
                index=index,
            )
            unit_views.append(unit_view)
            section_blockers.extend(blockers)
            page_relations.append(
                {
                    "from": f"project://section/{section.id}",
                    "to": f"project://unit/{unit.id}",
                    "kind": "contains",
                },
            )
            page_relations.extend(unit_view["relations"])
            for item in unit_view["resolvedRefs"]:
                page_resolved[item["ref"]] = item

        prefix = f"section:{section.id}"
        target_versions = {
            ref: version
            for ref, version in snapshot.target_versions.items()
            if ref == prefix or ref.startswith(f"{prefix}/")
        }
        section_views.append(
            {
                "id": section.id,
                "number": section_number,
                "title": section.title,
                "narrative": section.narrative,
                "durationBudget": section.duration_budget,
                "constraints": list(section.constraints),
                "script": section.script,
                "units": unit_views,
                "resolvedRefs": list(
                    {
                        item["ref"]: item
                        for unit in unit_views
                        for item in unit["resolvedRefs"]
                    }.values(),
                ),
                "relations": [
                    relation
                    for unit in unit_views
                    for relation in unit["relations"]
                ],
                "readiness": {
                    "ready": not section_blockers,
                    "blockers": list(dict.fromkeys(section_blockers)),
                },
                "blockers": list(dict.fromkeys(section_blockers)),
                "targetVersions": target_versions,
                "targetVersion": snapshot.target_version(prefix),
                "uiLocator": {"page": "plan", "sectionId": section.id},
            },
        )
        page_blockers.extend(section_blockers)

    unique_blockers = list(dict.fromkeys(page_blockers))
    return {
        "title": snapshot.text("title.txt", required=True),
        "outline": snapshot.text("story/outline.md"),
        "aspectRatio": snapshot.text(
            "settings/aspect-ratio.txt",
            required=True,
        ),
        "targetDuration": parse_reference_duration(
            snapshot.text("settings/target-duration.txt"),
            label="project target duration",
        ),
        "sections": section_views,
        "resolvedRefs": list(page_resolved.values()),
        "relations": page_relations,
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": snapshot.target_version("project:plan"),
        "uiLocator": {"page": "plan"},
    }
