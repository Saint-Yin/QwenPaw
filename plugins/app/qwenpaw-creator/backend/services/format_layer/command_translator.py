"""Translate the 42 semantic UI commands without executing or choosing a Specialist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from domain.enums import DETERMINISTIC_COMMANDS, CreatorCommandType, UiPhase
from domain.errors import PhaseConflictError, ValidationError
from domain.refs import parse_target_ref, validate_workspace_ref
from schemas.commands import CreatorCommandRequest

CommandLane = Literal["deterministic_mutation", "creator_action"]
CommandPhaseState = Literal["APPLY", "QUEUE_FOR_BOUNDARY", "DEFERRED_UNTIL_REVIEW_RESOLVED"]

_COALESCED = frozenset(
    {
        CreatorCommandType.SET_STRATEGY_TEXT,
        CreatorCommandType.SET_SECTION_TEXT,
        CreatorCommandType.SET_UNIT_TEXT,
        CreatorCommandType.SET_EDIT_AUDIO_PLAN,
    }
)

_DESCRIPTIONS: dict[CreatorCommandType, str] = {
    CreatorCommandType.GENERATE_SCRIPT: "生成项目脚本并完成必要关联修改",
    CreatorCommandType.IMPORT_SCRIPT: "导入用户脚本",
    CreatorCommandType.SET_STRATEGY_TEXT: "修改创作策略文本",
    CreatorCommandType.SET_SECTION_TEXT: "修改 Section 文本",
    CreatorCommandType.SET_UNIT_TEXT: "修改 Unit 文本",
    CreatorCommandType.PLAN_UNITS: "规划 Unit 及生产路由",
    CreatorCommandType.CREATE_SECTION: "创建 Section",
    CreatorCommandType.DELETE_SECTION: "删除 Section 并闭合引用",
    CreatorCommandType.MOVE_SECTION: "移动 Section",
    CreatorCommandType.CREATE_UNIT: "创建 Unit",
    CreatorCommandType.DELETE_UNIT: "删除 Unit 并闭合引用",
    CreatorCommandType.MOVE_UNIT: "移动 Unit",
    CreatorCommandType.CHANGE_UNIT_ROUTE: "切换 Unit 生产路由并处理关联内容",
    CreatorCommandType.UPSERT_SHOT: "保存 Shot",
    CreatorCommandType.DELETE_SHOT: "删除 Shot",
    CreatorCommandType.MOVE_SHOT: "移动 Shot",
    CreatorCommandType.BIND_REFERENCE: "绑定版本化引用",
    CreatorCommandType.UNBIND_REFERENCE: "解除版本化引用",
    CreatorCommandType.GENERATE_STORYBOARD_PROMPT: "生成 R2V 分镜 Prompt",
    CreatorCommandType.GENERATE_STORYBOARD_IMAGE: "生成 R2V 分镜图",
    CreatorCommandType.GENERATE_VIDEO_PROMPT: "生成 R2V 视频 Prompt",
    CreatorCommandType.GENERATE_R2V_VIDEO: "生成 R2V 视频",
    CreatorCommandType.BUILD_EDIT_PLAN: "构建 AI Edit 计划",
    CreatorCommandType.EXECUTE_EDIT: "执行 AI Edit 计划",
    CreatorCommandType.SET_EDIT_CLIP_RANGE: "修改剪辑片段时间范围",
    CreatorCommandType.SET_EDIT_CLIP_OS: "修改剪辑片段 OS",
    CreatorCommandType.SET_EDIT_CLIP_TRANSITION: "修改剪辑片段转场",
    CreatorCommandType.MOVE_EDIT_CLIP: "移动剪辑片段",
    CreatorCommandType.DELETE_EDIT_CLIP: "删除剪辑片段",
    CreatorCommandType.SET_EDIT_AUDIO_PLAN: "修改剪辑音频计划",
    CreatorCommandType.ATTACH_SOURCE_ASSETS: "挂载指定素材版本",
    CreatorCommandType.DETACH_SOURCE_ASSETS: "解除指定素材版本",
    CreatorCommandType.SUPPLEMENT_ASSET: "补充视觉资产",
    CreatorCommandType.GENERATE_ASSET: "生成视觉资产",
    CreatorCommandType.SELECT_ARTIFACT_VERSION: "选择明确 Artifact Version",
    CreatorCommandType.SET_SECTION_COMPOSE_SELECTION: "选择 Section 合成版本",
    CreatorCommandType.SET_SECTION_COMPOSE_TRANSITION: "修改 Section 合成转场",
    CreatorCommandType.STITCH_SECTION: "合成 Section 视频",
    CreatorCommandType.SET_FINAL_COMPOSE_SELECTION: "选择 Final 合成版本",
    CreatorCommandType.SET_FINAL_COMPOSE_TRANSITION: "修改 Final 合成转场",
    CreatorCommandType.COMPOSE_FINAL_VIDEO: "合成最终视频",
    CreatorCommandType.ANALYZE_SOURCE_MEDIA: "理解指定源素材",
}


@dataclass(frozen=True, slots=True)
class CommandDisposition:
    lane: CommandLane
    phase_state: CommandPhaseState
    description: str
    target_refs: tuple[str, ...]
    requires_manual_edit_outbox: bool
    coalesce_key: str | None
    payload: dict[str, Any]


def _validate_version_refs(command: CreatorCommandRequest) -> None:
    for key in ("assetVersionRefs", "artifactVersionRefs", "sourceRefs"):
        values = command.arguments.get(key, [])
        if values is None:
            continue
        if not isinstance(values, list):
            raise ValidationError(f"{key} 必须是数组")
        for ref in values:
            validate_workspace_ref(str(ref))
    if command.type in {CreatorCommandType.ATTACH_SOURCE_ASSETS, CreatorCommandType.DETACH_SOURCE_ASSETS}:
        refs = command.arguments.get("assetVersionRefs")
        if not isinstance(refs, list) or not refs:
            raise ValidationError("attach/detach 必须携带非空 exact assetVersionRefs")
        if any(not str(ref).startswith("asset://") for ref in refs):
            raise ValidationError("attach/detach 只能使用不可变 asset:// version refs")
    if command.type == CreatorCommandType.CHANGE_UNIT_ROUTE:
        route = command.arguments.get("taskType")
        if route not in {"r2v", "edit"}:
            raise ValidationError("CHANGE_UNIT_ROUTE 的 taskType 只能是 r2v 或 edit")
    if command.type == CreatorCommandType.SUPPLEMENT_ASSET:
        operation = command.arguments.get("operation")
        target = parse_target_ref(command.target_ref)
        if operation == "create":
            if target != parse_target_ref("project:assets"):
                raise ValidationError("新建资产必须以 project:assets 为 target")
            asset_kind = command.arguments.get("assetKind")
            if asset_kind == "material":
                raise ValidationError("素材必须通过 Asset ingest 创建")
            if asset_kind not in {"character", "scene", "prop"}:
                raise ValidationError("新建资产的 assetKind 不合法")
            if not str(command.arguments.get("name") or "").strip():
                raise ValidationError("新建资产必须携带 name")
        elif operation == "delete":
            if target.kind != "asset":
                raise ValidationError("删除视觉资产必须以 asset:<id> 为 target")
        elif operation is None:
            if target.kind != "asset":
                raise ValidationError("视觉资产字段修改必须以 asset:<id> 为 target")
            field = command.arguments.get("field")
            if field not in {
                "name",
                "description",
                "promptConfig",
                "image",
                "appearance",
                "appearancePrompt",
            }:
                raise ValidationError("SUPPLEMENT_ASSET field 不受支持")
        else:
            raise ValidationError("SUPPLEMENT_ASSET operation 只能是 create 或 delete")


def _description(command: CreatorCommandRequest) -> str:
    base = _DESCRIPTIONS[command.type]
    if command.type != CreatorCommandType.SUPPLEMENT_ASSET:
        return base
    operation = command.arguments.get("operation")
    if operation == "create":
        labels = {"character": "角色", "scene": "场景", "prop": "道具", "material": "素材"}
        kind = str(command.arguments["assetKind"])
        name = str(command.arguments["name"]).strip()
        return f"新建{labels[kind]}资产「{name}」"
    if operation == "delete":
        return "删除指定视觉资产并闭合所有引用"
    return base


def translate_command(command: CreatorCommandRequest, *, ui_phase: UiPhase | str) -> CommandDisposition:
    phase = UiPhase(str(ui_phase))
    parse_target_ref(command.target_ref)
    _validate_version_refs(command)
    lane: CommandLane = "deterministic_mutation" if command.type in DETERMINISTIC_COMMANDS else "creator_action"

    if lane == "deterministic_mutation" and not command.expected_target_versions:
        raise ValidationError("deterministic command 必须携带 expectedTargetVersions CAS")
    if phase in {UiPhase.INTERRUPTING, UiPhase.CANCELLED, UiPhase.ERROR}:
        raise PhaseConflictError(f"{phase.value} 阶段不接受新的 semantic command")
    if phase == UiPhase.FINALIZING:
        phase_state = "QUEUE_FOR_BOUNDARY"
    elif phase == UiPhase.WAITING_REVIEW:
        if lane == "creator_action":
            phase_state: CommandPhaseState = "DEFERRED_UNTIL_REVIEW_RESOLVED"
        else:
            has_first_write_token = bool(command.expected_presentation_version)
            has_overlay_token = bool(command.expected_overlay_head)
            if not (has_first_write_token or has_overlay_token):
                raise ValidationError("Pending 手动编辑必须携带 presentationVersion 或 overlayHead")
            phase_state = "APPLY"
    elif lane == "creator_action" and phase in {
        UiPhase.EXECUTING,
        UiPhase.WAITING_AUTHORIZATION,
        UiPhase.RESUMING,
    }:
        phase_state = "QUEUE_FOR_BOUNDARY"
    else:
        phase_state = "APPLY"

    coalesce_key = None
    if command.type in _COALESCED:
        if not command.edit_session_id:
            raise ValidationError("可合并文本编辑必须携带 editSessionId")
        field = (
            "audio_plan"
            if command.type == CreatorCommandType.SET_EDIT_AUDIO_PLAN
            else str(command.arguments.get("field") or "value")
        )
        coalesce_key = json.dumps(
            [command.edit_session_id, command.target_ref, field],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return CommandDisposition(
        lane=lane,
        phase_state=phase_state,
        description=_description(command),
        target_refs=(command.target_ref,),
        requires_manual_edit_outbox=lane == "deterministic_mutation",
        coalesce_key=coalesce_key,
        payload=command.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


if set(_DESCRIPTIONS) != set(CreatorCommandType):
    raise RuntimeError("Every Creator command must have one product-semantic description")
