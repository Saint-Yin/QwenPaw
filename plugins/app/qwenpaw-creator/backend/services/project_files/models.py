"""Pydantic authority for Creator's single-file Project domain model.

The models in this module deliberately contain no SQLite or HTTP concerns.
They describe only the durable contents of one Project's ``project.json``.
Runtime state (tasks, reviews, locks and change sets) belongs under the
Project's ``runtime/`` directory and must not be added here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
from typing import Annotated, Any, Generic, Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


CURRENT_PROJECT_SCHEMA_VERSION = 1
SHA256_PATTERN = r"^[a-f0-9]{64}$"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]
EntityId = Annotated[
    str,
    Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, Field(pattern=SHA256_PATTERN)]


class StrictModel(BaseModel):
    """Base for persisted models: unknown fields are storage corruption."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_default=True,
        validate_assignment=True,
    )


T = TypeVar("T", bound=StrictModel)


class EntityCollection(StrictModel, Generic[T]):
    """Stable-ID collection with explicit presentation order."""

    items: dict[EntityId, T] = Field(default_factory=dict)
    order: list[EntityId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_order(self) -> EntityCollection[T]:
        if len(self.order) != len(set(self.order)):
            raise ValueError("order contains duplicate ids")
        if set(self.order) != set(self.items):
            raise ValueError("order must contain every item id exactly once")
        return self


class ProviderModelScope(StrictModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ExecutionPreauthorization(StrictModel):
    max_cost: float = Field(ge=0)
    max_candidates: int = Field(ge=1)
    provider_models: list[ProviderModelScope] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_models(self) -> ExecutionPreauthorization:
        pairs = [(item.provider, item.model) for item in self.provider_models]
        if len(pairs) != len(set(pairs)):
            raise ValueError("provider/model scope cannot be duplicated")
        return self


class ProjectSettings(StrictModel):
    aspect_ratio: str = "16:9"
    resolution: str = "720P"
    platform: str = ""
    language: str = "zh-CN"
    target_duration_seconds: float | None = Field(default=None, ge=0)
    content_type: str | None = None
    execution_preauthorization: ExecutionPreauthorization | None = None


class CreativeStrategy(StrictModel):
    creative_brief: str = ""
    audience: str = ""
    creative_direction: str = ""
    constraints: str = ""
    success_criteria: str = ""


class IndexedFile(StrictModel):
    file_id: EntityId
    kind: Literal[
        "source_original",
        "source_thumbnail",
        "source_intelligence",
        "artifact_payload",
        "artifact_thumbnail",
        "large_text",
        "model_native",
        "other",
    ]
    relative_uri: str
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1)
    schema_name: str | None = None
    schema_version: int | None = Field(default=None, ge=1)
    created_at: UtcDateTime

    @field_validator("relative_uri")
    @classmethod
    def _validate_relative_uri(cls, value: str) -> str:
        if not value or value != value.strip() or "\\" in value or "\x00" in value:
            raise ValueError("relative_uri must be a normalized POSIX path")
        path = PurePosixPath(value)
        if path.is_absolute() or len(path.parts) < 2 or path.parts[0] != "assets":
            raise ValueError("relative_uri must be relative to the Project assets directory")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("relative_uri cannot contain traversal segments")
        return path.as_posix()


class IndexedContentRef(StrictModel):
    file_id: EntityId


class SourceAssetVersion(StrictModel):
    version_id: EntityId
    logical_asset_id: EntityId
    name: str
    file_id: EntityId | None = None
    checksum: Sha256
    media_kind: Literal["image", "video", "audio", "document", "text", "other"]
    media_type: str = Field(min_length=1)
    provenance_refs: list[str] = Field(default_factory=list)
    thumbnail_file_id: EntityId | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    native_model_file_id: EntityId | None = None
    created_at: UtcDateTime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_location(self) -> SourceAssetVersion:
        if self.file_id is not None:
            return self
        source_url = str(self.metadata.get("publicSourceUrl") or "").strip()
        parsed = urlsplit(source_url)
        if (
            self.metadata.get("sourceKind") != "remote_url"
            or self.metadata.get("checksumKind") != "source_url_sha256"
            or parsed.scheme not in {"http", "https", "oss"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "source version without file_id must identify a public remote URL"
            )
        if hashlib.sha256(source_url.encode("utf-8")).hexdigest() != self.checksum:
            raise ValueError("remote source checksum must be the public URL fingerprint")
        return self


class SourceIntelligenceVersion(StrictModel):
    intelligence_version_id: EntityId
    source_asset_version_id: EntityId
    file_id: EntityId
    source_checksum: Sha256
    model_run_ids: list[EntityId] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    created_at: UtcDateTime


class ArtifactSlot(StrictModel):
    slot_id: EntityId
    kind: str
    owner_ref: str
    version_ids: list[EntityId] = Field(default_factory=list)
    selected_version_id: EntityId | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version_ids")
    @classmethod
    def _validate_unique_versions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("artifact slot version_ids cannot contain duplicates")
        return value


class ArtifactVersion(StrictModel):
    version_id: EntityId
    slot_id: EntityId
    kind: str
    owner_ref: str
    name: str
    file_id: EntityId
    checksum: Sha256
    based_on_generation: int = Field(ge=0)
    provenance_refs: list[str] = Field(default_factory=list)
    thumbnail_file_id: EntityId | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    input_fingerprint: str | None = None
    stale: bool = False
    stale_reason: str | None = None
    created_at: UtcDateTime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetIndex(StrictModel):
    files_by_id: dict[EntityId, IndexedFile] = Field(default_factory=dict)
    source_versions_by_id: dict[EntityId, SourceAssetVersion] = Field(default_factory=dict)
    intelligence_versions_by_id: dict[EntityId, SourceIntelligenceVersion] = Field(
        default_factory=dict
    )
    artifact_slots_by_id: dict[EntityId, ArtifactSlot] = Field(default_factory=dict)
    artifact_versions_by_id: dict[EntityId, ArtifactVersion] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_index(self) -> AssetIndex:
        _require_mapping_identity(self.files_by_id, "file_id", "files_by_id")
        _require_mapping_identity(
            self.source_versions_by_id,
            "version_id",
            "source_versions_by_id",
        )
        _require_mapping_identity(
            self.intelligence_versions_by_id,
            "intelligence_version_id",
            "intelligence_versions_by_id",
        )
        _require_mapping_identity(self.artifact_slots_by_id, "slot_id", "artifact_slots_by_id")
        _require_mapping_identity(
            self.artifact_versions_by_id,
            "version_id",
            "artifact_versions_by_id",
        )

        for version in self.source_versions_by_id.values():
            if version.file_id is not None:
                payload = _require_key(self.files_by_id, version.file_id, "source file")
                if payload.sha256 != version.checksum:
                    raise ValueError(
                        f"source version checksum does not match file {version.file_id}"
                    )
            for file_id in (version.thumbnail_file_id, version.native_model_file_id):
                if file_id is not None:
                    _require_key(self.files_by_id, file_id, "source auxiliary file")

        for intelligence in self.intelligence_versions_by_id.values():
            source = _require_key(
                self.source_versions_by_id,
                intelligence.source_asset_version_id,
                "source intelligence source version",
            )
            _require_key(self.files_by_id, intelligence.file_id, "source intelligence file")
            if intelligence.source_checksum != source.checksum:
                raise ValueError("source intelligence checksum does not match its source version")

        for version in self.artifact_versions_by_id.values():
            slot = _require_key(self.artifact_slots_by_id, version.slot_id, "artifact slot")
            if version.version_id not in slot.version_ids:
                raise ValueError(f"artifact version {version.version_id} is absent from its slot")
            if version.owner_ref != slot.owner_ref or version.kind != slot.kind:
                raise ValueError(f"artifact version {version.version_id} does not match its slot")
            payload = _require_key(self.files_by_id, version.file_id, "artifact file")
            if payload.sha256 != version.checksum:
                raise ValueError(f"artifact version checksum does not match file {version.file_id}")
            if version.thumbnail_file_id is not None:
                _require_key(self.files_by_id, version.thumbnail_file_id, "artifact thumbnail")

        for slot in self.artifact_slots_by_id.values():
            for version_id in slot.version_ids:
                version = _require_key(
                    self.artifact_versions_by_id,
                    version_id,
                    "artifact slot version",
                )
                if version.slot_id != slot.slot_id:
                    raise ValueError(f"artifact slot {slot.slot_id} contains a foreign version")
            if (
                slot.selected_version_id is not None
                and slot.selected_version_id not in slot.version_ids
            ):
                raise ValueError(
                    f"selected version is not a member of artifact slot {slot.slot_id}"
                )
        return self


class ProjectSource(StrictModel):
    source_id: EntityId
    display_name: str
    logical_asset_id: EntityId
    selected_asset_version_id: EntityId
    current_intelligence_version_id: EntityId | None = None
    user_notes: str = ""


class SourceCatalog(StrictModel):
    sources: EntityCollection[ProjectSource] = Field(default_factory=EntityCollection)


class VisualVariant(StrictModel):
    variant_id: EntityId
    requirements: str = ""
    prompt: str = ""
    reference_asset_version_ids: list[EntityId] = Field(default_factory=list)
    reference_artifact_version_ids: list[EntityId] = Field(default_factory=list)
    generated_artifact_version_ids: list[EntityId] = Field(default_factory=list)


class VisualEntity(StrictModel):
    entity_id: EntityId
    kind: Literal["character", "scene", "prop"]
    name: str = Field(min_length=1)
    description: str = ""
    continuity: str = ""
    variants: EntityCollection[VisualVariant] = Field(default_factory=EntityCollection)
    selected_artifact_version_id: EntityId | None = None


class VisualDevelopment(StrictModel):
    visual_bible: str = ""
    style: str = ""
    entities: EntityCollection[VisualEntity] = Field(default_factory=EntityCollection)


class UnitTaskType(StrEnum):
    R2V = "r2v"
    EDIT = "edit"


class ShotCamera(StrEnum):
    STATIC = "⊙ 静止"
    PUSH_IN = "↑ 推近"
    PULL_OUT = "↓ 拉远"
    PAN_RIGHT = "→ 横摇右"
    PAN_LEFT = "← 横摇左"
    CRANE = "↕ 升降"
    ORBIT = "◎ 环绕"
    HANDHELD = "～ 手持晃动"


class ShotFraming(StrEnum):
    WIDE = "全景"
    MEDIUM = "中景"
    CLOSE = "近景"
    CLOSE_UP = "特写"


class Shot(StrictModel):
    shot_id: EntityId
    description: str = ""
    camera: ShotCamera | None = None
    framing: ShotFraming | None = None
    camera_description: str = ""
    dialogue: str = ""
    duration_seconds: float = Field(ge=0)
    character_refs: list[EntityId] = Field(default_factory=list)
    scene_ref: EntityId | None = None
    prop_refs: list[EntityId] = Field(default_factory=list)


class Unit(StrictModel):
    unit_id: EntityId
    title: str = ""
    route: UnitTaskType
    duration_seconds: float = Field(ge=0)
    narrative: str = ""
    continuity: str = ""
    source_refs: list[EntityId] = Field(default_factory=list)
    character_refs: list[EntityId] = Field(default_factory=list)
    scene_ref: EntityId | None = None
    prop_refs: list[EntityId] = Field(default_factory=list)
    shots: EntityCollection[Shot] = Field(default_factory=EntityCollection)

    @model_validator(mode="after")
    def _validate_shots_for_route(self) -> Unit:
        _require_collection_identity(self.shots, "shot_id", "shots")
        if self.route == UnitTaskType.R2V:
            for shot in self.shots.items.values():
                if shot.camera is None or shot.framing is None:
                    raise ValueError("R2V shot requires camera and framing")
        return self


class Section(StrictModel):
    section_id: EntityId
    title: str = Field(min_length=1)
    summary: str = ""
    narrative: str = ""
    script: str = ""
    voiceover: str = ""
    duration_budget_seconds: float | None = Field(default=None, ge=0)
    pacing: str = ""
    constraints: list[str] = Field(default_factory=list)
    transition: str = ""
    units: EntityCollection[Unit] = Field(default_factory=EntityCollection)

    @model_validator(mode="after")
    def _validate_unit_identity(self) -> Section:
        _require_collection_identity(self.units, "unit_id", "units")
        return self


class Story(StrictModel):
    title: str = ""
    outline: str = ""
    narration: str = ""
    sections: EntityCollection[Section] = Field(default_factory=EntityCollection)

    @model_validator(mode="after")
    def _validate_section_identity(self) -> Story:
        _require_collection_identity(self.sections, "section_id", "sections")
        return self


class GenerationRecipe(StrictModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    seed: int | None = None
    candidate_count: int = Field(default=1, ge=1)


class R2VProduction(StrictModel):
    route: Literal["r2v"] = "r2v"
    recipe: GenerationRecipe | None = None
    storyboard_prompt: str = ""
    storyboard_reference_version_ids: list[EntityId] = Field(default_factory=list)
    selected_storyboard_artifact_version_id: EntityId | None = None
    video_prompt: str = ""
    video_reference_version_ids: list[EntityId] = Field(default_factory=list)
    selected_video_artifact_version_id: EntityId | None = None


class EditClip(StrictModel):
    clip_id: EntityId
    source_asset_version_id: EntityId
    source_in_seconds: float = Field(ge=0)
    source_out_seconds: float = Field(gt=0)
    transition: str = "cut"
    original_sound: str = "preserve"
    reason: str = ""
    overlay: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_range(self) -> EditClip:
        if self.source_out_seconds <= self.source_in_seconds:
            raise ValueError("source_out_seconds must be greater than source_in_seconds")
        return self


class EditStoryboardPanel(StrictModel):
    panel_id: EntityId
    clip_id: EntityId
    title: str = ""
    description: str = ""
    source_timestamp_seconds: float = Field(ge=0)
    frame_artifact_version_id: EntityId | None = None


class EditAudioPlan(StrictModel):
    preserve_original: bool = True
    music_prompt: str = ""
    voiceover: str = ""
    notes: str = ""


class AiEditPlan(StrictModel):
    """Structured edit plan embedded directly in ``project.json``."""

    plan_id: EntityId
    plan_hash: Sha256 | None = None
    summary: str = ""
    target_duration_seconds: float | None = Field(default=None, ge=0)
    timeline: EntityCollection[EditClip] = Field(default_factory=EntityCollection)
    storyboard: EntityCollection[EditStoryboardPanel] = Field(default_factory=EntityCollection)
    audio_plan: EditAudioPlan = Field(default_factory=EditAudioPlan)
    model: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_and_hash_plan(self) -> AiEditPlan:
        _require_collection_identity(self.timeline, "clip_id", "edit timeline")
        _require_collection_identity(self.storyboard, "panel_id", "edit storyboard")
        for panel in self.storyboard.items.values():
            _require_key(self.timeline.items, panel.clip_id, "storyboard panel clip")
        actual = self.content_hash()
        if self.plan_hash is not None and self.plan_hash != actual:
            raise ValueError("plan_hash does not match canonical AI Edit Plan content")
        object.__setattr__(self, "plan_hash", actual)
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"plan_hash"})
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class EditProduction(StrictModel):
    route: Literal["edit"] = "edit"
    intent: str = ""
    source_asset_version_ids: list[EntityId] = Field(default_factory=list)
    plan: AiEditPlan | None = None
    storyboard_sheet_artifact_version_id: EntityId | None = None
    timeline_summary: str = ""
    subtitles_file_id: EntityId | None = None
    rendered_video_artifact_version_id: EntityId | None = None


UnitProduction = Annotated[
    R2VProduction | EditProduction,
    Field(discriminator="route"),
]


class Production(StrictModel):
    units_by_id: dict[EntityId, UnitProduction] = Field(default_factory=dict)


class SequenceItem(StrictModel):
    selection_id: EntityId
    source_ref: str
    source_kind: Literal["unit_video", "section_video"]
    artifact_version_id: EntityId


class Transition(StrictModel):
    from_selection_id: EntityId
    to_selection_id: EntityId
    kind: str
    duration_ms: int = Field(default=0, ge=0)


class Composition(StrictModel):
    sequence: EntityCollection[SequenceItem] = Field(default_factory=EntityCollection)
    transitions: list[Transition] = Field(default_factory=list)
    audio_plan: str = ""
    subtitle_file_id: EntityId | None = None
    rendered_video_artifact_version_id: EntityId | None = None

    @model_validator(mode="after")
    def _validate_sequence(self) -> Composition:
        _require_collection_identity(self.sequence, "selection_id", "composition sequence")
        for transition in self.transitions:
            _require_key(self.sequence.items, transition.from_selection_id, "transition source")
            _require_key(self.sequence.items, transition.to_selection_id, "transition target")
        return self


class PostProduction(StrictModel):
    sections_by_id: dict[EntityId, Composition] = Field(default_factory=dict)
    final: Composition | None = None


class Project(StrictModel):
    schema_version: Literal[1] = CURRENT_PROJECT_SCHEMA_VERSION
    project_id: EntityId
    generation: int = Field(default=0, ge=0)
    created_at: UtcDateTime
    updated_at: UtcDateTime
    name: str = Field(min_length=1)
    description: str = ""
    scenario: Literal["short_drama", "video_edit", "general"] = "general"
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    strategy: CreativeStrategy = Field(default_factory=CreativeStrategy)
    sources: SourceCatalog = Field(default_factory=SourceCatalog)
    visual: VisualDevelopment = Field(default_factory=VisualDevelopment)
    story: Story = Field(default_factory=Story)
    production: Production = Field(default_factory=Production)
    post_production: PostProduction = Field(default_factory=PostProduction)
    assets: AssetIndex = Field(default_factory=AssetIndex)

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, value: str) -> str:
        # A Project id is also a host-filesystem segment and is intentionally
        # stricter than other EntityIds (which may contain ':').
        if ":" in value or value in {".", ".."}:
            raise ValueError("project_id must be a safe filesystem segment")
        return value

    @model_validator(mode="after")
    def _validate_graph(self) -> Project:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")

        _require_collection_identity(self.sources.sources, "source_id", "project sources")
        _require_collection_identity(self.visual.entities, "entity_id", "visual entities")
        source_ids = set(self.sources.sources.items)
        source_versions = self.assets.source_versions_by_id
        artifact_versions = self.assets.artifact_versions_by_id
        indexed_files = self.assets.files_by_id

        for source in self.sources.sources.items.values():
            selected = _require_key(
                source_versions,
                source.selected_asset_version_id,
                "selected source version",
            )
            if selected.logical_asset_id != source.logical_asset_id:
                raise ValueError(f"source {source.source_id} selected a foreign logical asset")
            if source.current_intelligence_version_id is not None:
                intelligence = _require_key(
                    self.assets.intelligence_versions_by_id,
                    source.current_intelligence_version_id,
                    "selected source intelligence",
                )
                if intelligence.source_asset_version_id != source.selected_asset_version_id:
                    raise ValueError(
                        f"source {source.source_id} intelligence targets another version"
                    )

        visual_ids: dict[str, set[str]] = {"character": set(), "scene": set(), "prop": set()}
        for entity in self.visual.entities.items.values():
            visual_ids[entity.kind].add(entity.entity_id)
            _require_collection_identity(entity.variants, "variant_id", "visual variants")
            for variant in entity.variants.items.values():
                _require_all(source_versions, variant.reference_asset_version_ids, "visual source")
                _require_all(
                    artifact_versions,
                    variant.reference_artifact_version_ids,
                    "visual artifact reference",
                )
                _require_all(
                    artifact_versions,
                    variant.generated_artifact_version_ids,
                    "visual artifact",
                )
            if entity.selected_artifact_version_id is not None:
                _require_key(
                    artifact_versions,
                    entity.selected_artifact_version_id,
                    "selected visual artifact",
                )

        story_units: dict[str, Unit] = {}
        for section in self.story.sections.items.values():
            for unit in section.units.items.values():
                if unit.unit_id in story_units:
                    raise ValueError(f"unit id {unit.unit_id} is duplicated across sections")
                story_units[unit.unit_id] = unit
                _require_all_ids(source_ids, unit.source_refs, "unit source")
                _validate_visual_refs(unit, visual_ids)
                for shot in unit.shots.items.values():
                    _validate_visual_refs(shot, visual_ids)

        for unit_id, production in self.production.units_by_id.items():
            unit = _require_key(story_units, unit_id, "production unit")
            if production.route != unit.route.value:
                raise ValueError(f"production route does not match story unit {unit_id}")
            if isinstance(production, R2VProduction):
                _require_version_refs(
                    source_versions,
                    artifact_versions,
                    production.storyboard_reference_version_ids,
                    "storyboard reference",
                )
                _require_version_refs(
                    source_versions,
                    artifact_versions,
                    production.video_reference_version_ids,
                    "video reference",
                )
                for version_id in (
                    production.selected_storyboard_artifact_version_id,
                    production.selected_video_artifact_version_id,
                ):
                    if version_id is not None:
                        _require_key(artifact_versions, version_id, "selected production artifact")
            else:
                _require_all(
                    source_versions,
                    production.source_asset_version_ids,
                    "edit source version",
                )
                if production.plan is not None:
                    for clip in production.plan.timeline.items.values():
                        _require_key(
                            source_versions,
                            clip.source_asset_version_id,
                            "AI Edit Plan source",
                        )
                    for panel in production.plan.storyboard.items.values():
                        if panel.frame_artifact_version_id is not None:
                            _require_key(
                                artifact_versions,
                                panel.frame_artifact_version_id,
                                "AI Edit Plan storyboard frame",
                            )
                for version_id in (
                    production.storyboard_sheet_artifact_version_id,
                    production.rendered_video_artifact_version_id,
                ):
                    if version_id is not None:
                        _require_key(artifact_versions, version_id, "edit production artifact")
                if production.subtitles_file_id is not None:
                    _require_key(indexed_files, production.subtitles_file_id, "edit subtitles")

        compositions = [
            *self.post_production.sections_by_id.values(),
            self.post_production.final,
        ]
        for composition in compositions:
            if composition is None:
                continue
            for item in composition.sequence.items.values():
                _require_key(artifact_versions, item.artifact_version_id, "composition artifact")
            if composition.subtitle_file_id is not None:
                _require_key(indexed_files, composition.subtitle_file_id, "composition subtitles")
            if composition.rendered_video_artifact_version_id is not None:
                _require_key(
                    artifact_versions,
                    composition.rendered_video_artifact_version_id,
                    "composition output",
                )
        return self

    @classmethod
    def new(
        cls,
        *,
        project_id: str,
        name: str,
        description: str = "",
        scenario: Literal["short_drama", "video_edit", "general"] = "general",
        settings: ProjectSettings | None = None,
        now: datetime | None = None,
    ) -> Project:
        timestamp = now or datetime.now(timezone.utc)
        return cls(
            project_id=project_id,
            created_at=timestamp,
            updated_at=timestamp,
            name=name,
            description=description,
            scenario=scenario,
            settings=settings or ProjectSettings(),
        )


