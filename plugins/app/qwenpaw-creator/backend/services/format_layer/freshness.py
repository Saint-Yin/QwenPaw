"""Shared deterministic input fingerprints for View and execution freshness."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from services.media.source_intelligence import parse_source_intelligence_files

from .inputs import (
    ProjectPresentationMetadata,
    ProjectionCatalogs,
    TextWorkspaceSnapshot,
)
from .parsing import find_unit, parse_sections


def canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _asset_identity(raw: str) -> tuple[str, str] | None:
    parsed = urlparse(raw)
    if parsed.scheme != "asset" or "@" not in parsed.netloc:
        return None
    logical_id, version_id = (unquote(value) for value in parsed.netloc.rsplit("@", 1))
    return (logical_id, version_id) if logical_id and version_id else None


def _analysis_identity(raw: str) -> tuple[str, str] | None:
    parsed = urlparse(raw)
    if (
        parsed.scheme != "analysis"
        or "@" not in parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    asset_version_id, analysis_version_id = (
        unquote(value) for value in parsed.netloc.rsplit("@", 1)
    )
    if not asset_version_id or not analysis_version_id:
        return None
    return asset_version_id, analysis_version_id


def _source_intelligence_payloads(
    snapshot: TextWorkspaceSnapshot,
) -> tuple[dict[str, Any], ...]:
    """Project validated analysis text, never native media, into AI Edit input."""

    payloads: list[dict[str, Any]] = []
    for current_path in sorted(
        path
        for path in snapshot.paths("sources/")
        if path.endswith("/understanding/current.ref")
    ):
        analysis_ref = snapshot.text(current_path)
        identity = _analysis_identity(analysis_ref)
        if identity is None:
            continue
        asset_version_id, analysis_version_id = identity
        source_root = current_path.removesuffix("/understanding/current.ref")
        version_root = f"{source_root}/understanding/versions/{analysis_version_id}/"
        files = {
            path.removeprefix(version_root): snapshot.files[path].content
            for path in snapshot.paths(version_root)
        }
        index = parse_source_intelligence_files(files)
        if (
            index.id != analysis_version_id
            or index.asset_version_id != asset_version_id
        ):
            continue
        raw = index.model_dump(mode="json", by_alias=True, exclude_none=True)
        payloads.append(
            {
                "analysisRef": analysis_ref,
                "analysisVersionId": analysis_version_id,
                "assetId": index.asset_id,
                "assetVersionId": index.asset_version_id,
                "sourceChecksum": index.source_checksum,
                "summary": index.summary,
                "media": raw["media"],
                "coverage": raw["coverage"],
                "modelRuns": raw["modelRuns"],
                "transcript": raw["transcript"],
                "semanticEntries": raw["semanticEntries"],
            }
        )
    return tuple(payloads)


def ai_edit_project_payload(
    snapshot: TextWorkspaceSnapshot,
    catalogs: ProjectionCatalogs,
    project_metadata: ProjectPresentationMetadata | None = None,
) -> dict[str, Any]:
    """Build the exact frozen-core project payload used by the service runner."""

    sections = parse_sections(snapshot)
    source_intelligence = _source_intelligence_payloads(snapshot)
    intelligence_by_version = {
        item["assetVersionId"]: item for item in source_intelligence
    }
    assets = [
        {
            "id": item.logical_asset_id,
            "versionId": item.id,
            "name": item.name,
            "mediaType": item.media_type,
            "url": item.url,
            "nativeModelUrl": item.native_model_url,
            "duration": item.duration_seconds,
            "category": "upload",
            **(
                {"sourceIntelligence": intelligence_by_version[item.id]}
                if item.id in intelligence_by_version
                else {}
            ),
        }
        for item in sorted(
            catalogs.assets,
            key=lambda value: (value.logical_asset_id, value.id),
        )
    ]
    return {
        "id": snapshot.project_id,
        "title": snapshot.text("title.txt"),
        "description": snapshot.text("description.md"),
        "scenario": project_metadata.scenario if project_metadata else None,
        "contentType": project_metadata.content_type if project_metadata else None,
        "plan": {
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "summary": section.summary,
                    "narrative": section.narrative,
                    "script": section.script,
                    "duration": section.duration_budget,
                    "units": [
                        {
                            "id": unit.id,
                            "title": unit.title,
                            "taskType": unit.route,
                            "duration": unit.duration,
                            "narrative": unit.narrative,
                            "continuity": unit.continuity,
                            "materialRefs": [
                                identity[0]
                                for _path, raw in unit.refs
                                if (identity := _asset_identity(raw)) is not None
                            ],
                            "materialVersionRefs": [
                                identity[1]
                                for _path, raw in unit.refs
                                if (identity := _asset_identity(raw)) is not None
                            ],
                            "analysisRefs": [
                                raw
                                for path, raw in unit.refs
                                if path == "source-analysis.ref"
                                and _analysis_identity(raw) is not None
                            ],
                            # Edit Shots are optional pre-plan editorial beats.
                            # They guide semantic clip selection but never
                            # replace the immutable AI Edit Plan timeline.
                            "shots": [
                                {
                                    "id": shot.id,
                                    "description": shot.description,
                                    "duration": shot.duration,
                                    "camera": shot.camera,
                                    "framing": shot.framing,
                                }
                                for shot in unit.shots
                            ],
                        }
                        for unit in section.units
                    ],
                }
                for section in sections
            ]
        },
        "assets": assets,
        "sourceIntelligence": list(source_intelligence),
    }


def ai_edit_execute_fingerprint(
    snapshot: TextWorkspaceSnapshot,
    catalogs: ProjectionCatalogs,
    *,
    unit_id: str,
    plan: Mapping[str, Any],
    project_metadata: ProjectPresentationMetadata | None = None,
) -> str:
    # Kept byte-for-byte equivalent to media.ai_edit_bridge's frozen hash
    # payload while avoiding a Format Layer -> execution-service dependency.
    find_unit(parse_sections(snapshot), unit_id)
    return canonical_json_hash(
        {
            "project": ai_edit_project_payload(
                snapshot,
                catalogs,
                project_metadata,
            ),
            "unitId": unit_id,
            "plan": dict(plan),
        }
    )


__all__ = [
    "ai_edit_execute_fingerprint",
    "ai_edit_project_payload",
    "canonical_json_hash",
]
