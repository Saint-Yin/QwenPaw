# -*- coding: utf-8 -*-
"""Reference Index View projection and bounded reference resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .errors import ProjectionInputError
from .inputs import ProjectionCatalogs, TextWorkspaceSnapshot
from .parsing import ParsedSection, parse_sections


def _decode_versioned_ref(raw: str, scheme: str) -> tuple[str, str] | None:
    parsed = urlparse(raw)
    if parsed.scheme != scheme or parsed.path not in {"", "/"}:
        return None
    identity, separator, version_id = parsed.netloc.rpartition("@")
    if not separator or not identity or not version_id:
        return None
    return unquote(identity), unquote(version_id)


def _entity_locator(kind: str, identifier: str) -> dict[str, str]:
    if kind == "section":
        return {"page": "plan", "sectionId": identifier}
    if kind == "unit":
        return {"page": "workbench", "unitId": identifier}
    raise ProjectionInputError(f"unknown entity locator kind: {kind}")


def _artifact_locator(owner_ref: str, version_id: str) -> dict[str, str]:
    if owner_ref.startswith("unit:"):
        return {
            "page": "workbench",
            "unitId": owner_ref.split(":", 1)[1],
            "versionId": version_id,
        }
    if owner_ref.startswith("section:"):
        return {
            "page": "section-compose",
            "sectionId": owner_ref.split(":", 1)[1],
            "versionId": version_id,
        }
    return {"page": "final-compose", "versionId": version_id}


def _entity_items(
    project_id: str,
    sections: Iterable[ParsedSection],
) -> list[dict[str, Any]]:
    del project_id
    result: list[dict[str, Any]] = []
    for section in sections:
        result.append(
            {
                "ref": f"project://section/{section.id}",
                "name": section.title,
                "type": "section",
                "version": None,
                "uiLocator": _entity_locator("section", section.id),
            },
        )
        for unit in section.units:
            result.append(
                {
                    "ref": f"project://unit/{unit.id}",
                    "name": unit.title,
                    "type": "unit",
                    "version": None,
                    "uiLocator": _entity_locator("unit", unit.id),
                },
            )
    return result


@dataclass(frozen=True, slots=True)
class RefIndex:
    """A flat autocomplete index; it is not a cross-page relationship model."""

    items: tuple[dict[str, Any], ...]

    def resolve(self, raw_ref: str) -> dict[str, Any] | None:
        parsed = urlparse(raw_ref)
        if parsed.scheme == "project":
            kind = parsed.netloc
            identifier = parsed.path.strip("/")
            canonical = f"project://{kind}/{identifier}"
            item = next(
                (
                    candidate
                    for candidate in self.items
                    if candidate["ref"] == canonical
                ),
                None,
            )
            if item is not None:
                return {**item, "ref": raw_ref}
            return None

        asset_identity = _decode_versioned_ref(raw_ref, "asset")
        if asset_identity is not None:
            logical_id, version_id = asset_identity
            item = next(
                (
                    candidate
                    for candidate in self.items
                    if candidate["type"] == "asset"
                    and candidate.get("logicalAssetId") == logical_id
                    and candidate.get("assetVersionId") == version_id
                ),
                None,
            )
            return {**item, "ref": raw_ref} if item is not None else None

        artifact_identity = _decode_versioned_ref(raw_ref, "artifact")
        if artifact_identity is not None:
            slot_id, version_id = artifact_identity
            item = next(
                (
                    candidate
                    for candidate in self.items
                    if candidate["type"] == "artifact"
                    and candidate.get("slotId") == slot_id
                    and candidate.get("artifactVersionId") == version_id
                ),
                None,
            )
            return {**item, "ref": raw_ref} if item is not None else None
        analysis_identity = _decode_versioned_ref(raw_ref, "analysis")
        if analysis_identity is not None:
            asset_version_id, analysis_version_id = analysis_identity
            item = next(
                (
                    candidate
                    for candidate in self.items
                    if candidate["type"] == "analysis"
                    and candidate.get("assetVersionId") == asset_version_id
                    and candidate.get("analysisVersionId")
                    == analysis_version_id
                ),
                None,
            )
            return {**item, "ref": raw_ref} if item is not None else None
        return None

    def search(
        self,
        query: str = "",
        *,
        types: Iterable[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ProjectionInputError(
                "ref search limit must be between 1 and 100",
            )
        allowed = set(
            types or {"section", "unit", "asset", "artifact", "analysis"},
        )
        unknown = allowed - {
            "section",
            "unit",
            "asset",
            "artifact",
            "analysis",
        }
        if unknown:
            raise ProjectionInputError(
                f"unknown ref search types: {sorted(unknown)}",
            )
        needle = query.casefold().strip()
        selected = [
            dict(item)
            for item in self.items
            if item["type"] in allowed
            and (
                not needle
                or needle in item["name"].casefold()
                or needle in item["ref"].casefold()
            )
        ]
        selected.sort(
            key=lambda item: (
                item["type"],
                item["name"].casefold(),
                item["ref"],
            ),
        )
        return selected[:limit]


def build_ref_index(
    snapshot: TextWorkspaceSnapshot,
    catalogs: ProjectionCatalogs,
) -> RefIndex:
    items = _entity_items(snapshot.project_id, parse_sections(snapshot))
    for record in catalogs.assets:
        items.append(
            {
                "ref": record.source_ref,
                "name": record.name,
                "type": "asset",
                "version": record.id,
                "thumbnailUrl": record.thumbnail_url,
                "url": record.url,
                "mediaType": record.media_type,
                "checksum": record.checksum,
                "logicalAssetId": record.logical_asset_id,
                "assetVersionId": record.id,
                "createdAt": record.created_at,
                "uiLocator": {
                    "page": "assets",
                    "assetId": record.logical_asset_id,
                    "versionId": record.id,
                },
            },
        )
    assets_by_version = {record.id: record for record in catalogs.assets}
    for path in snapshot.paths("sources/"):
        if not path.endswith("/understanding/current.ref"):
            continue
        raw_ref = snapshot.text(path)
        identity = _decode_versioned_ref(raw_ref, "analysis")
        if identity is None:
            continue
        asset_version_id, analysis_version_id = identity
        asset = assets_by_version.get(asset_version_id)
        if asset is None:
            continue
        items.append(
            {
                "ref": raw_ref,
                "name": f"{asset.name} · 素材理解",
                "type": "analysis",
                "version": analysis_version_id,
                "assetVersionId": asset_version_id,
                "analysisVersionId": analysis_version_id,
                "uiLocator": {
                    "page": "assets",
                    "assetId": asset.logical_asset_id,
                    "versionId": asset.id,
                },
            },
        )
    for record in catalogs.artifacts:
        items.append(
            {
                "ref": record.source_ref,
                "name": record.name,
                "type": "artifact",
                "version": record.id,
                "thumbnailUrl": record.thumbnail_url,
                "url": record.url,
                "mediaType": record.kind,
                "checksum": record.checksum,
                "slotId": record.slot_id,
                "artifactVersionId": record.id,
                "createdAt": record.created_at,
                "freshnessStatus": "stale" if record.stale else "current",
                "staleReason": record.stale_reason,
                "uiLocator": _artifact_locator(record.owner_ref, record.id),
            },
        )
    deduplicated = {item["ref"]: item for item in items}
    ordered = tuple(dict(deduplicated[key]) for key in sorted(deduplicated))
    return RefIndex(ordered)


def resolve_many(
    index: RefIndex,
    raw_refs: Iterable[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    resolved: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: set[str] = set()
    for raw_ref in raw_refs:
        if raw_ref in seen:
            continue
        seen.add(raw_ref)
        item = index.resolve(raw_ref)
        if item is None:
            blockers.append(f"UNRESOLVED_REFERENCE:{raw_ref}")
        else:
            resolved.append(item)
    return resolved, blockers