def _require_mapping_identity(
    mapping: dict[str, Any],
    identity_field: str,
    label: str,
) -> None:
    for key, item in mapping.items():
        if getattr(item, identity_field) != key:
            raise ValueError(f"{label} key {key} does not match {identity_field}")


def _require_collection_identity(
    collection: EntityCollection[Any],
    identity_field: str,
    label: str,
) -> None:
    _require_mapping_identity(collection.items, identity_field, label)


def _require_key(mapping: dict[str, T], key: str, label: str) -> T:
    try:
        return mapping[key]
    except KeyError as exc:
        raise ValueError(f"{label} references missing id {key}") from exc


def _require_all(mapping: dict[str, Any], keys: list[str], label: str) -> None:
    for key in keys:
        _require_key(mapping, key, label)


def _require_all_ids(known: set[str], keys: list[str], label: str) -> None:
    for key in keys:
        if key not in known:
            raise ValueError(f"{label} references missing id {key}")


def _require_version_refs(
    source_versions: dict[str, SourceAssetVersion],
    artifact_versions: dict[str, ArtifactVersion],
    keys: list[str],
    label: str,
) -> None:
    for key in keys:
        if key not in source_versions and key not in artifact_versions:
            raise ValueError(f"{label} references missing exact version {key}")


def _validate_visual_refs(value: Unit | Shot, known: dict[str, set[str]]) -> None:
    _require_all_ids(known["character"], value.character_refs, "character")
    _require_all_ids(known["prop"], value.prop_refs, "prop")
    if value.scene_ref is not None and value.scene_ref not in known["scene"]:
        raise ValueError(f"scene references missing id {value.scene_ref}")


__all__ = [
    "CURRENT_PROJECT_SCHEMA_VERSION",
    "AiEditPlan",
    "ArtifactSlot",
    "ArtifactVersion",
    "AssetIndex",
    "Composition",
    "CreativeStrategy",
    "EditProduction",
    "EntityCollection",
    "EntityId",
    "IndexedContentRef",
    "IndexedFile",
    "PostProduction",
    "Production",
    "Project",
    "ProjectSettings",
    "ProjectSource",
    "R2VProduction",
    "Section",
    "Shot",
    "SourceAssetVersion",
    "SourceCatalog",
    "SourceIntelligenceVersion",
    "Story",
    "Unit",
    "UnitProduction",
    "UnitTaskType",
    "VisualDevelopment",
    "VisualEntity",
    "VisualVariant",
]
