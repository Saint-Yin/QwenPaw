import type { UiPhase, UnitTaskType } from './common';
import type { ReviewManifest } from './reviews';
import type { ResolvedRef } from './refs';

export interface CreatorTaskProgress {
  goalId?: string;
  phase:
    | 'source_ingest'
    | 'source_intelligence'
    | 'creative_strategy'
    | 'story_planning'
    | 'visual_development'
    | 'unit_planning'
    | 'unit_production'
    | 'post_production'
    | 'review'
    | 'completed';
  label: string;
  latestMilestone?: string;
  completed?: number;
  total?: number;
  sectionId?: string;
  unitId?: string;
  sourceEventSeq: number;
  updatedAt: string;
}

export interface AgentStatusBarView {
  progress: CreatorTaskProgress;
  activity?: { label: string; runningTaskCount: number };
  badges: Array<{
    kind: 'execution_authorization' | 'review' | 'manual_edits_queued' | 'error';
    label: string;
    count?: number;
    actionTarget?: string;
  }>;
}

export interface ViewEnvelope<T> {
  projectId: string;
  approvedRevisionId: string;
  workingBranchId?: string | null;
  workingHead?: string | null;
  reviewRevisionId?: string | null;
  activeTransactionId?: string | null;
  uiPhase: UiPhase;
  manualEditOverlay?: { id: string; head: string; mutationCount: number } | null;
  agentStatusBar: AgentStatusBarView;
  view: T | ReviewPresentationView<T>;
}

export interface ReviewPresentationView<T> {
  presentationVersion: string;
  reviewRevisionId: string;
  approvedRevisionId: string;
  overlayId?: string;
  overlayHead?: string;
  view: T;
  origins: Record<string, 'approved' | 'review_candidate' | 'user_overlay'>;
  targetVersions: Record<string, { targetVersion: string; decisionGroupId?: string; decisionToken?: string }>;
}

export type ShotCamera =
  | '⊙ 静止'
  | '↑ 推近'
  | '↓ 拉远'
  | '→ 横摇右'
  | '← 横摇左'
  | '↕ 升降'
  | '◎ 环绕'
  | '～ 手持晃动';

export type ShotFraming = '全景' | '中景' | '近景' | '特写';

export interface ShotView {
  id: string;
  number: number;
  description: string;
  camera: ShotCamera;
  framing: ShotFraming;
  cameraDescription?: string;
  dialogue?: string;
  duration: number;
  targetVersion: string;
}

export interface GenerationUnitView {
  id: string;
  number: number;
  title?: string;
  taskType: UnitTaskType;
  duration: number;
  storyboardPrompt?: string;
  storyboardImageUrl?: string | null;
  storyboardImageVersionId?: string | null;
  videoPrompt?: string;
  videoUrl?: string | null;
  shots: ShotView[];
  sceneRef?: string;
  characterRefs: string[];
  propRefs: string[];
  materialRefs: string[];
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  readiness: { ready: boolean; blockers: string[] };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
}

export interface SectionView {
  id: string;
  number: number;
  title: string;
  narrative?: string;
  durationBudget?: number;
  constraints: string[];
  script?: string;
  units: GenerationUnitView[];
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  targetVersions: Record<string, string>;
  targetVersion: string;
  readiness: { ready: boolean; blockers: string[] };
  blockers: string[];
  uiLocator: Record<string, string>;
}

export interface PlanView {
  title: string;
  outline?: string;
  aspectRatio: string;
  targetDuration?: number;
  sections: SectionView[];
  relations: Array<Record<string, string>>;
  resolvedRefs: ResolvedRef[];
  readiness: { ready: boolean };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
}

