# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-branches,too-many-statements
"""Asset Library View projection."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable

from .errors import ProjectionInputError
from .inputs import IngestItemRecord, ProjectionCatalogs, TextWorkspaceSnapshot
from .r2v_workbench_view import _artifact_view
from .ref_index_view import build_ref_index


def _source_directories(
    snapshot: TextWorkspaceSnapshot,
) -> tuple[tuple[str, str, str], ...]:
    result: set[tuple[str, str, str]] = set()
    for path in snapshot.paths("sources/"):
        parts = PurePosixPath(path).parts
        if len(parts) < 3:
            continue
        segment = parts[1]
        identity = segment.split("--", 1)
        if len(identity) != 2 or not all(identity):
            raise ProjectionInputError(
                f"invalid source directory: {segment!r}",
            )
        result.add((identity[0], identity[1], f"sources/{segment}"))
    return tuple(sorted(result))


def _visual_directories(
    snapshot: TextWorkspaceSnapshot,
) -> tuple[tuple[str, str, str, str], ...]:
    """Return every visual entity, including planned entities without a selection.

    The origin/main Assets page renders planned character/scene/prop cards before
    an image exists.  Enumerating only ``selected.ref`` files would silently
    remove those cards from the cut-over UI.
    """

    result: set[tuple[str, str, str, str]] = set()
    for category in ("characters", "scenes", "props"):
        prefix = f"visual/{category}/"
        for path in snapshot.paths(prefix):
            parts = PurePosixPath(path).parts
            if len(parts) < 4:
                continue
            segment = parts[2]
            identity = segment.split("--", 1)
            if len(identity) != 2 or not all(identity):
                raise ProjectionInputError(
                    f"invalid visual asset directory: {segment!r}",
                )
            result.add(
                (
                    category,
                    identity[0],
                    identity[1],
                    f"visual/{category}/{segment}",
                ),
            )
    return tuple(sorted(result))


def _unit_title(snapshot: TextWorkspaceSnapshot, unit_id: str) -> str | None:
    for path in snapshot.paths("story/sections/"):
        parts = PurePosixPath(path).parts
        if len(parts) < 6 or parts[3] != "units":
            continue
        identity = parts[4].split("--", 2)
        if len(identity) < 2 or identity[1] != unit_id:
            continue
        title = snapshot.text("/".join((*parts[:5], "title.txt")))
        return title or unit_id
    return None


def _reference_count(
    snapshot: TextWorkspaceSnapshot,
    source_ref: str,
    *,
    selection_path: str,
) -> int:
    return sum(
        1
        for path, entry in snapshot.files.items()
        if path.endswith(".ref")
        and path != selection_path
        and entry.content.strip() == source_ref
    )


def _ordered_text_documents(
    snapshot: TextWorkspaceSnapshot,
    root: str,
    directory: str,
) -> dict[int, str]:
    prefix = f"{root}/{directory}/"
    result: dict[int, str] = {}
    for path in snapshot.paths(prefix):
        relative = path[len(prefix) :]
        if "/" in relative or not relative.endswith(".md"):
            continue
        stem = relative[:-3]
        if len(stem) == 6 and stem.isdigit():
            result[int(stem)] = snapshot.text(path, required=True)
    return result


def _prompt_reference_groups(
    snapshot: TextWorkspaceSnapshot,
    root: str,
) -> dict[int, list[str]]:
    prefix = f"{root}/references/"
    result: dict[int, list[tuple[int, str]]] = {}
    for path in snapshot.paths(prefix):
        relative = path[len(prefix) :]
        if "/" in relative or not relative.endswith(".ref"):
            continue
        stem = relative[:-4]
        order_text, separator, position_text = stem.partition("--")
        if separator and order_text.isdigit() and position_text.isdigit():
            order, position = int(order_text), int(position_text)
        else:
            order, position = 1000, len(result.get(1000, ())) + 1
        result.setdefault(order, []).append(
            (position, snapshot.text(path, required=True)),
        )
    return {
        order: [ref for _position, ref in sorted(items)]
        for order, items in result.items()
    }


def _visual_image_refs(
    snapshot: TextWorkspaceSnapshot,
    root: str,
    selected_ref: str,
) -> dict[int, str]:
    result = {1000: selected_ref} if selected_ref else {}
    prefix = f"{root}/images/"
    for path in snapshot.paths(prefix):
        relative = path[len(prefix) :]
        if "/" in relative or not relative.endswith(".ref"):
            continue
        stem = relative[:-4]
        if len(stem) == 6 and stem.isdigit():
            result[int(stem)] = snapshot.text(path, required=True)
    return result


def _detail_image(
    index,
    raw_ref: str,
    *,
    name: str,
    description: str,
    facet_kind: str,
) -> dict[str, Any] | None:
    resolved = index.resolve(raw_ref)
    if resolved is None:
        return None
    identifier = (
        resolved.get("assetVersionId")
        or resolved.get("artifactVersionId")
        or raw_ref
    )
    result = {
        "id": str(identifier),
        "name": name,
        "description": description,
        "facetKind": facet_kind,
    }
    url = resolved.get("url") or resolved.get("thumbnailUrl")
    if url:
        result["url"] = url
    return result


def _visual_detail(
    snapshot: TextWorkspaceSnapshot,
    *,
    index,
    root: str,
    asset_id: str,
    category: str,
    name: str,
    description: str,
    selected_ref: str,
) -> dict[str, Any]:
    prompts = _ordered_text_documents(snapshot, root, "prompts")
    requirements = _ordered_text_documents(snapshot, root, "requirements")
    reference_groups = _prompt_reference_groups(snapshot, root)
    image_refs = _visual_image_refs(snapshot, root, selected_ref)
    orders = sorted(
        {*prompts, *requirements, *reference_groups, *image_refs} or {1000},
    )
    defaults = {
        "characters": "正面基准形象",
        "scenes": "环境基准图",
        "props": "道具基准图",
    }
    facet_defaults = {
        "characters": "front_anchor",
        "scenes": "unknown",
        "props": "usage_state",
    }
    images: list[dict[str, Any]] = []
    for order in orders:
        raw_ref = image_refs.get(order)
        if not raw_ref:
            continue
        image = _detail_image(
            index,
            raw_ref,
            name=requirements.get(order) or defaults[category],
            description=prompts.get(order) or description,
            facet_kind=facet_defaults[category],
        )
        if image is not None:
            images.append(image)
    kind = category[:-1]
    result = {
        "id": asset_id,
        "name": name,
        "kind": kind,
        "description": description,
        "mediaType": "image",
        "images": images,
        "refsNeeded": [
            requirements.get(order) or defaults[category] for order in orders
        ],
        "prompts": [prompts.get(order, "") for order in orders],
        "referenceImageRefs": [
            reference_groups.get(order, []) for order in orders
        ],
    }
    if kind == "character":
        result["role"] = "supporting"
    if images and images[0].get("url"):
        result["primaryUrl"] = images[0]["url"]
    return result


def _source_detail(item, *, user_notes: str) -> dict[str, Any]:
    media_type = (
        item.media_type
        if item.media_type in {"image", "video", "audio"}
        else None
    )
    images = (
        [
            {
                "id": item.id,
                "name": item.name,
                "url": item.url,
                "description": user_notes,
                "facetKind": "unknown",
            },
        ]
        if item.media_type == "image"
        else []
    )
    result = {
        "id": item.logical_asset_id,
        "name": item.name,
        "kind": "material",
        "description": user_notes,
        "primaryUrl": item.url,
        "images": images,
        "refsNeeded": [],
        "prompts": [],
        "referenceImageRefs": [],
    }
    if media_type is not None:
        result["mediaType"] = media_type
    return result


def build_asset_library_view(
    snapshot: TextWorkspaceSnapshot,
    *,
    catalogs: ProjectionCatalogs,
    ingest_items: Iterable[IngestItemRecord] = (),
) -> dict[str, Any]:
    index = build_ref_index(snapshot, catalogs)
    attached: list[dict[str, Any]] = []
    relations: list[dict[str, str]] = []
    resolved_refs: list[dict[str, Any]] = []
    blockers: list[str] = []
    for asset_id, slug, root in _source_directories(snapshot):
        selection_path = f"{root}/selected-version.ref"
        raw_ref = snapshot.text(selection_path, required=True)
        item = index.resolve(raw_ref)
        if item is None or item.get("logicalAssetId") != asset_id:
            blockers.append(f"ATTACHED_SOURCE_VERSION_NOT_FOUND:{asset_id}")
            continue
        resolved_refs.append(item)
        count = _reference_count(
            snapshot,
            raw_ref,
            selection_path=selection_path,
        )
        attached.append(
            {
                "assetId": asset_id,
                "assetVersionId": item["assetVersionId"],
                "sourceRef": raw_ref,
                "name": item["name"],
                "category": "upload",
                "existence": "available",
                "presentationStatus": "accepted",
                "sourceLabel": slug.replace("-", " "),
                "mediaType": item.get("mediaType"),
                "checksum": item.get("checksum"),
                "thumbnailUrl": item.get("thumbnailUrl"),
                "userNotes": snapshot.text(f"{root}/user-notes.md"),
                "understandingRef": snapshot.text(
                    f"{root}/understanding/current.ref",
                )
                or None,
                "referenceCount": count,
                "createdAt": item.get("createdAt"),
                "targetVersion": snapshot.target_version(f"asset:{asset_id}"),
                "uiLocator": {"page": "assets", "assetId": asset_id},
            },
        )
        if count:
            relations.append(
                {
                    "from": f"project://asset/{asset_id}",
                    "to": raw_ref,
                    "kind": "referenced_by_project",
                },
            )

    visual_assets: list[dict[str, Any]] = []
    visual_logical_ids: set[str] = set()
    for category, asset_id, slug, root in _visual_directories(snapshot):
        selected_path = f"{root}/selected.ref"
        raw_ref = snapshot.text(selected_path)
        item = index.resolve(raw_ref) if raw_ref else None
        if raw_ref and item is None:
            blockers.append(f"VISUAL_REFERENCE_NOT_FOUND:{raw_ref}")
        if item is not None:
            resolved_refs.append(item)
            visual_logical_ids.add(str(item.get("logicalAssetId") or ""))
        references = [
            snapshot.text(path, required=True)
            for path in snapshot.paths(f"{root}/references/")
            if path.endswith(".ref")
        ]
        for reference in references:
            resolved_reference = index.resolve(reference)
            if resolved_reference is not None:
                resolved_refs.append(resolved_reference)
        name = snapshot.text(f"{root}/name.txt") or slug.replace("-", " ")
        description = snapshot.text(f"{root}/description.md")
        detail = _visual_detail(
            snapshot,
            index=index,
            root=root,
            asset_id=asset_id,
            category=category,
            name=name,
            description=description,
            selected_ref=raw_ref,
        )
        visual_assets.append(
            {
                "id": asset_id,
                "name": name,
                "category": category[:-1]
                if category.endswith("s")
                else category,
                "selectedRef": raw_ref or None,
                "resolvedRef": item,
                "description": description,
                "existence": "available" if item is not None else "planned",
                "presentationStatus": "accepted"
                if item is not None
                else "draft",
                "mediaType": item.get("mediaType")
                if item is not None
                else "image",
                "assetVersionId": item.get("assetVersionId")
                if item is not None
                else None,
                "artifactVersionId": item.get("artifactVersionId")
                if item is not None
                else None,
                "url": item.get("url") if item is not None else None,
                "thumbnailUrl": item.get("thumbnailUrl")
                if item is not None
                else None,
                "referenceRefs": references,
                "referenceCount": _reference_count(
                    snapshot,
                    raw_ref,
                    selection_path=selected_path,
                )
                if raw_ref
                else 0,
                "targetVersion": snapshot.target_version(f"asset:{asset_id}"),
                "detail": detail,
                "uiLocator": {"page": "assets", "assetId": asset_id},
            },
        )

    available = [
        {
            "assetId": item.logical_asset_id,
            "assetVersionId": item.id,
            "sourceRef": item.source_ref,
            "name": item.name,
            "category": "upload",
            "existence": "available",
            "presentationStatus": "accepted"
            if any(entry["assetVersionId"] == item.id for entry in attached)
            else "draft",
            "mediaType": item.media_type,
            "checksum": item.checksum,
            "url": item.url,
            "thumbnailUrl": item.thumbnail_url,
            "durationSeconds": item.duration_seconds,
            "objectVersion": item.object_version,
            "createdAt": item.created_at,
            "referenceCount": _reference_count(
                snapshot,
                item.source_ref,
                selection_path="",
            ),
            "attached": any(
                entry["assetVersionId"] == item.id for entry in attached
            ),
            "uiLocator": {
                "page": "assets",
                "assetId": item.logical_asset_id,
                "versionId": item.id,
            },
        }
        for item in sorted(
            catalogs.assets,
            key=lambda record: (
                record.logical_asset_id,
                record.created_at,
                record.id,
            ),
        )
    ]

    # One immutable current presentation card per logical source, plus one
    # card per visual entity and currently selected generated Artifact.  This
    # is a page projection for the origin/main unified grid; attach/detach
    # operations continue to use the typed arrays above and exact refs.
    selected_snapshot_refs = {
        entry.content.strip()
        for path, entry in snapshot.files.items()
        if path.endswith(".ref") and entry.content.strip()
    }
    latest_sources: dict[str, Any] = {}
    for item in sorted(
        catalogs.assets,
        key=lambda record: (record.created_at, record.id),
    ):
        if item.logical_asset_id in visual_logical_ids:
            continue
        latest_sources[item.logical_asset_id] = item
    presentation_assets: list[dict[str, Any]] = []
    for item in latest_sources.values():
        selected = item.source_ref in selected_snapshot_refs
        attached_entry = next(
            (
                entry
                for entry in attached
                if entry["assetVersionId"] == item.id
            ),
            None,
        )
        user_notes = str((attached_entry or {}).get("userNotes") or "")
        presentation_assets.append(
            {
                "id": item.logical_asset_id,
                "name": item.name,
                "category": "upload",
                "existence": "available",
                "presentationStatus": "accepted" if selected else "draft",
                "mediaType": item.media_type,
                "url": item.url,
                "thumbnailUrl": item.thumbnail_url,
                "description": user_notes,
                "sourceDescription": "用户上传",
                "sourceRef": item.source_ref,
                "referenceCount": _reference_count(
                    snapshot,
                    item.source_ref,
                    selection_path="",
                ),
                "targetVersion": item.object_version,
                "assetVersionId": item.id,
                "checksum": item.checksum,
                "durationSeconds": item.duration_seconds,
                "userNotes": user_notes,
                "detail": _source_detail(item, user_notes=user_notes),
                "uiLocator": {
                    "page": "assets",
                    "assetId": item.logical_asset_id,
                    "versionId": item.id,
                },
            },
        )
    for item in visual_assets:
        presentation_assets.append(
            {
                "id": item["id"],
                "name": item["name"],
                "category": "env_ref"
                if item["category"] == "scene"
                else "subject_ref",
                "existence": item["existence"],
                "presentationStatus": item["presentationStatus"],
                "mediaType": item["mediaType"],
                "assetVersionId": item.get("assetVersionId"),
                "artifactVersionId": item.get("artifactVersionId"),
                "url": item["url"],
                "thumbnailUrl": item["thumbnailUrl"],
                "description": item["description"],
                "sourceDescription": item["description"],
                "sourceRef": item["selectedRef"],
                "referenceCount": item["referenceCount"],
                "targetVersion": item["targetVersion"],
                "detail": item["detail"],
                "uiLocator": item["uiLocator"],
            },
        )
    for item in sorted(
        catalogs.artifacts,
        key=lambda record: (record.created_at, record.id),
    ):
        selected_by_visual_entity = any(
            visual.get("selectedRef") == item.source_ref
            for visual in visual_assets
        )
        if (
            item.source_ref not in selected_snapshot_refs
            or item.kind
            not in {
                "r2v_storyboard_image",
                "unit_video",
                "section_video",
            }
            or selected_by_visual_entity
        ):
            continue
        owner_id = item.owner_ref.removeprefix("unit:")
        owner_title = _unit_title(snapshot, owner_id)
        semantic_name = (
            f"{owner_title} · {'分镜图' if item.kind == 'r2v_storyboard_image' else '单元成片'}"
            if owner_title
            else item.name
        )
        presentation_assets.append(
            {
                "id": item.id,
                "name": semantic_name,
                "category": "generated",
                "existence": "available",
                "presentationStatus": "stale" if item.stale else "accepted",
                "mediaType": "image"
                if item.kind == "r2v_storyboard_image"
                else "video",
                "url": item.url,
                "thumbnailUrl": item.thumbnail_url,
                "description": str(
                    item.metadata.get("generationPrompt") or "",
                ),
                "sourceDescription": f"生成资产，来自 {item.owner_ref}",
                "sourceRef": item.source_ref,
                "referenceCount": _reference_count(
                    snapshot,
                    item.source_ref,
                    selection_path="",
                ),
                "generatedKind": "storyboard_image"
                if item.kind == "r2v_storyboard_image"
                else item.kind,
                "ownerRef": item.owner_ref,
                "artifactVersionId": item.id,
                "checksum": item.checksum,
                "durationSeconds": item.duration_seconds,
                "targetVersion": item.checksum,
                "uiLocator": _artifact_view(item, selected=True)["uiLocator"],
            },
        )
    ingest = [
        {
            "taskId": item.task_id,
            "assetId": item.asset_id,
            "assetVersionId": item.asset_version_id,
            "name": item.name,
            "status": item.status,
            "progress": item.progress,
            "error": item.error,
        }
        for item in ingest_items
    ]
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "attachedSources": attached,
        "ingestItems": ingest,
        "availableAssets": available,
        "visualAssets": visual_assets,
        "presentationAssets": presentation_assets,
        "resolvedRefs": list(
            {item["ref"]: item for item in resolved_refs}.values(),
        ),
        "relations": relations,
        "readiness": {"ready": not unique_blockers},
        "blockers": unique_blockers,
        "targetVersion": snapshot.target_version("project:assets"),
        "uiLocator": {"page": "assets"},
    }
