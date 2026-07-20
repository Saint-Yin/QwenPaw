"""Semantic Creator Commands translated directly into Project file commits."""

from __future__ import annotations

import asyncio
import json
import math
import re
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Body, Depends, Header, status
from pydantic import ValidationError as PydanticValidationError

from domain.enums import CreatorCommandType
from domain.errors import (
    BadRequestError,
    CasConflictError,
    ConflictError,
    NotFoundError,
    StorageIntegrityError,
    ValidationError,
)
from schemas.commands import CreatorCommandAccepted, CreatorCommandRequest
from services.file_agent_runtime import notify_creator_agent_runtime
from services.media_files import (
    execute_file_image_command,
    execute_file_local_media_command,
    execute_file_r2v_command,
)
from services.project_files.commit import ProjectCommitError
from services.project_files.facade import CreatorFileServices
from services.project_files.store import ProjectNotFound, ProjectStoreError
from services.runtime_files.errors import (
    IdempotencyConflictError,
    IdempotencyStateConflictError,
)
from services.runtime_files.idempotency_store import IdempotencyRecordStore
from services.runtime_files.models import (
    ChangeOrigin,
    IdempotencyStatus,
    MessageChannel,
    MessageClassification,
    ReviewPolicy,
)
from services.runtime_files.session_store import SessionStoreError
from services.source_analysis import source_analysis_service

from .dependencies import (
    CreatorErrorRoute,
    project_file_services,
    resolve_idempotency_key,
)


router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["commands-files"],
    route_class=CreatorErrorRoute,
)


_DIRECT_FILE_COMMANDS = frozenset(
    {
        CreatorCommandType.IMPORT_SCRIPT,
        CreatorCommandType.SET_STRATEGY_TEXT,
        CreatorCommandType.SET_SECTION_TEXT,
        CreatorCommandType.SET_UNIT_TEXT,
        CreatorCommandType.CREATE_SECTION,
        CreatorCommandType.DELETE_SECTION,
        CreatorCommandType.MOVE_SECTION,
        CreatorCommandType.CREATE_UNIT,
        CreatorCommandType.DELETE_UNIT,
        CreatorCommandType.MOVE_UNIT,
        CreatorCommandType.CHANGE_UNIT_ROUTE,
        CreatorCommandType.UPSERT_SHOT,
        CreatorCommandType.DELETE_SHOT,
        CreatorCommandType.MOVE_SHOT,
        CreatorCommandType.BIND_REFERENCE,
        CreatorCommandType.UNBIND_REFERENCE,
        CreatorCommandType.SET_EDIT_CLIP_RANGE,
        CreatorCommandType.SET_EDIT_CLIP_OS,
        CreatorCommandType.SET_EDIT_CLIP_TRANSITION,
        CreatorCommandType.MOVE_EDIT_CLIP,
        CreatorCommandType.DELETE_EDIT_CLIP,
        CreatorCommandType.SET_EDIT_AUDIO_PLAN,
        CreatorCommandType.ATTACH_SOURCE_ASSETS,
        CreatorCommandType.DETACH_SOURCE_ASSETS,
        CreatorCommandType.SUPPLEMENT_ASSET,
        CreatorCommandType.SELECT_ARTIFACT_VERSION,
        CreatorCommandType.SET_SECTION_COMPOSE_SELECTION,
        CreatorCommandType.SET_SECTION_COMPOSE_TRANSITION,
        CreatorCommandType.SET_FINAL_COMPOSE_SELECTION,
        CreatorCommandType.SET_FINAL_COMPOSE_TRANSITION,
    }
)
_IMAGE_FILE_COMMANDS = frozenset(
    {
        CreatorCommandType.GENERATE_ASSET,
        CreatorCommandType.GENERATE_STORYBOARD_IMAGE,
    }
)
_LOCAL_MEDIA_FILE_COMMANDS = frozenset(
    {
        CreatorCommandType.EXECUTE_EDIT,
        CreatorCommandType.STITCH_SECTION,
        CreatorCommandType.COMPOSE_FINAL_VIDEO,
    }
)
_R2V_FILE_COMMANDS = frozenset({CreatorCommandType.GENERATE_R2V_VIDEO})
_AGENT_COMMANDS = frozenset(
    set(CreatorCommandType)
    - set(_DIRECT_FILE_COMMANDS)
    - set(_IMAGE_FILE_COMMANDS)
    - set(_LOCAL_MEDIA_FILE_COMMANDS)
    - set(_R2V_FILE_COMMANDS)
)
_ENTITY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _stable_id(prefix: str, project_id: str, command_id: str, suffix: str = "") -> str:
    digest = uuid5(
        NAMESPACE_URL,
        f"qwenpaw-creator:command:{prefix}:{project_id}:{command_id}:{suffix}",
    ).hex
    return f"{prefix}-{digest}"


def _idempotency(services: CreatorFileServices, project_id: str) -> IdempotencyRecordStore:
    return IdempotencyRecordStore(
        services.projects.project_root(project_id)
        / "runtime"
        / "idempotency"
        / "commands"
    )


def _target_id(target_ref: str, prefix: str) -> str:
    expected = f"{prefix}:"
    if not target_ref.startswith(expected) or not target_ref[len(expected) :]:
        raise ValidationError(f"targetRef 必须是 {expected}<id>")
    return target_ref[len(expected) :]


def _text(value: Any, label: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} 必须是字符串")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{label} 不能为空")
    return value


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} 必须是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{label} 必须是有限数字")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{label} 不能小于 {minimum:g}")
    return number


def _entity_id(value: Any, label: str) -> str:
    identifier = _text(value, label, allow_empty=False).strip()
    if identifier in {".", ".."} or _ENTITY_ID.fullmatch(identifier) is None:
        raise ValidationError(f"{label} 不合法")
    return identifier


def _section(candidate: dict[str, Any], section_id: str) -> dict[str, Any]:
    item = candidate["story"]["sections"]["items"].get(section_id)
    if item is None:
        raise NotFoundError("Section 不存在")
    return item


