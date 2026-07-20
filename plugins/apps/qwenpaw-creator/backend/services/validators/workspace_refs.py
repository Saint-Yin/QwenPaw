# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=too-many-boolean-expressions,too-many-branches
# pylint: disable=too-many-statements
"""Exact, Project-scoped Workspace reference validation for the seal boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from services.format_layer.inputs import TextWorkspaceSnapshot

from .base import ValidationIssue, ValidationReport


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceAuthority:
    asset_versions: Mapping[str, str] = field(default_factory=dict)
    artifact_versions: Mapping[str, str] = field(default_factory=dict)
    artifact_slots: frozenset[str] = frozenset()
    analysis_versions: Mapping[str, tuple[str, frozenset[str]]] = field(
        default_factory=dict,
    )
    ai_edit_plan_versions: Mapping[str, str] = field(default_factory=dict)


def _issue(code: str, message: str, path: str) -> ValidationIssue:
    return ValidationIssue(code, message, path)


def validate_exact_workspace_references(
    snapshot: TextWorkspaceSnapshot,
    authority: WorkspaceReferenceAuthority,
    *,
    section_ids: frozenset[str],
    unit_ids: frozenset[str],
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    for path in snapshot.paths():
        if not path.endswith(".ref"):
            continue
        raw = snapshot.text(path, required=True)
        parsed = urlparse(raw)
        if parsed.scheme == "asset":
            if (
                "@" not in parsed.netloc
                or parsed.path
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                issues.append(
                    _issue(
                        "REFERENCE_NOT_EXACT",
                        "Asset ref 必须包含 logical id 与不可变 version id",
                        path,
                    ),
                )
                continue
            logical_id, version_id = (
                unquote(item) for item in parsed.netloc.rsplit("@", 1)
            )
            if authority.asset_versions.get(version_id) != logical_id:
                issues.append(
                    _issue(
                        "DANGLING_REFERENCE",
                        "AssetVersion 不存在或 logical id 不匹配",
                        path,
                    ),
                )
            continue

        if parsed.scheme == "artifact":
            if (
                "@" not in parsed.netloc
                or parsed.path
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                issues.append(
                    _issue(
                        "REFERENCE_NOT_EXACT",
                        "Artifact ref 必须包含 Slot 与不可变 version id",
                        path,
                    ),
                )
                continue
            slot_id, version_id = (
                unquote(item) for item in parsed.netloc.rsplit("@", 1)
            )
            if authority.artifact_versions.get(version_id) != slot_id:
                issues.append(
                    _issue(
                        "DANGLING_REFERENCE",
                        "ArtifactVersion 不存在或 Slot 不匹配",
                        path,
                    ),
                )
            continue

        if parsed.scheme == "analysis":
            fragment = parse_qs(parsed.fragment, keep_blank_values=True)
            fragment_valid = not parsed.fragment or (
                set(fragment) == {"shot"}
                and len(fragment["shot"]) == 1
                and bool(fragment["shot"][0])
            )
            if (
                "@" not in parsed.netloc
                or parsed.path
                or parsed.params
                or parsed.query
                or not fragment_valid
            ):
                issues.append(
                    _issue(
                        "REFERENCE_NOT_EXACT",
                        "Analysis ref 必须包含 AssetVersion 与 analysis version",
                        path,
                    ),
                )
                continue
            asset_version_id, analysis_version_id = (
                unquote(item) for item in parsed.netloc.rsplit("@", 1)
            )
            analysis = authority.analysis_versions.get(analysis_version_id)
            if (
                asset_version_id not in authority.asset_versions
                or analysis is None
                or analysis[0] != "SUCCEEDED"
                or asset_version_id not in analysis[1]
            ):
                issues.append(
                    _issue(
                        "DANGLING_REFERENCE",
                        "Source Intelligence version 不存在或未绑定当前素材版本",
                        path,
                    ),
                )
            continue

        if parsed.scheme == "ai-edit-plan":
            if (
                "@" not in parsed.netloc
                or parsed.path
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                issues.append(
                    _issue(
                        "REFERENCE_NOT_EXACT",
                        "AI Edit Plan ref 必须包含 Unit 与不可变 version id",
                        path,
                    ),
                )
                continue
            unit_id, version_id = (
                unquote(item) for item in parsed.netloc.rsplit("@", 1)
            )
            if authority.ai_edit_plan_versions.get(version_id) != unit_id:
                issues.append(
                    _issue(
                        "DANGLING_REFERENCE",
                        "AI Edit Plan Version 不存在或 Unit 不匹配",
                        path,
                    ),
                )
            continue

        if parsed.scheme == "project":
            identifier = unquote(parsed.path.strip("/"))
            if (
                parsed.netloc not in {"section", "unit"}
                or not identifier
                or "/" in identifier
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                issues.append(
                    _issue(
                        "REFERENCE_NOT_EXACT",
                        "Project ref 必须是具体 section/unit",
                        path,
                    ),
                )
                continue
            known = section_ids if parsed.netloc == "section" else unit_ids
            if identifier not in known:
                issues.append(
                    _issue(
                        "DANGLING_REFERENCE",
                        "Project entity ref 指向不存在对象",
                        path,
                    ),
                )
            continue

        issues.append(
            _issue(
                "REFERENCE_SCHEME_UNSUPPORTED",
                f"不支持的 Workspace ref scheme: {parsed.scheme}",
                path,
            ),
        )
    return ValidationReport.from_iterable(issues)


def analysis_authority_from_source_run(
    status: str,
    target_refs: Any,
    read_set: Any,
    asset_versions: Mapping[str, str],
) -> tuple[str, frozenset[str]]:
    """Derive exact analysis authority from a terminal Source SpecialistRun.

    The immutable analysis version id is the Source ``runId``.  Only exact
    AssetVersions whose logical id matches that Run's admitted ``asset:``
    target and whose exact id is recorded in the Runtime-owned native-media
    read-set may be authorized; a task result or the downstream ref being
    validated is never trusted as authority.
    """

    targets = tuple(str(item) for item in target_refs or ())
    logical_ids = {
        item.removeprefix("asset:")
        for item in targets
        if item.startswith("asset:") and not item.startswith("asset://")
    }
    if status != "SUCCEEDED":
        return status, frozenset()
    valid: set[str] = set()
    for item in read_set or ():
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref") or "")
        version_id = str(item.get("objectVersion") or "")
        if (
            ref.startswith("asset:")
            and not ref.startswith("asset://")
            and ref.removeprefix("asset:") in logical_ids
            and asset_versions.get(version_id) == ref.removeprefix("asset:")
        ):
            valid.add(version_id)
    return status, frozenset(valid)


__all__ = [
    "WorkspaceReferenceAuthority",
    "analysis_authority_from_source_run",
    "validate_exact_workspace_references",
]
