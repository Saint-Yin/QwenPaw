# -*- coding: utf-8 -*-
"""Single-source string enums shared by runtime, API and tests."""

from __future__ import annotations

from enum import StrEnum


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


class SpecialistRole(StrEnum):
    SOURCE_INTELLIGENCE = "source_intelligence_agent"
    STORY_PLANNING = "story_planning_agent"
    VISUAL_DEVELOPMENT = "visual_development_agent"
    UNIT_PLANNING_ROUTING = "unit_planning_routing_agent"
    R2V_GENERATION_DIRECTOR = "r2v_generation_director"
    AI_EDITING_DIRECTOR = "ai_editing_director"
    REVIEW_CONSISTENCY = "review_consistency_agent"


class CreatorSessionStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_RUNTIME = "WAITING_RUNTIME"
    INTERRUPT_REQUESTED = "INTERRUPT_REQUESTED"
    WAITING_USER_INPUT = "WAITING_USER_INPUT"
    WAITING_EXECUTION_AUTH = "WAITING_EXECUTION_AUTH"
    PENDING_REVIEW = "PENDING_REVIEW"
    RESUMING = "RESUMING"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class CreatorGoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    WAITING_REVIEW = "WAITING_REVIEW"
    RESUME_REQUIRED = "RESUME_REQUIRED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TransactionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETION_CHECK = "COMPLETION_CHECK"
    SEALING = "SEALING"
    PENDING_REVIEW = "PENDING_REVIEW"
    REVISING = "REVISING"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    NO_CHANGE = "NO_CHANGE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class SpecialistRunStatus(StrEnum):
    QUEUED = "QUEUED"
    QUEUED_CAPACITY = "QUEUED_CAPACITY"
    RUNNING_MODEL = "RUNNING_MODEL"
    WAITING_RUNTIME = "WAITING_RUNTIME"
    WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


TERMINAL_SPECIALIST_STATUSES = frozenset(
    {
        SpecialistRunStatus.SUCCEEDED,
        SpecialistRunStatus.BLOCKED,
        SpecialistRunStatus.FAILED,
        SpecialistRunStatus.STALE,
        SpecialistRunStatus.CANCELLED,
    },
)


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"


class TaskKind(StrEnum):
    ASSET_INGEST = "asset_ingest"
    ASSET_IMPORT = "asset_import"
    SOURCE_INTELLIGENCE = "source_intelligence"
    IMAGE_GENERATION = "image_generation"
    R2V_GENERATION = "r2v_generation"
    AI_EDIT_PLAN = "ai_edit_plan"
    AI_EDIT_EXECUTE = "ai_edit_execute"
    COMPOSE = "compose"


class ReviewDecision(StrEnum):
    PENDING = "PENDING"
    ACCEPTED_APPLIED = "ACCEPTED_APPLIED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    SUPERSEDED_BY_USER_EDIT = "SUPERSEDED_BY_USER_EDIT"
    CARRIED_FORWARD_TO_NEXT_ROUND = "CARRIED_FORWARD_TO_NEXT_ROUND"


class ReviewDecisionCommand(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVISE = "REVISE"


class UiPhase(StrEnum):
    IDLE = "idle"
    EXECUTING = "executing"
    INTERRUPTING = "interrupting"
    WAITING_INPUT = "waiting_input"
    WAITING_AUTHORIZATION = "waiting_authorization"
    FINALIZING = "finalizing"
    WAITING_REVIEW = "waiting_review"
    RESUMING = "resuming"
    CANCELLED = "cancelled"
    ERROR = "error"


class CreatorProgressPhase(StrEnum):
    SOURCE_INGEST = "source_ingest"
    SOURCE_INTELLIGENCE = "source_intelligence"
    CREATIVE_STRATEGY = "creative_strategy"
    STORY_PLANNING = "story_planning"
    VISUAL_DEVELOPMENT = "visual_development"
    UNIT_PLANNING = "unit_planning"
    UNIT_PRODUCTION = "unit_production"
    POST_PRODUCTION = "post_production"
    REVIEW = "review"
    COMPLETED = "completed"


class CreatorCommandType(StrEnum):
    GENERATE_SCRIPT = "GENERATE_SCRIPT"
    IMPORT_SCRIPT = "IMPORT_SCRIPT"
    SET_STRATEGY_TEXT = "SET_STRATEGY_TEXT"
    SET_SECTION_TEXT = "SET_SECTION_TEXT"
    SET_UNIT_TEXT = "SET_UNIT_TEXT"
    PLAN_UNITS = "PLAN_UNITS"
    CREATE_SECTION = "CREATE_SECTION"
    DELETE_SECTION = "DELETE_SECTION"
    MOVE_SECTION = "MOVE_SECTION"
    CREATE_UNIT = "CREATE_UNIT"
    DELETE_UNIT = "DELETE_UNIT"
    MOVE_UNIT = "MOVE_UNIT"
    CHANGE_UNIT_ROUTE = "CHANGE_UNIT_ROUTE"
    UPSERT_SHOT = "UPSERT_SHOT"
    DELETE_SHOT = "DELETE_SHOT"
    MOVE_SHOT = "MOVE_SHOT"
    BIND_REFERENCE = "BIND_REFERENCE"
    UNBIND_REFERENCE = "UNBIND_REFERENCE"
    GENERATE_STORYBOARD_PROMPT = "GENERATE_STORYBOARD_PROMPT"
    GENERATE_STORYBOARD_IMAGE = "GENERATE_STORYBOARD_IMAGE"
    GENERATE_VIDEO_PROMPT = "GENERATE_VIDEO_PROMPT"
    GENERATE_R2V_VIDEO = "GENERATE_R2V_VIDEO"
    BUILD_EDIT_PLAN = "BUILD_EDIT_PLAN"
    EXECUTE_EDIT = "EXECUTE_EDIT"
    SET_EDIT_CLIP_RANGE = "SET_EDIT_CLIP_RANGE"
    SET_EDIT_CLIP_OS = "SET_EDIT_CLIP_OS"
    SET_EDIT_CLIP_TRANSITION = "SET_EDIT_CLIP_TRANSITION"
    MOVE_EDIT_CLIP = "MOVE_EDIT_CLIP"
    DELETE_EDIT_CLIP = "DELETE_EDIT_CLIP"
    SET_EDIT_AUDIO_PLAN = "SET_EDIT_AUDIO_PLAN"
    ATTACH_SOURCE_ASSETS = "ATTACH_SOURCE_ASSETS"
    DETACH_SOURCE_ASSETS = "DETACH_SOURCE_ASSETS"
    SUPPLEMENT_ASSET = "SUPPLEMENT_ASSET"
    GENERATE_ASSET = "GENERATE_ASSET"
    SELECT_ARTIFACT_VERSION = "SELECT_ARTIFACT_VERSION"
    SET_SECTION_COMPOSE_SELECTION = "SET_SECTION_COMPOSE_SELECTION"
    SET_SECTION_COMPOSE_TRANSITION = "SET_SECTION_COMPOSE_TRANSITION"
    STITCH_SECTION = "STITCH_SECTION"
    SET_FINAL_COMPOSE_SELECTION = "SET_FINAL_COMPOSE_SELECTION"
    SET_FINAL_COMPOSE_TRANSITION = "SET_FINAL_COMPOSE_TRANSITION"
    COMPOSE_FINAL_VIDEO = "COMPOSE_FINAL_VIDEO"
    ANALYZE_SOURCE_MEDIA = "ANALYZE_SOURCE_MEDIA"


DETERMINISTIC_COMMANDS = frozenset(
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
    },
)