export interface ArtifactVersionView {
  id: string;
  name: string;
  slotId: string;
  kind: string;
  url: string;
  checksum: string;
  durationSeconds?: number;
  createdAt: string;
  provenanceRefs: string[];
  selected: boolean;
  freshnessStatus?: 'current' | 'stale';
  staleReason?: string | null;
  reviewOperationId?: string;
  artifactVersionId: string;
  sourceRef: string;
  basedOnRevisionId: string;
  inputFingerprint?: string;
  ownerRef: string;
  sectionId?: string;
  sourceKind?: 'section' | 'unit';
  uiLocator: Record<string, string>;
}

export interface R2VWorkbenchView {
  kind: 'r2v';
  unit: GenerationUnitView;
  storyboardPrompt: string;
  videoPrompt: string;
  storyboardVersions: ArtifactVersionView[];
  videoVersions: ArtifactVersionView[];
  selectedStoryboardVersionId?: string | null;
  selectedVideoVersionId?: string | null;
  storyboardInputRefs?: string[];
  videoInputRefs?: string[];
  inputReferenceBindings: Array<{
    sourceRef: string;
    field: 'scene' | 'characters' | 'props' | 'sources';
    referenceSets: Array<'storyboard' | 'video'>;
  }>;
  providerConstraints: {
    provider: string;
    minDuration: number;
    maxDuration: number;
    maxReferenceImages: number;
    model: string;
    version: string;
    capturedAt: string;
    allowedDurations: number[];
  };
  continuity: string;
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  readiness: { ready: boolean };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
  selectionSource: { revisionId: string; storyboardSlotId?: string | null };
}

export interface EditWorkbenchView {
  kind: 'edit';
  unit: GenerationUnitView;
  goal?: string;
  plan: AiEditPlan | null;
  storyboard_image_url: string | null;
  material_assets: AiEditMaterialAsset[];
  workflow_trace: Array<Record<string, unknown>>;
  videoVersions: ArtifactVersionView[];
  planVersion?: { id: string; checksum: string; createdAt: string } | null;
  planRef?: string | null;
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  readiness: { ready: boolean; blockers?: string[] };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
  previousUnitLastClipEnd?: number | null;
  nextUnitFirstClipStart?: number | null;
}

export interface AiEditTimelineClip {
  clip_id: string;
  asset_id: string;
  asset_name?: string;
  source_url?: string;
  asset_version_id?: string;
  start: number;
  end: number;
  duration: number;
  order: number;
  transition?: string;
  reason?: string;
  overlay_copy?: {
    kind: 'pet_os' | 'interview_summary';
    text: string;
    vibe?: 'action' | 'surprise' | 'curious' | 'chill' | string;
    appear_at: number;
    duration: number;
  };
}

export interface AiEditStoryboardPanel {
  panel_id: string;
  clip_id?: string;
  order: number;
  title: string;
  description: string;
  source_asset_id: string;
  timestamp: number;
  timeline_start?: number;
  timeline_end?: number;
  image_url?: string;
}

