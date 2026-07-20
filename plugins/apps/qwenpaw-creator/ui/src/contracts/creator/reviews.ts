export type ReviewDecisionState =
  | "PENDING"
  | "ACCEPTED_APPLIED"
  | "REJECTED"
  | "REVISION_REQUESTED"
  | "SUPERSEDED_BY_USER_EDIT"
  | "CARRIED_FORWARD_TO_NEXT_ROUND";

export interface ReviewOperation {
  id: string;
  decisionGroupId: string;
  mutationIds: string[];
  kind:
    | "create"
    | "update"
    | "delete"
    | "move"
    | "rename"
    | "replace_media"
    | "change_reference";
  targetRef: string;
  artifactKind: string;
  path?: string;
  beforeVersionRef?: string;
  afterVersionRef?: string;
  causalRefs: string[];
  source: "user_direct" | "dependency_cascade" | "system_derived_content";
  actorRunIds: string[];
  triggerMessageSeqs: number[];
  dependencyReasons: string[];
  uiLocator?: Record<string, string>;
}

export interface JournalSeqRange {
  fromExclusive: number;
  toInclusive: number;
}

export interface ReviewDecisionGroup {
  id: string;
  title: string;
  operationIds: string[];
  groupingReasons: string[];
  decisionToken: string;
  decision: ReviewDecisionState;
}

export type ReviewMediaType = "image" | "video" | "audio" | "other";
export type ReviewMediaCandidateState =
  | "SELECTED"
  | "PREVIOUSLY_SELECTED"
  | "UNSELECTED_CANDIDATE"
  | "SUPERSEDED"
  | "HISTORICAL";

export interface ReviewMediaVersion {
  versionRef: string;
  versionKind: "asset" | "artifact";
  versionId: string;
  ownerId: string;
  version: number;
  mediaType: ReviewMediaType;
  mimeType?: string | null;
  artifactKind?: string | null;
  targetRef?: string | null;
  checksum: string;
  durationSeconds?: number | null;
  createdBy?: string | null;
  createdAt: string;
  provenanceRefs: string[];
  inputFingerprint?: string | null;
  modelRunId?: string | null;
  selectedInBaseRevision: boolean;
  selectedInReviewRevision: boolean;
  candidateState: ReviewMediaCandidateState;
}

export interface MediaComparison {
  id: string;
  operationIds: string[];
  targetRef: string;
  path?: string | null;
  changeKind:
    | "create"
    | "delete"
    | "replace_media"
    | "change_reference"
    | "move"
    | "rename"
    | "candidate";
  before?: ReviewMediaVersion | null;
  after?: ReviewMediaVersion | null;
  candidates: ReviewMediaVersion[];
  inputStoryboardRefs: string[];
  sourceRefs: string[];
}

export interface IntegrationPreview {
  id: string;
  scope: "section" | "final";
  targetRef: string;
  title: string;
  operationIds: string[];
  before?: ReviewMediaVersion | null;
  after?: ReviewMediaVersion | null;
  affectedRefs: string[];
  uiLocator: Record<string, string>;
}

export interface ReviewManifest {
  id: string;
  transactionId: string;
  reviewRound: number;
  baseRevisionId: string;
  reviewRevisionId: string;
  manifestToken: string;
  summary: string;
  journalSeqRange: JournalSeqRange;
  decisionGroups: ReviewDecisionGroup[];
  operations: ReviewOperation[];
  createdArtifactVersionRefs: string[];
  mediaComparisons: MediaComparison[];
  integrationPreviews: IntegrationPreview[];
  createdAt: string;
}

export interface ReviewDecisionRequest {
  decisionToken: string;
  decision: "ACCEPT" | "REJECT" | "REVISE";
  instruction?: string;
  selection?: { field: string; text: string };
}

export interface ReviewCommentRequest {
  clientCommentId: string;
  text: string;
  selection?: { field: string; text: string };
}

export interface ReviewCommentResponse {
  commentId: string;
  groupId: string;
  text: string;
  selection?: Record<string, unknown> | null;
  createdAt: string;
}

export interface ReviewOperationContent {
  operationId: string;
  beforeVersionRef?: string;
  afterVersionRef?: string;
  before?: string;
  after?: string;
  contentType: "markdown" | "text" | "vtt" | "ctm" | string;
}

export interface ReviewDecisionResponse {
  group: ReviewDecisionGroup;
  approvedRevisionId?: string;
  manifest: ReviewManifest;
}
