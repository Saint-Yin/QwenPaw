import type { ExpectedTargetVersion } from './common';

export type CreatorCommandType =
  | 'GENERATE_SCRIPT'
  | 'IMPORT_SCRIPT'
  | 'SET_STRATEGY_TEXT'
  | 'SET_SECTION_TEXT'
  | 'SET_UNIT_TEXT'
  | 'PLAN_UNITS'
  | 'CREATE_SECTION'
  | 'DELETE_SECTION'
  | 'MOVE_SECTION'
  | 'CREATE_UNIT'
  | 'DELETE_UNIT'
  | 'MOVE_UNIT'
  | 'CHANGE_UNIT_ROUTE'
  | 'UPSERT_SHOT'
  | 'DELETE_SHOT'
  | 'MOVE_SHOT'
  | 'BIND_REFERENCE'
  | 'UNBIND_REFERENCE'
  | 'GENERATE_STORYBOARD_PROMPT'
  | 'GENERATE_STORYBOARD_IMAGE'
  | 'GENERATE_VIDEO_PROMPT'
  | 'GENERATE_R2V_VIDEO'
  | 'BUILD_EDIT_PLAN'
  | 'EXECUTE_EDIT'
  | 'SET_EDIT_CLIP_RANGE'
  | 'SET_EDIT_CLIP_OS'
  | 'SET_EDIT_CLIP_TRANSITION'
  | 'MOVE_EDIT_CLIP'
  | 'DELETE_EDIT_CLIP'
  | 'SET_EDIT_AUDIO_PLAN'
  | 'ATTACH_SOURCE_ASSETS'
  | 'DETACH_SOURCE_ASSETS'
  | 'SUPPLEMENT_ASSET'
  | 'GENERATE_ASSET'
  | 'SELECT_ARTIFACT_VERSION'
  | 'SET_SECTION_COMPOSE_SELECTION'
  | 'SET_SECTION_COMPOSE_TRANSITION'
  | 'STITCH_SECTION'
  | 'SET_FINAL_COMPOSE_SELECTION'
  | 'SET_FINAL_COMPOSE_TRANSITION'
  | 'COMPOSE_FINAL_VIDEO'
  | 'ANALYZE_SOURCE_MEDIA';

export interface CreatorCommand {
  clientCommandId: string;
  editSessionId?: string;
  type: CreatorCommandType;
  targetRef: string;
  arguments: Record<string, unknown>;
  context?: Record<string, unknown>;
  expectedTargetVersions: ExpectedTargetVersion[];
  expectedPresentationVersion?: string;
  expectedDecisionToken?: string;
  expectedOverlayHead?: string;
}

export interface CreatorCommandAccepted {
  commandId: string;
  status:
    | 'RECEIVED'
    | 'APPLIED'
    | 'QUEUED'
    | 'DEFERRED_UNTIL_REVIEW_RESOLVED'
    | 'CONSUMED'
    | 'REJECTED';
  eventSeq: number;
  transactionId?: string;
  messageSeq?: number;
  workingHead?: string;
}