export interface AiEditPlan {
  summary?: string;
  target_duration?: number;
  timeline?: AiEditTimelineClip[];
  storyboard?: AiEditStoryboardPanel[];
  storyboard_image_url?: string;
  audio_plan?: Record<string, unknown>;
  model?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AiEditMaterialAsset {
  id?: string;
  name?: string;
  url?: string;
  duration?: number;
  [key: string]: unknown;
}

export interface IngestItemView {
  taskId: string;
  assetId?: string | null;
  assetVersionId?: string | null;
  name: string;
  status: string;
  progress?: number | null;
  error?: string | null;
}

export interface AttachedSourceView {
  assetId: string;
  assetVersionId: string;
  sourceRef: string;
  name: string;
  category: 'upload';
  existence: 'available';
  presentationStatus: 'accepted';
  sourceLabel: string;
  mediaType?: string;
  checksum?: string;
  thumbnailUrl?: string;
  userNotes?: string;
  understandingRef?: string | null;
  referenceCount: number;
  createdAt?: string;
  targetVersion: string;
  uiLocator: Record<string, string>;
}

export interface AvailableAssetView {
  assetId: string;
  assetVersionId: string;
  sourceRef: string;
  name: string;
  category: 'upload';
  existence: 'available';
  presentationStatus: 'draft' | 'accepted';
  mediaType: string;
  checksum: string;
  url: string;
  thumbnailUrl?: string;
  durationSeconds?: number;
  objectVersion: string;
  createdAt: string;
  referenceCount: number;
  attached: boolean;
  uiLocator: Record<string, string>;
}

export interface VisualAssetView {
  id: string;
  name: string;
  category: 'character' | 'scene' | 'prop';
  selectedRef?: string | null;
  resolvedRef?: ResolvedRef | null;
  description?: string;
  existence: 'planned' | 'available';
  presentationStatus: 'draft' | 'accepted';
  mediaType: string;
  assetVersionId?: string | null;
  artifactVersionId?: string | null;
  url?: string | null;
  thumbnailUrl?: string | null;
  referenceRefs: string[];
  referenceCount: number;
  uiLocator: Record<string, string>;
}

export interface AssetDetailImageView {
  id: string;
  name: string;
  url?: string;
  description?: string;
  facetKind?: 'front_anchor' | 'expression' | 'costume' | 'pose' | 'profile' | 'multi_angle' | 'usage_state' | 'interaction_pose' | 'unknown';
}

/** Complete Assets drawer projection; every value comes from the Assets View. */
export interface AssetDetailView {
  id: string;
  name: string;
  kind: 'character' | 'scene' | 'prop' | 'material';
  description?: string;
  role?: 'protagonist' | 'supporting' | 'extra';
  mediaType?: 'image' | 'video' | 'audio';
  primaryUrl?: string;
  images: AssetDetailImageView[];
  refsNeeded: string[];
  prompts: string[];
  referenceImageRefs: string[][];
}

/** Read-only unified projection used to preserve the origin/main Assets grid. */
export interface PresentationAssetView {
  id: string;
  name: string;
  category: 'upload' | 'subject_ref' | 'env_ref' | 'brand_constraint' | 'understanding' | 'generated';
  existence: 'planned' | 'available';
  presentationStatus: 'draft' | 'pending' | 'accepted' | 'stale';
  mediaType?: string;
  url?: string | null;
  thumbnailUrl?: string | null;
  description?: string;
  sourceDescription: string;
  sourceRef?: string | null;
  referenceCount: number;
  generatedKind?: 'storyboard_image' | 'unit_video' | 'section_video' | string;
  ownerRef?: string;
  artifactVersionId?: string;
  targetVersion?: string;
  assetVersionId?: string;
  checksum?: string;
  durationSeconds?: number;
  userNotes?: string;
  detail?: AssetDetailView;
  uiLocator: Record<string, string>;
}

export interface AssetLibraryView {
  attachedSources: AttachedSourceView[];
  ingestItems: IngestItemView[];
  availableAssets: AvailableAssetView[];
  visualAssets: VisualAssetView[];
  presentationAssets: PresentationAssetView[];
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  readiness: { ready: boolean };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
}

export interface ComposeSelectionView {
  sourceRef: string;
  sourceKind?: 'section' | 'unit';
  artifactRef: string;
  artifactVersionId: string;
  slotId: string;
  order: number;
  uiLocator: Record<string, string>;
}

export interface ComposeView {
  kind: 'section' | 'final';
  sectionId?: string;
  sectionNumber?: number;
  sectionTitle?: string;
  sections?: Array<{ id: string; number: number; title: string }>;
  selections: ComposeSelectionView[];
  candidates: ArtifactVersionView[];
  transitions: Array<{ path: string; value: string }>;
  audioPlan?: string;
  mix?: string;
  subtitlesVtt?: string;
  renderedVideoRef?: string | null;
  renderedVideoUrl?: string | null;
  resolvedRefs: ResolvedRef[];
  relations: Array<Record<string, string>>;
  readiness: { ready: boolean };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
}

export interface ReviewView {
  manifest: ReviewManifest;
}
