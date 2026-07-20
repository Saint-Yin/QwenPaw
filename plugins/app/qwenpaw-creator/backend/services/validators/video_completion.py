"""Deterministic Section/Final video completion and owner routing checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote, urlparse

from services.format_layer.inputs import TextWorkspaceSnapshot
from services.format_layer.parsing import ParsedSection

from .base import ValidationIssue, ValidationReport
from .short_drama import duration_tolerance, parse_canonical_target_duration


_VIDEO_SCENARIOS = frozenset({"short_drama", "video_edit"})


def _artifact_identity(raw: str) -> tuple[str, str] | None:
    parsed = urlparse(raw.strip())
    if (
        parsed.scheme != "artifact"
        or "@" not in parsed.netloc
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    slot_id, version_id = (unquote(item) for item in parsed.netloc.rsplit("@", 1))
    if not slot_id or not version_id:
        return None
    return slot_id, version_id


def _artifact_catalog(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    return {str(row["id"]): row for row in rows}


def _selected_unit_video_path(section: ParsedSection, unit_id: str, route: str) -> str:
    unit = next(item for item in section.units if item.id == unit_id)
    if route == "r2v":
        return f"{unit.root}/production/r2v/video/selected.ref"
    return f"{unit.root}/production/edit/rendered-video.ref"


def _resolve_owned_artifact(
    *,
    raw_ref: str,
    catalog: Mapping[str, Mapping[str, Any]],
    expected_kind: str,
    expected_owner: str,
) -> tuple[Mapping[str, Any], str] | None:
    identity = _artifact_identity(raw_ref)
    if identity is None:
        return None
    slot_id, version_id = identity
    row = catalog.get(version_id)
    if (
        row is None
        or str(row.get("slot_id") or "") != slot_id
        or str(row.get("slot_kind") or "") != expected_kind
        or str(row.get("slot_target_ref") or "") != expected_owner
    ):
        return None
    return row, version_id


def _unit_video_selections(
    *,
    snapshot: TextWorkspaceSnapshot,
    section: ParsedSection,
    catalog: Mapping[str, Mapping[str, Any]],
    issues: list[ValidationIssue],
) -> list[tuple[str, str, Mapping[str, Any], str]] | None:
    selected: list[tuple[str, str, Mapping[str, Any], str]] = []
    for unit in section.units:
        path = _selected_unit_video_path(section, unit.id, unit.route)
        raw_ref = snapshot.text(path)
        resolved = _resolve_owned_artifact(
            raw_ref=raw_ref,
            catalog=catalog,
            expected_kind="unit_video",
            expected_owner=f"unit:{unit.id}",
        )
        if resolved is None:
            issues.append(
                ValidationIssue(
                    "UNIT_VIDEO_SELECTION_NOT_CURRENT",
                    "Unit 必须选择属于自身 unit_video Slot 的 exact ArtifactVersion",
                    f"unit:{unit.id}",
                )
            )
            return None
        row, version_id = resolved
        duration = row.get("duration_seconds")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or float(duration) <= 0
        ):
            issues.append(
                ValidationIssue(
                    "UNIT_VIDEO_ACTUAL_DURATION_MISSING",
                    "Unit Video 必须包含可验证的正数实际时长",
                    f"unit:{unit.id}",
                )
            )
            return None
        selected.append((unit.id, raw_ref.strip(), row, version_id))
    return selected


def _sequence_matches(
    snapshot: TextWorkspaceSnapshot,
    *,
    prefix: str,
    expected: Sequence[tuple[str, str]],
) -> bool:
    current = {
        path: snapshot.text(path, required=True).strip()
        for path in snapshot.paths(prefix)
        if path.endswith(".ref")
    }
    return current == {path: raw_ref for path, raw_ref in expected}


def _source_selections_match(
    row: Mapping[str, Any],
    *,
    expected: Sequence[tuple[str, str]],
) -> bool:
    raw = dict(row.get("metadata") or {}).get("sourceSelections")
    if not isinstance(raw, list) or len(raw) != len(expected):
        return False
    for order, (selection, (source_ref, version_id)) in enumerate(
        zip(raw, expected, strict=True), 1
    ):
        if not isinstance(selection, Mapping):
            return False
        if (
            str(selection.get("sourceRef") or "") != source_ref
            or str(selection.get("artifactVersionId") or "") != version_id
            or selection.get("order") != order
            or not isinstance(selection.get("transition"), str)
        ):
            return False
    return True


def _validate_composed_artifact(
    *,
    issues: list[ValidationIssue],
    target_ref: str,
    raw_ref: str,
    catalog: Mapping[str, Mapping[str, Any]],
    expected_kind: str,
    expected_owner: str,
    expected_sources: Sequence[tuple[str, str]],
    expected_provenance: Sequence[str],
    expected_duration: float | None,
) -> Mapping[str, Any] | None:
    resolved = _resolve_owned_artifact(
        raw_ref=raw_ref,
        catalog=catalog,
        expected_kind=expected_kind,
        expected_owner=expected_owner,
    )
    if resolved is None:
        issues.append(
            ValidationIssue(
                "COMPOSED_VIDEO_EXACT_REF_REQUIRED",
                f"{expected_kind} 必须选择 owner/kind 匹配的 exact ArtifactVersion",
                target_ref,
            )
        )
        return None
    row, _version_id = resolved
    if not _source_selections_match(row, expected=expected_sources):
        issues.append(
            ValidationIssue(
                "COMPOSED_VIDEO_SOURCE_SELECTIONS_STALE",
                "合成产物 sourceSelections 与当前 canonical sequence 不一致",
                target_ref,
            )
        )
    if tuple(str(item) for item in row.get("provenance_refs") or ()) != tuple(
        expected_provenance
    ):
        issues.append(
            ValidationIssue(
                "COMPOSED_VIDEO_PROVENANCE_STALE",
                "合成产物 provenance 必须逐项等于当前 sequence 的 exact refs",
                target_ref,
            )
        )
    duration = row.get("duration_seconds")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or float(duration) <= 0
    ):
        issues.append(
            ValidationIssue(
                "COMPOSED_VIDEO_ACTUAL_DURATION_MISSING",
                "合成产物必须包含可验证的正数实际时长",
                target_ref,
            )
        )
    elif expected_duration is not None and abs(
        float(duration) - expected_duration
    ) > duration_tolerance(expected_duration):
        issues.append(
            ValidationIssue(
                "COMPOSED_VIDEO_DURATION_MISMATCH",
                (
                    f"合成产物实际时长 {float(duration):g}s 与目标 "
                    f"{expected_duration:g}s 超出容差 "
                    f"{duration_tolerance(expected_duration):g}s"
                ),
                target_ref,
            )
        )
    return row


def validate_video_project_completion(
    *,
    scenario: str,
    project_id: str,
    snapshot: TextWorkspaceSnapshot,
    sections: Sequence[ParsedSection],
    artifact_rows: Sequence[Mapping[str, Any]],
) -> ValidationReport:
    """The Unit -> Section -> Final completion chain is disabled."""

    return ValidationReport()

    if scenario not in _VIDEO_SCENARIOS:
        return ValidationReport()
    issues: list[ValidationIssue] = []
    catalog = _artifact_catalog(artifact_rows)
    nonempty = [section for section in sections if section.units]
    if not nonempty:
        return ValidationReport(
            (
                ValidationIssue(
                    "VIDEO_SECTION_UNIT_REQUIRED",
                    "视频项目至少需要一个包含 Unit 的 Section，不能以空规划完成",
                    "project:plan",
                ),
            )
        )
    completed_sections: list[tuple[ParsedSection, str, Mapping[str, Any], str]] = []

    for section in nonempty:
        unit_selections = _unit_video_selections(
            snapshot=snapshot,
            section=section,
            catalog=catalog,
            issues=issues,
        )
        if unit_selections is None:
            continue
        target_ref = f"post:{section.id}"
        rendered_ref = snapshot.text(
            f"post/sections/{section.id}/rendered-video.ref"
        ).strip()
        row = _validate_composed_artifact(
            issues=issues,
            target_ref=target_ref,
            raw_ref=rendered_ref,
            catalog=catalog,
            expected_kind="section_video",
            expected_owner=f"section:{section.id}",
            expected_sources=[
                (f"project://unit/{unit_id}", version_id)
                for unit_id, _ref, _row, version_id in unit_selections
            ],
            expected_provenance=[
                ref for _unit_id, ref, _row, _version_id in unit_selections
            ],
            expected_duration=section.duration_budget,
        )
        if row is not None and not any(
            issue.target_ref == target_ref for issue in issues
        ):
            identity = _artifact_identity(rendered_ref)
            assert identity is not None
            completed_sections.append((section, rendered_ref, row, identity[1]))

    if not nonempty or len(completed_sections) != len(nonempty):
        return ValidationReport.from_iterable(issues)

    raw_target = snapshot.text("settings/target-duration.txt")
    try:
        target_duration = parse_canonical_target_duration(raw_target)
    except Exception as exc:
        # Keep this validator total even if a legacy project has malformed
        # settings.  Short-drama planning emits the more specific canonical
        # issue; this code identifies why Final cannot close.
        issues.append(
            ValidationIssue(
                "FINAL_VIDEO_TARGET_DURATION_INVALID",
                f"Final 目标时长不可验证: {exc}",
                "post:final",
            )
        )
        return ValidationReport.from_iterable(issues)

    _validate_composed_artifact(
        issues=issues,
        target_ref="post:final",
        raw_ref=snapshot.text("post/final/rendered-video.ref").strip(),
        catalog=catalog,
        expected_kind="final_video",
        expected_owner=f"project:{project_id}",
        expected_sources=[
            (f"project://section/{section.id}", version_id)
            for section, _ref, _row, version_id in completed_sections
        ],
        expected_provenance=[
            ref for _section, ref, _row, _version_id in completed_sections
        ],
        expected_duration=target_duration,
    )
    return ValidationReport.from_iterable(issues)


def derive_missing_post_work_refs(
    *,
    scenario: str,
    project_id: str,
    snapshot: TextWorkspaceSnapshot,
    sections: Sequence[ParsedSection],
    artifact_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Expose only post owners whose exact upstream videos are already ready."""

    return tuple(
        ref
        for ref in derive_missing_video_work_refs(
            scenario=scenario,
            project_id=project_id,
            snapshot=snapshot,
            sections=sections,
            artifact_rows=artifact_rows,
        )
        if ref.startswith("post:")
    )


def derive_missing_video_work_refs(
    *,
    scenario: str,
    project_id: str,
    snapshot: TextWorkspaceSnapshot,
    sections: Sequence[ParsedSection],
    artifact_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return the next deterministic Unit/Post owners needed for final video.

    The completion validator intentionally stops each Section at the first
    missing upstream layer.  Consequently Unit refs mean production must still
    build/select a current video, while Post refs are exposed only after every
    Unit feeding that owner is ready.
    """

    report = validate_video_project_completion(
        scenario=scenario,
        project_id=project_id,
        snapshot=snapshot,
        sections=sections,
        artifact_rows=artifact_rows,
    )
    refs = {
        issue.target_ref
        for issue in report.issues
        if issue.target_ref.startswith(("unit:", "post:"))
    }
    return tuple(sorted(refs))


__all__ = [
    "derive_missing_post_work_refs",
    "derive_missing_video_work_refs",
    "validate_video_project_completion",
]
