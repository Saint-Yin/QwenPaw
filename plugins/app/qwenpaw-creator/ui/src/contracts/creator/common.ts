export type UnitTaskType = 'r2v' | 'edit';

export type UiPhase =
  | 'idle'
  | 'executing'
  | 'interrupting'
  | 'waiting_input'
  | 'waiting_authorization'
  | 'finalizing'
  | 'waiting_review'
  | 'resuming'
  | 'cancelled'
  | 'error';

export type SpecialistRole =
  | 'source_intelligence_agent'
  | 'story_planning_agent'
  | 'visual_development_agent'
  | 'unit_planning_routing_agent'
  | 'r2v_generation_director'
  | 'ai_editing_director'
  | 'review_consistency_agent';

export interface ExpectedTargetVersion {
  ref: string;
  objectVersion: string;
}

export interface CreatorApiError {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}
