"""Immutable input contracts for pure Workspace-to-view projections.

The objects in this module are read models of the actual authorities.  They do
not persist a page DTO and they deliberately contain no generic project-shaped
document.  Callers must provide exact revision selections and target versions.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Mapping
from urllib.parse import quote

from .errors import ProjectionInputError

_TEXT_SUFFIXES = frozenset({".md", ".txt", ".ref", ".vtt", ".ctm"})


def _immutable_map(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _non_empty(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ProjectionInputError(f"{label} is required")
    return normalized


@dataclass(frozen=True, slots=True)
class WorkspaceFile:
    content: str
    object_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_version", _non_empty(self.object_version, "object_version"))


@dataclass(frozen=True, slots=True)
class TextWorkspaceSnapshot:
    """A materialized immutable revision or working-tree snapshot."""

    project_id: str
    revision_id: str
    files: Mapping[str, WorkspaceFile]
    target_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _non_empty(self.project_id, "project_id"))
        object.__setattr__(self, "revision_id", _non_empty(self.revision_id, "revision_id"))
        checked: dict[str, WorkspaceFile] = {}
        for raw_path, entry in self.files.items():
            path = PurePosixPath(str(raw_path))
            if (
                path.is_absolute()
                or not path.parts
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.suffix not in _TEXT_SUFFIXES
            ):
                raise ProjectionInputError(f"invalid Text Workspace path: {raw_path!r}")
            if not isinstance(entry, WorkspaceFile):
                raise ProjectionInputError(f"file entry must be WorkspaceFile: {raw_path!r}")
            checked[path.as_posix()] = entry
        versions = {str(ref): _non_empty(version, f"target version for {ref}") for ref, version in self.target_versions.items()}
        object.__setattr__(self, "files", MappingProxyType(dict(sorted(checked.items()))))
        object.__setattr__(self, "target_versions", MappingProxyType(dict(sorted(versions.items()))))

    def text(self, path: str, *, required: bool = False) -> str:
        entry = self.files.get(path)
        if entry is None:
            if required:
                raise ProjectionInputError(f"required Workspace file is missing: {path}")
            return ""
        return entry.content.strip()

    def target_version(self, target_ref: str) -> str:
        try:
            return self.target_versions[target_ref]
        except KeyError as exc:
            raise ProjectionInputError(f"target version is missing: {target_ref}") from exc

    def paths(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(path for path in self.files if path.startswith(prefix))


@dataclass(frozen=True, slots=True)
class ProjectPresentationMetadata:
    scenario: Literal["short_drama", "video_edit", "general"]
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class AssetVersionRecord:
    id: str
    logical_asset_id: str
    name: str
    checksum: str
    media_type: Literal["image", "video", "audio", "doc", "text"]
    url: str
    created_at: str
    provenance_refs: tuple[str, ...] = ()
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    object_version: str = ""
    native_model_url: str | None = None

    def __post_init__(self) -> None:
        for label in ("id", "logical_asset_id", "name", "checksum", "url", "created_at", "object_version"):
            _non_empty(str(getattr(self, label)), label)

    @property
    def source_ref(self) -> str:
        return f"asset://{quote(self.logical_asset_id, safe='')}@{quote(self.id, safe='')}"


@dataclass(frozen=True, slots=True)
class ArtifactVersionRecord:
    id: str
    slot_id: str
    kind: str
    owner_ref: str
    name: str
    url: str
    checksum: str
    created_at: str
    based_on_revision_id: str
    provenance_refs: tuple[str, ...] = ()
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    input_fingerprint: str | None = None
    stale: bool = False
    stale_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in (
            "id",
            "slot_id",
            "kind",
            "owner_ref",
            "name",
            "url",
            "checksum",
            "created_at",
            "based_on_revision_id",
        ):
            _non_empty(str(getattr(self, label)), label)
        object.__setattr__(self, "metadata", _immutable_map(self.metadata))

    @property
    def source_ref(self) -> str:
        return f"artifact://{quote(self.slot_id, safe='')}@{quote(self.id, safe='')}"


@dataclass(frozen=True, slots=True)
class ProjectionCatalogs:
    assets: tuple[AssetVersionRecord, ...] = ()
    artifacts: tuple[ArtifactVersionRecord, ...] = ()

    def asset_version(self, version_id: str) -> AssetVersionRecord | None:
        return next((item for item in self.assets if item.id == version_id), None)

    def artifact_version(self, version_id: str) -> ArtifactVersionRecord | None:
        return next((item for item in self.artifacts if item.id == version_id), None)

    def artifact_versions_for_slot(self, slot_id: str) -> tuple[ArtifactVersionRecord, ...]:
        return tuple(item for item in self.artifacts if item.slot_id == slot_id)


@dataclass(frozen=True, slots=True)
class RevisionSelections:
    revision_id: str
    artifact_versions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", _non_empty(self.revision_id, "revision_id"))
        values = {str(slot): _non_empty(version, f"selection for {slot}") for slot, version in self.artifact_versions.items()}
        object.__setattr__(self, "artifact_versions", MappingProxyType(dict(sorted(values.items()))))


@dataclass(frozen=True, slots=True)
class ProviderConstraintSnapshot:
    provider: str
    model: str
    version: str
    captured_at: str
    min_duration: float
    max_duration: float
    max_reference_images: int
    allowed_durations: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        for label in ("provider", "model", "version", "captured_at"):
            _non_empty(str(getattr(self, label)), label)
        if self.min_duration <= 0 or self.max_duration < self.min_duration:
            raise ProjectionInputError("invalid provider duration bounds")
        if self.max_reference_images < 1:
            raise ProjectionInputError("max_reference_images must be positive")


@dataclass(frozen=True, slots=True)
class AiEditPlanVersion:
    id: str
    unit_id: str
    checksum: str
    created_at: str
    workbench_envelope: Mapping[str, Any]

    def __post_init__(self) -> None:
        for label in ("id", "unit_id", "checksum", "created_at"):
            _non_empty(str(getattr(self, label)), label)
        object.__setattr__(self, "workbench_envelope", _immutable_map(deepcopy(dict(self.workbench_envelope))))

    @property
    def source_ref(self) -> str:
        return f"ai-edit-plan://{quote(self.unit_id, safe='')}@{quote(self.id, safe='')}"


@dataclass(frozen=True, slots=True)
class IngestItemRecord:
    task_id: str
    asset_id: str | None
    asset_version_id: str | None
    name: str
    status: str
    progress: float | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ManualEditOverlayRecord:
    id: str
    head: str
    mutation_count: int

    def __post_init__(self) -> None:
        _non_empty(self.id, "overlay id")
        _non_empty(self.head, "overlay head")
        if self.mutation_count < 0:
            raise ProjectionInputError("overlay mutation_count cannot be negative")

    def to_view(self) -> dict[str, Any]:
        return {"id": self.id, "head": self.head, "mutationCount": self.mutation_count}


@dataclass(frozen=True, slots=True)
class RuntimeViewState:
    project_id: str
    approved_revision_id: str
    session_status: str
    transaction_status: str | None
    agent_status_bar: Mapping[str, Any]
    working_branch_id: str | None = None
    working_head: str | None = None
    review_revision_id: str | None = None
    active_transaction_id: str | None = None
    manual_edit_overlay: ManualEditOverlayRecord | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _non_empty(self.project_id, "project_id"))
        object.__setattr__(self, "approved_revision_id", _non_empty(self.approved_revision_id, "approved_revision_id"))
        object.__setattr__(self, "session_status", _non_empty(self.session_status, "session_status"))
        object.__setattr__(self, "agent_status_bar", _immutable_map(deepcopy(dict(self.agent_status_bar))))


ReviewOrigin = Literal["approved", "review_candidate", "user_overlay"]


@dataclass(frozen=True, slots=True)
class ReviewTargetMetadata:
    target_version: str
    decision_group_id: str | None = None
    decision_token: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.target_version, "review target version")
        if (self.decision_group_id is None) != (self.decision_token is None):
            raise ProjectionInputError("decision group id and token must be supplied together")

    def to_view(self) -> dict[str, str]:
        result = {"targetVersion": self.target_version}
        if self.decision_group_id is not None:
            result["decisionGroupId"] = self.decision_group_id
            result["decisionToken"] = self.decision_token or ""
        return result


@dataclass(frozen=True, slots=True)
class ReviewPresentationState:
    presentation_version: str
    review_revision_id: str
    approved_revision_id: str
    origins: Mapping[str, ReviewOrigin]
    target_versions: Mapping[str, ReviewTargetMetadata]
    overlay_id: str | None = None
    overlay_head: str | None = None

    def __post_init__(self) -> None:
        for label in ("presentation_version", "review_revision_id", "approved_revision_id"):
            _non_empty(str(getattr(self, label)), label)
        if (self.overlay_id is None) != (self.overlay_head is None):
            raise ProjectionInputError("overlay id and head must be supplied together")
        origin_map = dict(self.origins)
        target_map = dict(self.target_versions)
        if set(origin_map) != set(target_map):
            raise ProjectionInputError("review origins and target versions must address the same targets")
        for target_ref, origin in origin_map.items():
            if origin not in {"approved", "review_candidate", "user_overlay"}:
                raise ProjectionInputError(f"invalid review origin for {target_ref}")
            metadata = target_map[target_ref]
            if origin == "review_candidate" and metadata.decision_group_id is None:
                raise ProjectionInputError(f"review candidate is missing decision CAS metadata: {target_ref}")
            if origin == "user_overlay" and self.overlay_id is None:
                raise ProjectionInputError(f"overlay origin is missing overlay metadata: {target_ref}")
        object.__setattr__(self, "origins", MappingProxyType(dict(sorted(origin_map.items()))))
        object.__setattr__(self, "target_versions", MappingProxyType(dict(sorted(target_map.items()))))


@dataclass(frozen=True, slots=True)
class ProjectionSnapshots:
    approved: TextWorkspaceSnapshot
    working: TextWorkspaceSnapshot | None = None
    review_presentation: TextWorkspaceSnapshot | None = None