def _unit_location(
    candidate: dict[str, Any], unit_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    for section in candidate["story"]["sections"]["items"].values():
        unit = section["units"]["items"].get(unit_id)
        if unit is not None:
            return section, unit
    raise NotFoundError("Unit 不存在")


def _shot_location(
    candidate: dict[str, Any], shot_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    for section in candidate["story"]["sections"]["items"].values():
        for unit in section["units"]["items"].values():
            shot = unit["shots"]["items"].get(shot_id)
            if shot is not None:
                return unit, shot
    raise NotFoundError("Shot 不存在")


def _move(order: list[str], item_id: str, args: dict[str, Any]) -> None:
    if item_id not in order:
        raise NotFoundError("移动目标不存在")
    order.remove(item_id)
    before = args.get("beforeId") or args.get("beforeSectionId") or args.get("beforeUnitId")
    after = args.get("afterId") or args.get("afterSectionId") or args.get("afterUnitId")
    if before in order:
        order.insert(order.index(before), item_id)
    elif after in order:
        order.insert(order.index(after) + 1, item_id)
    else:
        raw_index = args.get("index")
        index = len(order) if raw_index is None else max(0, min(int(raw_index), len(order)))
        order.insert(index, item_id)


def _insert_after(order: list[str], item_id: str, after_id: Any) -> None:
    if isinstance(after_id, str) and after_id in order:
        order.insert(order.index(after_id) + 1, item_id)
    else:
        order.append(item_id)


def _source_id_for_ref(candidate: dict[str, Any], source_ref: str) -> str:
    if source_ref.startswith("asset://") and "@" in source_ref:
        version_id = source_ref.rsplit("@", 1)[1]
    elif source_ref.startswith("asset-version:"):
        version_id = source_ref.split(":", 1)[1]
    else:
        raise ValidationError("source reference 必须指向 AssetVersion")
    for source_id, source in candidate["sources"]["sources"]["items"].items():
        if source["selected_asset_version_id"] == version_id:
            return source_id
    raise NotFoundError("AssetVersion 尚未 attach 到 Project")


def _visual_id_for_ref(source_ref: str) -> str:
    prefix = "project://asset/"
    if not source_ref.startswith(prefix) or not source_ref[len(prefix) :]:
        raise ValidationError("视觉引用必须是 project://asset/<id>")
    return source_ref[len(prefix) :]


def _ensure_production(candidate: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    unit_id = unit["unit_id"]
    production = candidate["production"]["units_by_id"].get(unit_id)
    if production is None:
        production = (
            {
                "route": "r2v",
                "recipe": None,
                "storyboard_prompt": "",
                "storyboard_reference_version_ids": [],
                "selected_storyboard_artifact_version_id": None,
                "video_prompt": "",
                "video_reference_version_ids": [],
                "selected_video_artifact_version_id": None,
            }
            if unit["route"] == "r2v"
            else {
                "route": "edit",
                "intent": "",
                "source_asset_version_ids": [],
                "plan": None,
                "storyboard_sheet_artifact_version_id": None,
                "timeline_summary": "",
                "subtitles_file_id": None,
                "rendered_video_artifact_version_id": None,
            }
        )
        candidate["production"]["units_by_id"][unit_id] = production
    return production


def _edit_plan(
    candidate: dict[str, Any], target_ref: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    unit_id = _target_id(target_ref, "unit")
    _section_record, unit = _unit_location(candidate, unit_id)
    if unit["route"] != "edit":
        raise ConflictError("AI Edit 手动命令只能修改 edit Unit")
    production = candidate["production"]["units_by_id"].get(unit_id)
    if not isinstance(production, dict) or production.get("route") != "edit":
        raise ConflictError("Unit 缺少 EditProduction")
    plan = production.get("plan")
    if not isinstance(plan, dict):
        raise ConflictError("Unit 缺少 AI Edit Plan")
    return production, plan


def _edit_clip(plan: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    clip_id = _text(args.get("clipId"), "clipId", allow_empty=False).strip()
    clip = plan["timeline"]["items"].get(clip_id)
    if clip is None:
        raise NotFoundError("AI Edit clip 不存在")
    return clip


def _refresh_edit_plan_projection(
    production: dict[str, Any], plan: dict[str, Any]
) -> None:
    timeline = plan["timeline"]
    cursor = 0.0
    lines = [
        f"AI Edit Plan：{plan['plan_id']}",
        f"Timeline 片段：{len(timeline['order'])}",
    ]
    ranges: list[str] = []
    for index, clip_id in enumerate(timeline["order"], 1):
        clip = timeline["items"][clip_id]
        start = float(clip["source_in_seconds"])
        end = float(clip["source_out_seconds"])
        cursor += end - start
        ranges.append(f"- {clip_id}: {start:g}–{end:g} 秒")
    cursor = round(cursor, 6)
    plan["target_duration_seconds"] = cursor
    lines.extend([f"目标时长：{cursor:g} 秒", "片段范围：", *ranges])
    production["timeline_summary"] = "\n".join(lines) + "\n"


def _visual_entity(candidate: dict[str, Any], target_ref: str) -> dict[str, Any]:
    entity_id = _target_id(target_ref, "asset")
    entity = candidate["visual"]["entities"]["items"].get(entity_id)
    if entity is None:
        raise NotFoundError("视觉资产不存在")
    return entity


def _prompt_index(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("promptIndex 必须是非负整数")
    if value < 0 or value > 999:
        raise ValidationError("promptIndex 必须在 0–999")
    return value


def _visual_variant_at(
    entity: dict[str, Any],
    prompt_index: Any,
    *,
    project_id: str,
    create: bool,
) -> dict[str, Any]:
    index = _prompt_index(prompt_index)
    variants = entity["variants"]
    if not create and index >= len(variants["order"]):
        raise NotFoundError("视觉资产形象不存在")
    while len(variants["order"]) <= index:
        position = len(variants["order"])
        variant_id = _stable_id(
            "variant", project_id, entity["entity_id"], str(position)
        )
        if variant_id in variants["items"]:
            raise ConflictError("视觉资产 Variant 稳定 ID 冲突")
        variants["items"][variant_id] = {
            "variant_id": variant_id,
            "requirements": "",
            "prompt": "",
            "reference_asset_version_ids": [],
            "reference_artifact_version_ids": [],
            "generated_artifact_version_ids": [],
        }
        variants["order"].append(variant_id)
    return variants["items"][variants["order"][index]]


def _append_visual_variant(
    entity: dict[str, Any], *, project_id: str
) -> dict[str, Any]:
    return _visual_variant_at(
        entity,
        len(entity["variants"]["order"]),
        project_id=project_id,
        create=True,
    )


def _exact_media_ref(candidate: dict[str, Any], value: Any) -> tuple[str, str]:
    ref = _text(value, "媒体引用", allow_empty=False).strip()
    if "\n" in ref or "\r" in ref:
        raise ValidationError("媒体引用必须是单行 exact ref")
    if ref.startswith("asset://"):
        locator = ref[len("asset://") :]
        logical_id, separator, version_id = locator.rpartition("@")
        if not separator or not logical_id or not version_id:
            raise ValidationError("Asset 引用必须是 asset://logicalId@versionId")
        logical_id, version_id = unquote(logical_id), unquote(version_id)
        version = candidate["assets"]["source_versions_by_id"].get(version_id)
        if version is None or version["logical_asset_id"] != logical_id:
            raise NotFoundError("AssetVersion 不存在或 logical id 不匹配")
        return "asset", version_id
    if ref.startswith("artifact://"):
        locator = ref[len("artifact://") :]
        slot_id, separator, version_id = locator.rpartition("@")
        if not separator or not slot_id or not version_id:
            raise ValidationError("Artifact 引用必须是 artifact://slotId@versionId")
        slot_id, version_id = unquote(slot_id), unquote(version_id)
        version = candidate["assets"]["artifact_versions_by_id"].get(version_id)
        if version is None or version["slot_id"] != slot_id:
            raise NotFoundError("ArtifactVersion 不存在或 slot id 不匹配")
        return "artifact", version_id
    raise ValidationError("媒体引用必须指向 AssetVersion 或 ArtifactVersion")


def _visual_media(candidate: dict[str, Any], args: dict[str, Any]) -> tuple[str, str]:
    image_ref = args.get("imageRef")
    if image_ref:
        return _exact_media_ref(candidate, image_ref)

    raw_version_id = args.get("assetVersionId")
    if raw_version_id:
        version_id = _text(raw_version_id, "assetVersionId", allow_empty=False).strip()
        version = candidate["assets"]["source_versions_by_id"].get(version_id)
        raw_asset_id = args.get("assetId")
        asset_id = (
            _text(raw_asset_id, "assetId", allow_empty=False).strip()
            if raw_asset_id
            else None
        )
        if version is None or (
            asset_id is not None and version["logical_asset_id"] != asset_id
        ):
            raise NotFoundError(
                "图片 AssetVersion 不存在或 logical id 不匹配"
            )
        return "asset", version_id

    image_url = _text(args.get("imageUrl"), "imageUrl", allow_empty=False).strip()
    if image_url.startswith(("asset://", "artifact://")):
        return _exact_media_ref(candidate, image_url)
    path = urlsplit(image_url).path
    routes = (
        ("/media/assets/", "asset", candidate["assets"]["source_versions_by_id"]),
        (
            "/media/artifacts/",
            "artifact",
            candidate["assets"]["artifact_versions_by_id"],
        ),
    )
    for marker, kind, versions in routes:
        if marker not in path:
            continue
        version_id = unquote(path.rsplit(marker, 1)[1]).strip("/")
        if version_id and version_id in versions:
            return kind, version_id
    raise NotFoundError("imageUrl 不能解析为当前 Project 的不可变媒体版本")


def _add_visual_media(
    entity: dict[str, Any], variant: dict[str, Any], media: tuple[str, str], *, select: bool
) -> None:
    kind, version_id = media
    field = (
        "reference_asset_version_ids"
        if kind == "asset"
        else "generated_artifact_version_ids"
    )
    if version_id not in variant[field]:
        variant[field].append(version_id)
    if kind == "artifact" and select:
        entity["selected_artifact_version_id"] = version_id


def _source_version_dependents(
    candidate: dict[str, Any], version_id: str
) -> list[str]:
    dependents: list[str] = []
    for source_id, source in candidate["sources"]["sources"]["items"].items():
        if source["selected_asset_version_id"] == version_id:
            dependents.append(f"source:{source_id}")
    for entity_id, entity in candidate["visual"]["entities"]["items"].items():
        for variant_id, variant in entity["variants"]["items"].items():
            if version_id in variant["reference_asset_version_ids"]:
                dependents.append(f"visual:{entity_id}/variant:{variant_id}")
    for unit_id, production in candidate["production"]["units_by_id"].items():
        if production["route"] == "r2v":
            if version_id in production["storyboard_reference_version_ids"]:
                dependents.append(f"unit:{unit_id}/storyboard")
            if version_id in production["video_reference_version_ids"]:
                dependents.append(f"unit:{unit_id}/video")
            continue
        if version_id in production["source_asset_version_ids"]:
            dependents.append(f"unit:{unit_id}/sources")
        plan = production.get("plan")
        if isinstance(plan, dict):
            for clip_id, clip in plan["timeline"]["items"].items():
                if clip["source_asset_version_id"] == version_id:
                    dependents.append(f"unit:{unit_id}/clip:{clip_id}")
    return dependents


def _delete_visual_entity(candidate: dict[str, Any], entity_id: str) -> None:
    entities = candidate["visual"]["entities"]
    entity = entities["items"].get(entity_id)
    if entity is None:
        raise NotFoundError("视觉资产不存在")
    kind = entity["kind"]
    for section in candidate["story"]["sections"]["items"].values():
        for unit in section["units"]["items"].values():
            records = [unit, *unit["shots"]["items"].values()]
            for record in records:
                if kind == "character":
                    record["character_refs"] = [
                        value for value in record["character_refs"] if value != entity_id
                    ]
                elif kind == "scene" and record["scene_ref"] == entity_id:
                    record["scene_ref"] = None
                elif kind == "prop":
                    record["prop_refs"] = [
                        value for value in record["prop_refs"] if value != entity_id
                    ]
    del entities["items"][entity_id]
    entities["order"].remove(entity_id)


def _apply_supplement_asset(
    candidate: dict[str, Any],
    request: CreatorCommandRequest,
    *,
    project_id: str,
) -> None:
    args = request.arguments
    operation = args.get("operation")
    entities = candidate["visual"]["entities"]

    if operation == "create":
        if request.target_ref != "project:assets":
            raise ValidationError("新建视觉资产 target 必须是 project:assets")
        kind = _text(args.get("assetKind"), "assetKind", allow_empty=False).strip()
        if kind not in {"character", "scene", "prop"}:
            raise ValidationError("素材必须通过 Asset ingest 创建；Visual 只支持角色、场景、道具")
        name = _text(args.get("name"), "name", allow_empty=False).strip()
        explicit_id = args.get("id") or args.get("assetId")
        entity_id = (
            _entity_id(explicit_id, "asset id")
            if explicit_id is not None
            else _stable_id("visual", project_id, request.client_command_id)
        )
        if entity_id in entities["items"]:
            raise ConflictError("视觉资产 id 已存在")
        entities["items"][entity_id] = {
            "entity_id": entity_id,
            "kind": kind,
            "name": name,
            "description": _text(args.get("description", ""), "description"),
            "continuity": "",
            "variants": {"items": {}, "order": []},
            "selected_artifact_version_id": None,
        }
        entities["order"].append(entity_id)
        return

    if request.target_ref == "project:assets":
        raise ValidationError("SUPPLEMENT_ASSET 修改/删除 target 必须是 asset:<id>")
    target_id = _target_id(request.target_ref, "asset")

    if operation == "delete":
        raw_version_ref = args.get("assetVersionRef")
        if raw_version_ref is not None or target_id in candidate["assets"]["source_versions_by_id"]:
            version_id = target_id
            if raw_version_ref is not None:
                kind, referenced_id = _exact_media_ref(candidate, raw_version_ref)
                if kind != "asset":
                    raise ValidationError("assetVersionRef 必须指向 AssetVersion")
                referenced = candidate["assets"]["source_versions_by_id"][referenced_id]
                if target_id not in {referenced_id, referenced["logical_asset_id"]}:
                    raise ConflictError("assetVersionRef 与 target asset id 不一致")
                version_id = referenced_id
            if version_id not in candidate["assets"]["source_versions_by_id"]:
                raise NotFoundError("AssetVersion 不存在")
            dependents = _source_version_dependents(candidate, version_id)
            if dependents:
                raise ConflictError(
                    "AssetVersion 仍被 Project 引用，请先解除引用",
                    details={"references": dependents},
                )
            intelligence = candidate["assets"]["intelligence_versions_by_id"]
            for intelligence_id in [
                item_id
                for item_id, item in intelligence.items()
                if item["source_asset_version_id"] == version_id
            ]:
                del intelligence[intelligence_id]
            del candidate["assets"]["source_versions_by_id"][version_id]
            return
        _delete_visual_entity(candidate, target_id)
        return
    if operation is not None:
        raise ValidationError("SUPPLEMENT_ASSET operation 只能是 create 或 delete")

    entity = _visual_entity(candidate, request.target_ref)
    field = _text(args.get("field"), "field", allow_empty=False).strip()
    if field == "name":
        entity["name"] = _text(args.get("value"), "name", allow_empty=False).strip()
        return
    if field == "description":
        entity["description"] = _text(args.get("value"), "description")
        return
    if field == "promptConfig":
        variant = _visual_variant_at(
            entity,
            args.get("promptIndex"),
            project_id=project_id,
            create=True,
        )
        variant["prompt"] = _text(args.get("prompt"), "prompt")
        raw_refs = args.get("referenceImageUrls", [])
        if not isinstance(raw_refs, list):
            raise ValidationError("referenceImageUrls 必须是 exact ref 数组")
        asset_references: list[str] = []
        artifact_references: list[str] = []
        for value in raw_refs:
            kind, version_id = _exact_media_ref(candidate, value)
            references = (
                asset_references if kind == "asset" else artifact_references
            )
            if version_id not in references:
                references.append(version_id)
        variant["reference_asset_version_ids"] = asset_references
        variant["reference_artifact_version_ids"] = artifact_references
        return
    if field == "image":
        prompt_index = _prompt_index(args.get("promptIndex"))
        variant = _visual_variant_at(
            entity,
            prompt_index,
            project_id=project_id,
            create=True,
        )
        _add_visual_media(
            entity,
            variant,
            _visual_media(candidate, args),
            select=prompt_index == 0,
        )
        return
    if field == "appearancePrompt":
        variant = _append_visual_variant(entity, project_id=project_id)
        variant["requirements"] = _text(
            args.get("refDescription"),
            "refDescription",
            allow_empty=False,
        ).strip()
        return
    if field == "appearance":
        if args.get("action") == "removeFacet":
            index = _prompt_index(args.get("promptIndex"))
            variants = entity["variants"]
            if index >= len(variants["order"]):
                raise NotFoundError("视觉资产形象不存在")
            variant_id = variants["order"].pop(index)
            removed = variants["items"].pop(variant_id)
            selected = entity.get("selected_artifact_version_id")
            if selected in removed["generated_artifact_version_ids"] and not any(
                selected in item["generated_artifact_version_ids"]
                for item in variants["items"].values()
            ):
                entity["selected_artifact_version_id"] = next(
                    (
                        version_id
                        for ordered_id in variants["order"]
                        for version_id in variants["items"][ordered_id][
                            "generated_artifact_version_ids"
                        ]
                    ),
                    None,
                )
            return
        if args.get("action") is not None:
            raise ValidationError("appearance action 不受支持")
        variant = _append_visual_variant(entity, project_id=project_id)
        variant["requirements"] = _text(
            args.get("refDescription"),
            "refDescription",
            allow_empty=False,
        ).strip()
        variant["prompt"] = _text(args.get("prompt", ""), "prompt")
        if any(args.get(key) for key in ("imageRef", "assetVersionId", "imageUrl")):
            _add_visual_media(
                entity,
                variant,
                _visual_media(candidate, args),
                select=entity.get("selected_artifact_version_id") is None,
            )
        return
    raise ValidationError("SUPPLEMENT_ASSET field 不受支持")


def _new_composition() -> dict[str, Any]:
    return {
        "sequence": {"items": {}, "order": []},
        "transitions": [],
        "audio_plan": "",
        "subtitle_file_id": None,
        "rendered_video_artifact_version_id": None,
    }


def _apply_selections(
    composition: dict[str, Any],
    selections: Any,
    *,
    project_id: str,
    command_id: str,
) -> None:
    if not isinstance(selections, list):
        raise ValidationError("selections 必须是数组")
    items: dict[str, Any] = {}
    order: list[str] = []
    for index, raw in enumerate(selections):
        if not isinstance(raw, dict):
            raise ValidationError("selection 必须是 object")
        source_ref = str(raw.get("sourceRef") or "")
        artifact_version_id = str(raw.get("artifactVersionId") or "")
        if not source_ref or not artifact_version_id:
            raise ValidationError("selection 缺少 sourceRef/artifactVersionId")
        selection_id = _stable_id("selection", project_id, command_id, str(index))
        items[selection_id] = {
            "selection_id": selection_id,
            "source_ref": source_ref,
            "source_kind": "section_video" if "section" in source_ref else "unit_video",
            "artifact_version_id": artifact_version_id,
        }
        order.append(selection_id)
    composition["sequence"] = {"items": items, "order": order}
    composition["transitions"] = []


def _apply_deterministic(
    candidate: dict[str, Any],
    request: CreatorCommandRequest,
    *,
    project_id: str,
) -> None:
    command = request.type
    args = request.arguments

    if command is CreatorCommandType.SET_STRATEGY_TEXT:
        mapping = {
            "creativeBrief": "creative_brief",
            "audience": "audience",
            "creativeDirection": "creative_direction",
            "constraints": "constraints",
            "successCriteria": "success_criteria",
        }
        field = mapping.get(str(args.get("field")), str(args.get("field")))
        if field not in set(mapping.values()):
            raise ValidationError("未知 strategy field")
        candidate["strategy"][field] = str(args.get("value") or "")
        return

    if command is CreatorCommandType.SET_SECTION_TEXT:
        section = _section(candidate, _target_id(request.target_ref, "section"))
        mapping = {
            "title": "title",
            "summary": "summary",
            "narrative": "narrative",
            "script": "script",
            "voiceover": "voiceover",
            "durationBudget": "duration_budget_seconds",
            "pacing": "pacing",
            "constraints": "constraints",
            "transition": "transition",
        }
        field = mapping.get(str(args.get("field")))
        if field is None:
            raise ValidationError("未知 Section field")
        section[field] = args.get("value")
        return

    if command is CreatorCommandType.SET_UNIT_TEXT:
        _parent, unit = _unit_location(
            candidate, _target_id(request.target_ref, "unit")
        )
        field = str(args.get("field") or "")
        value = args.get("value")
        direct = {
            "title": "title",
            "duration": "duration_seconds",
            "narrative": "narrative",
            "continuity": "continuity",
        }
        if field in direct:
            unit[direct[field]] = value
            return
        production = _ensure_production(candidate, unit)
        production_field = {
            "storyboardPrompt": "storyboard_prompt",
            "videoPrompt": "video_prompt",
            "goal": "intent",
        }.get(field)
        if production_field is None or production_field not in production:
            raise ValidationError("未知 Unit field")
        production[production_field] = str(value or "")
        return

    sections = candidate["story"]["sections"]
    if command is CreatorCommandType.CREATE_SECTION:
        section_id = _stable_id("section", project_id, request.client_command_id)
        if section_id not in sections["items"]:
            sections["items"][section_id] = {
                "section_id": section_id,
                "title": str(args.get("title") or "新结构段"),
                "summary": "",
                "narrative": "",
                "script": "",
                "voiceover": "",
                "duration_budget_seconds": None,
                "pacing": "",
                "constraints": [],
                "transition": "",
                "units": {"items": {}, "order": []},
            }
            _insert_after(sections["order"], section_id, args.get("afterSectionId"))
        return
    if command is CreatorCommandType.DELETE_SECTION:
        section_id = _target_id(request.target_ref, "section")
        section = _section(candidate, section_id)
        for unit_id in section["units"]["items"]:
            candidate["production"]["units_by_id"].pop(unit_id, None)
        candidate["post_production"]["sections_by_id"].pop(section_id, None)
        del sections["items"][section_id]
        sections["order"].remove(section_id)
        return
    if command is CreatorCommandType.MOVE_SECTION:
        _move(sections["order"], _target_id(request.target_ref, "section"), args)
        return

    if command is CreatorCommandType.CREATE_UNIT:
        section = _section(candidate, _target_id(request.target_ref, "section"))
        unit_id = _stable_id("unit", project_id, request.client_command_id)
        route = str(args.get("taskType") or "r2v")
        if route not in {"r2v", "edit"}:
            raise ValidationError("taskType 必须是 r2v/edit")
        if unit_id not in section["units"]["items"]:
            unit = {
                "unit_id": unit_id,
                "title": str(args.get("title") or "新单元"),
                "route": route,
                "duration_seconds": float(args.get("duration") or 5),
                "narrative": "",
                "continuity": "",
                "source_refs": [],
                "character_refs": [],
                "scene_ref": None,
                "prop_refs": [],
                "shots": {"items": {}, "order": []},
            }
            section["units"]["items"][unit_id] = unit
            _insert_after(section["units"]["order"], unit_id, args.get("afterUnitId"))
            _ensure_production(candidate, unit)
        return
    if command is CreatorCommandType.DELETE_UNIT:
        unit_id = _target_id(request.target_ref, "unit")
        section, _unit = _unit_location(candidate, unit_id)
        del section["units"]["items"][unit_id]
        section["units"]["order"].remove(unit_id)
        candidate["production"]["units_by_id"].pop(unit_id, None)
        return
    if command is CreatorCommandType.MOVE_UNIT:
        unit_id = _target_id(request.target_ref, "unit")
        section, unit = _unit_location(candidate, unit_id)
        destination_id = str(args.get("sectionId") or section["section_id"])
        destination = _section(candidate, destination_id)
        if destination is not section:
            del section["units"]["items"][unit_id]
            section["units"]["order"].remove(unit_id)
            destination["units"]["items"][unit_id] = unit
            destination["units"]["order"].append(unit_id)
        _move(destination["units"]["order"], unit_id, args)
        return
    if command is CreatorCommandType.CHANGE_UNIT_ROUTE:
        _section_record, unit = _unit_location(
            candidate, _target_id(request.target_ref, "unit")
        )
        route = str(args.get("taskType") or args.get("route") or "")
        if route not in {"r2v", "edit"}:
            raise ValidationError("route 必须是 r2v/edit")
        unit["route"] = route
        candidate["production"]["units_by_id"].pop(unit["unit_id"], None)
        _ensure_production(candidate, unit)
        return

    if command is CreatorCommandType.UPSERT_SHOT:
        _section_record, unit = _unit_location(
            candidate, _target_id(request.target_ref, "unit")
        )
        raw = args.get("shot")
        if not isinstance(raw, dict):
            raise ValidationError("shot 必须是 object")
        shot_id = str(raw.get("id") or _stable_id("shot", project_id, request.client_command_id))
        shot = {
            "shot_id": shot_id,
            "description": str(raw.get("description") or ""),
            "camera": raw.get("camera") or "⊙ 静止",
            "framing": raw.get("framing") or "中景",
            "camera_description": str(raw.get("cameraDescription") or ""),
            "dialogue": str(raw.get("dialogue") or ""),
            "duration_seconds": float(raw.get("duration") or 0),
            "character_refs": list(raw.get("characterRefs") or []),
            "scene_ref": raw.get("sceneRef"),
            "prop_refs": list(raw.get("propRefs") or []),
        }
        unit["shots"]["items"][shot_id] = shot
        if shot_id not in unit["shots"]["order"]:
            unit["shots"]["order"].append(shot_id)
        return
    if command is CreatorCommandType.DELETE_SHOT:
        shot_id = _target_id(request.target_ref, "shot")
        unit, _shot = _shot_location(candidate, shot_id)
        del unit["shots"]["items"][shot_id]
        unit["shots"]["order"].remove(shot_id)
        return
    if command is CreatorCommandType.MOVE_SHOT:
        shot_id = _target_id(request.target_ref, "shot")
        unit, _shot = _shot_location(candidate, shot_id)
        _move(unit["shots"]["order"], shot_id, args)
        return

    if command in {CreatorCommandType.BIND_REFERENCE, CreatorCommandType.UNBIND_REFERENCE}:
        _section_record, unit = _unit_location(
            candidate, _target_id(request.target_ref, "unit")
        )
        field = str(args.get("field") or "")
        source_ref = str(args.get("sourceRef") or "")
        add = command is CreatorCommandType.BIND_REFERENCE
        if field == "sources":
            value = _source_id_for_ref(candidate, source_ref)
            target = unit["source_refs"]
        elif field in {"characters", "props"}:
            value = _visual_id_for_ref(source_ref)
            target = unit["character_refs" if field == "characters" else "prop_refs"]
        elif field == "scene":
            value = _visual_id_for_ref(source_ref)
            unit["scene_ref"] = value if add else None
            return
        else:
            raise ValidationError("未知 reference field")
        if add and value not in target:
            target.append(value)
        if not add and value in target:
            target.remove(value)
        production = _ensure_production(candidate, unit)
        if field == "sources" and production["route"] == "edit":
            version_id = candidate["sources"]["sources"]["items"][value][
                "selected_asset_version_id"
            ]
            refs = production["source_asset_version_ids"]
            if add and version_id not in refs:
                refs.append(version_id)
            if not add and version_id in refs:
                refs.remove(version_id)
        return

    if command in {
        CreatorCommandType.SET_EDIT_CLIP_RANGE,
        CreatorCommandType.SET_EDIT_CLIP_OS,
        CreatorCommandType.SET_EDIT_CLIP_TRANSITION,
        CreatorCommandType.MOVE_EDIT_CLIP,
        CreatorCommandType.DELETE_EDIT_CLIP,
        CreatorCommandType.SET_EDIT_AUDIO_PLAN,
    }:
        production, plan = _edit_plan(candidate, request.target_ref)
        timeline = plan["timeline"]
        if command is CreatorCommandType.SET_EDIT_AUDIO_PLAN:
            audio_plan = args.get("audio_plan")
            if not isinstance(audio_plan, dict):
                raise ValidationError("audio_plan 必须是对象")
            unknown = set(audio_plan) - {
                "preserve_original",
                "music_prompt",
                "voiceover",
                "notes",
            }
            if unknown:
                raise ValidationError(
                    "audio_plan 包含未知字段: " + ", ".join(sorted(unknown))
                )
            preserve = audio_plan.get("preserve_original", True)
            if not isinstance(preserve, bool):
                raise ValidationError("audio_plan.preserve_original 必须是布尔值")
            plan["audio_plan"] = {
                "preserve_original": preserve,
                "music_prompt": _text(
                    audio_plan.get("music_prompt", ""), "audio_plan.music_prompt"
                ),
                "voiceover": _text(
                    audio_plan.get("voiceover", ""), "audio_plan.voiceover"
                ),
                "notes": _text(audio_plan.get("notes", ""), "audio_plan.notes"),
            }
            _refresh_edit_plan_projection(production, plan)
            return

        clip = _edit_clip(plan, args)
        clip_id = clip["clip_id"]
        if command is CreatorCommandType.SET_EDIT_CLIP_RANGE:
            start = _number(args.get("start"), "start", minimum=0)
            end = _number(args.get("end"), "end", minimum=0)
            if start >= end:
                raise ValidationError("clip range 必须满足 start < end")
            clip["source_in_seconds"] = start
            clip["source_out_seconds"] = end
        elif command is CreatorCommandType.SET_EDIT_CLIP_OS:
            overlay = clip["overlay"]
            overlay.setdefault("kind", "pet_os")
            overlay["text"] = _text(
                args.get("text", ""), "text", allow_empty=False
            )
            overlay["vibe"] = _text(
                args.get("vibe", "chill"), "vibe", allow_empty=False
            )
            if "appear_at" in args:
                overlay["appear_at"] = _number(
                    args.get("appear_at"), "appear_at", minimum=0
                )
            if "duration" in args:
                duration = args.get("duration")
                if duration is None or duration == "":
                    overlay.pop("duration", None)
                else:
                    overlay["duration"] = _number(
                        duration, "duration", minimum=0.001
                    )
        elif command is CreatorCommandType.SET_EDIT_CLIP_TRANSITION:
            clip["transition"] = _text(
                args.get("transition"), "transition", allow_empty=False
            )
        elif command is CreatorCommandType.MOVE_EDIT_CLIP:
            before = args.get("beforeClipId")
            after = args.get("afterClipId")
            if before and after:
                raise ValidationError("MOVE_EDIT_CLIP 不能同时提供 before/after")
            timeline["order"].remove(clip_id)
            anchor = before or after
            if anchor:
                anchor_id = _text(anchor, "相邻 clip id", allow_empty=False).strip()
                if anchor_id not in timeline["order"]:
                    raise NotFoundError("相邻 clip 不存在")
                anchor_index = timeline["order"].index(anchor_id)
                timeline["order"].insert(
                    anchor_index if before else anchor_index + 1, clip_id
                )
            else:
                timeline["order"].append(clip_id)
        elif command is CreatorCommandType.DELETE_EDIT_CLIP:
            del timeline["items"][clip_id]
            timeline["order"].remove(clip_id)
            storyboard = plan["storyboard"]
            removed_panels = [
                panel_id
                for panel_id, panel in storyboard["items"].items()
                if panel["clip_id"] == clip_id
            ]
            for panel_id in removed_panels:
                del storyboard["items"][panel_id]
            if removed_panels:
                removed_set = set(removed_panels)
                storyboard["order"] = [
                    panel_id
                    for panel_id in storyboard["order"]
                    if panel_id not in removed_set
                ]
        _refresh_edit_plan_projection(production, plan)
        return

    if command in {CreatorCommandType.ATTACH_SOURCE_ASSETS, CreatorCommandType.DETACH_SOURCE_ASSETS}:
        refs = args.get("assetVersionRefs")
        if not isinstance(refs, list):
            raise ValidationError("assetVersionRefs 必须是数组")
        source_collection = candidate["sources"]["sources"]
        for raw_ref in refs:
            raw = str(raw_ref)
            version_id = raw.rsplit("@", 1)[-1] if "@" in raw else raw.split(":", 1)[-1]
            version = candidate["assets"]["source_versions_by_id"].get(version_id)
            if version is None:
                raise NotFoundError("AssetVersion 不存在")
            existing = next(
                (
                    source_id
                    for source_id, source in source_collection["items"].items()
                    if source["selected_asset_version_id"] == version_id
                ),
                None,
            )
            if command is CreatorCommandType.ATTACH_SOURCE_ASSETS and existing is None:
                source_id = _stable_id("source", project_id, request.client_command_id, version_id)
                source_collection["items"][source_id] = {
                    "source_id": source_id,
                    "display_name": version["name"],
                    "logical_asset_id": version["logical_asset_id"],
                    "selected_asset_version_id": version_id,
                    "current_intelligence_version_id": None,
                    "user_notes": "",
                }
                source_collection["order"].append(source_id)
            elif command is CreatorCommandType.DETACH_SOURCE_ASSETS and existing is not None:
                del source_collection["items"][existing]
                source_collection["order"].remove(existing)
                for section in sections["items"].values():
                    for unit in section["units"]["items"].values():
                        if existing in unit["source_refs"]:
                            unit["source_refs"].remove(existing)
        return

    if command is CreatorCommandType.SUPPLEMENT_ASSET:
        _apply_supplement_asset(candidate, request, project_id=project_id)
        return

    if command is CreatorCommandType.SELECT_ARTIFACT_VERSION:
        slot_id = str(args.get("slotId") or "")
        version_id = str(args.get("artifactVersionId") or "")
        slot = candidate["assets"]["artifact_slots_by_id"].get(slot_id)
        if slot is None or version_id not in slot["version_ids"]:
            raise NotFoundError("ArtifactVersion 不属于目标 Slot")
        slot["selected_version_id"] = version_id
        if request.target_ref.startswith("unit:"):
            _parent, unit = _unit_location(
                candidate, _target_id(request.target_ref, "unit")
            )
            production = _ensure_production(candidate, unit)
            kind = str(slot["kind"]).casefold()
            if production["route"] == "r2v":
                field = (
                    "selected_storyboard_artifact_version_id"
                    if "storyboard" in kind or "image" in kind
                    else "selected_video_artifact_version_id"
                )
                production[field] = version_id
            elif "video" in kind:
                production["rendered_video_artifact_version_id"] = version_id
        return

    if command in {
        CreatorCommandType.SET_SECTION_COMPOSE_SELECTION,
        CreatorCommandType.SET_FINAL_COMPOSE_SELECTION,
    }:
        if command is CreatorCommandType.SET_FINAL_COMPOSE_SELECTION:
            composition = candidate["post_production"].get("final") or _new_composition()
            candidate["post_production"]["final"] = composition
        else:
            section_id = _target_id(request.target_ref, "post")
            _section(candidate, section_id)
            composition = candidate["post_production"]["sections_by_id"].setdefault(
                section_id, _new_composition()
            )
        _apply_selections(
            composition,
            args.get("selections"),
            project_id=project_id,
            command_id=request.client_command_id,
        )
        return

    if command in {
        CreatorCommandType.SET_SECTION_COMPOSE_TRANSITION,
        CreatorCommandType.SET_FINAL_COMPOSE_TRANSITION,
    }:
        composition = (
            candidate["post_production"].get("final")
            if command is CreatorCommandType.SET_FINAL_COMPOSE_TRANSITION
            else candidate["post_production"]["sections_by_id"].get(
                _target_id(request.target_ref, "post")
            )
        )
        if composition is None:
            raise ConflictError("请先保存 Compose selections")
        source_by_ref = {
            item["source_ref"]: selection_id
            for selection_id, item in composition["sequence"]["items"].items()
        }
        from_id = source_by_ref.get(str(args.get("fromSourceRef") or ""))
        to_id = source_by_ref.get(str(args.get("toSourceRef") or ""))
        if from_id is None or to_id is None:
            raise NotFoundError("Transition source selection 不存在")
        composition["transitions"] = [
            item
            for item in composition["transitions"]
            if not (
                item["from_selection_id"] == from_id
                and item["to_selection_id"] == to_id
            )
        ]
        composition["transitions"].append(
            {
                "from_selection_id": from_id,
                "to_selection_id": to_id,
                "kind": str(args.get("type") or "cut"),
                "duration_ms": max(0, round(float(args.get("durationSeconds") or 0) * 1000)),
            }
        )
        return

    if command is CreatorCommandType.IMPORT_SCRIPT:
        text = str(args.get("text") or "")
        candidate["story"]["outline"] = text
        imported = args.get("sections")
        if isinstance(imported, list) and imported:
            sections["items"] = {}
            sections["order"] = []
            for index, raw in enumerate(imported):
                if not isinstance(raw, dict):
                    continue
                section_id = _stable_id(
                    "section", project_id, request.client_command_id, str(index)
                )
                sections["items"][section_id] = {
                    "section_id": section_id,
                    "title": str(raw.get("title") or f"结构段 {index + 1}"),
                    "summary": str(raw.get("summary") or ""),
                    "narrative": str(raw.get("narrative") or ""),
                    "script": str(raw.get("script") or raw.get("text") or ""),
                    "voiceover": "",
                    "duration_budget_seconds": raw.get("durationBudget"),
                    "pacing": "",
                    "constraints": [],
                    "transition": "",
                    "units": {"items": {}, "order": []},
                }
                sections["order"].append(section_id)
        return

    # Remaining deterministic edit/asset compatibility commands are admitted
    # to the Agent so one model turn can update the nested Pydantic structure.
    raise ValidationError(f"尚未实现的 deterministic command: {command.value}")


def _validate_expected_versions(request: CreatorCommandRequest, etag: str) -> None:
    conflicts = [
        item.ref
        for item in request.expected_target_versions
        if f"project:{etag}:" not in item.object_version
    ]
    if conflicts:
        raise CasConflictError(
            "Command target 已被其他写者修改",
            details={"refs": conflicts, "currentEtag": etag},
        )


def _command_response(record: Any) -> dict[str, Any]:
    if not isinstance(record.response, dict):
        raise StorageIntegrityError("Command idempotency response 损坏")
    return record.response


def _apply_command_sync(
    services: CreatorFileServices,
    project_id: str,
    request: CreatorCommandRequest,
    key: str,
) -> dict[str, Any]:
    with services.projects.lifecycle_lock(project_id):
        base = services.projects.read(project_id)
        records = _idempotency(services, project_id)
        payload = request.model_dump(mode="json", by_alias=True)
        request_hash = records.request_hash(payload)
        with records.operation_lock(
            owner_id=project_id,
            scope="POST-commands",
            idempotency_key=key,
        ):
            reservation = records.reserve(
                owner_id=project_id,
                scope="POST-commands",
                idempotency_key=key,
                request_hash=request_hash,
                record_id=_stable_id("command", project_id, key),
            )
            if reservation.record.status is IdempotencyStatus.COMPLETED:
                return _command_response(reservation.record)
            if reservation.record.status is IdempotencyStatus.FAILED:
                raise StorageIntegrityError(
                    "上一次 Command 失败，请使用新的 Idempotency-Key 重试"
                )
            _validate_expected_versions(request, base.etag)
            candidate = base.project.model_dump(mode="json")
            _apply_deterministic(candidate, request, project_id=project_id)
            result = services.commits.commit(
                base=base,
                candidate=candidate,
                origin=ChangeOrigin.FRONTEND_EDIT,
                review_policy=ReviewPolicy.AUTO_FIX,
                caused_by_request_id=key,
                round_id=_stable_id("round", project_id, key),
                transaction_id=_stable_id("transaction", project_id, key),
                advance_accepted_baseline=True,
                _lifecycle_lock_held=True,
            )
            services.poller.note_commit(result.snapshot)
            # The Project snapshot poll is the authority for direct edits.
            # Do not enter SessionStore while holding the Project lifecycle
            # lock: SessionStore deliberately acquires that same lock before
            # its Runtime lock, so doing so would deadlock until timeout.
            body = {
                "commandId": request.client_command_id,
                "status": "APPLIED",
                "eventSeq": 0,
                "transactionId": result.transaction_id,
                "workingHead": result.snapshot.etag,
            }
            records.complete(
                owner_id=project_id,
                scope="POST-commands",
                idempotency_key=key,
                request_hash=request_hash,
                response=body,
                response_status=status.HTTP_202_ACCEPTED,
            )
            return body


def _queue_agent_command_sync(
    services: CreatorFileServices,
    project_id: str,
    request: CreatorCommandRequest,
    key: str,
) -> dict[str, Any]:
    # Reserve under the lifecycle lock so creating the idempotency directory
    # cannot race a Project deletion. Session admission then owns its normal
    # lifecycle/runtime locks without a recursive lock acquisition.
    with services.projects.lifecycle_lock(project_id):
        services.projects.read(project_id)
        records = _idempotency(services, project_id)
        request_payload = request.model_dump(mode="json", by_alias=True)
        request_hash = records.request_hash(request_payload)
        with records.operation_lock(
            owner_id=project_id,
            scope="POST-commands",
            idempotency_key=key,
        ):
            reservation = records.reserve(
                owner_id=project_id,
                scope="POST-commands",
                idempotency_key=key,
                request_hash=request_hash,
                record_id=_stable_id("command", project_id, key),
            )
            if reservation.record.status is IdempotencyStatus.COMPLETED:
                return _command_response(reservation.record)
            if reservation.record.status is IdempotencyStatus.FAILED:
                raise StorageIntegrityError(
                    "上一次 Command 失败，请使用新的 Idempotency-Key 重试"
                )

    session = services.sessions.get_project_session(project_id)
    conversations = services.sessions.list_conversations(project_id, session.session_id)
    conversation = next((item for item in conversations if item.is_default), conversations[0])
    instruction = (
        "执行 Creator semantic command。"
        f"\ncommand={request.type.value}"
        f"\ntargetRef={request.target_ref}"
        "\narguments="
        + json.dumps(request.arguments, ensure_ascii=False, sort_keys=True)
    )
    admitted = services.sessions.admit_user_request(
        project_id,
        session.session_id,
        conversation.conversation_id,
        request_id=key,
        client_message_id=request.client_command_id,
        content_parts=[{"type": "text", "text": instruction}],
        channel=MessageChannel.FRONTEND,
        classification=MessageClassification.WORKSPACE_COMMAND,
        source="frontend_command",
        metadata={"command": request.model_dump(mode="json", by_alias=True)},
    )
    refreshed = services.sessions.get_project_session(project_id)
    if refreshed.active_goal_id is None:
        services.sessions.create_goal(
            project_id,
            session.session_id,
            conversation.conversation_id,
            root_message_seq=admitted.message.message_seq,
            intent=instruction,
            goal_id=_stable_id("goal", project_id, key),
            metadata={"source": "frontend_command"},
        )
    events = services.sessions.list_events(
        project_id, session.session_id, after_seq=0, limit=None
    )
    event = next(
        (
            item
            for item in events
            if item.event_type == "command.queued"
            and item.message_id == admitted.message.message_id
        ),
        None,
    )
    if event is None:
        event = services.sessions.append_event(
            project_id,
            session.session_id,
            event_type="command.queued",
            actor="frontend",
            message_id=admitted.message.message_id,
            payload={
                "commandId": request.client_command_id,
                "messageSeq": admitted.message.message_seq,
                "type": request.type.value,
            },
        )
    body = {
        "commandId": request.client_command_id,
        "status": "QUEUED",
        "eventSeq": event.event_seq,
        "messageSeq": admitted.message.message_seq,
    }
    with services.projects.lifecycle_lock(project_id):
        services.projects.read(project_id)
        records.complete(
            owner_id=project_id,
            scope="POST-commands",
            idempotency_key=key,
            request_hash=request_hash,
            response=body,
            response_status=status.HTTP_202_ACCEPTED,
        )
    return body


def _translate(error: BaseException) -> None:
    if isinstance(error, ProjectNotFound):
        raise NotFoundError("Project 不存在") from error
    if isinstance(error, IdempotencyConflictError):
        raise ConflictError("Idempotency-Key 已用于不同的 Command") from error
    if isinstance(error, IdempotencyStateConflictError):
        raise ConflictError("Command idempotency 状态冲突") from error
    if isinstance(error, ProjectCommitError):
        raise ConflictError(str(error)) from error
    if isinstance(error, (ProjectStoreError, SessionStoreError)):
        raise StorageIntegrityError(str(error)) from error
    raise error


@router.post(
    "/commands",
    response_model=CreatorCommandAccepted,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_command(
    project_id: str,
    payload: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    services: CreatorFileServices = Depends(project_file_services),
) -> dict[str, Any]:
    try:
        request = CreatorCommandRequest.model_validate(payload)
    except PydanticValidationError as error:
        raise BadRequestError(
            "semantic command 请求不合法",
            details={"validationErrors": error.errors(include_url=False)},
        ) from error
    key = resolve_idempotency_key(
        idempotency_key, stable_client_id=request.client_command_id
    )
    try:
        if request.type is CreatorCommandType.ANALYZE_SOURCE_MEDIA:
            dispatch = await source_analysis_service(services).dispatch(
                project_id=project_id,
                target_ref=request.target_ref,
                command_id=key,
                arguments=request.arguments,
                start=True,
            )
            return {
                "commandId": request.client_command_id,
                "status": "QUEUED",
                "eventSeq": 0,
                "transactionId": dispatch.job.round_id,
                "workingHead": dispatch.job.input_etag,
            }
        if request.type in _IMAGE_FILE_COMMANDS:
            execution = await execute_file_image_command(
                services,
                project_id=project_id,
                command=request.type,
                target_ref=request.target_ref,
                arguments=request.arguments,
                idempotency_key=key,
                expected_object_versions=[
                    item.object_version for item in request.expected_target_versions
                ],
            )
            return execution.command_response(request.client_command_id)
        if request.type in _LOCAL_MEDIA_FILE_COMMANDS:
            execution = await execute_file_local_media_command(
                services,
                project_id=project_id,
                command=request.type,
                target_ref=request.target_ref,
                arguments=request.arguments,
                idempotency_key=key,
                expected_object_versions=[
                    item.object_version for item in request.expected_target_versions
                ],
            )
            return execution.command_response(request.client_command_id)
        if request.type in _R2V_FILE_COMMANDS:
            execution = await execute_file_r2v_command(
                services,
                project_id=project_id,
                target_ref=request.target_ref,
                arguments=request.arguments,
                idempotency_key=key,
                expected_object_versions=[
                    item.object_version for item in request.expected_target_versions
                ],
            )
            return execution.command_response(request.client_command_id)
        if request.type in _AGENT_COMMANDS:
            result = await asyncio.to_thread(
                _queue_agent_command_sync,
                services,
                project_id,
                request,
                key,
            )
            notify_creator_agent_runtime(project_id)
            return result
        return await asyncio.to_thread(
            _apply_command_sync,
            services,
            project_id,
            request,
            key,
        )
    except BaseException as error:
        _translate(error)


__all__ = ["router"]
