/**
 * File-native Review records are serialized directly from the Runtime
 * Pydantic models.  Keep their snake_case field names at this boundary so the
 * browser never invents a second representation of the persisted authority.
 */
export type FileProjectChangeKind =
  | "create"
  | "update"
  | "delete"
  | "move"
  | "reorder"
  | "select_asset";

export type FileProjectReviewStatus = "PENDING" | "RESOLVED" | "SUPERSEDED";

export type FileProjectReviewOperationDecision =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "REVISED"
  | "SUPERSEDED_BY_USER_EDIT";

export interface FileProjectReviewOperation {
  kind: FileProjectChangeKind;
  json_pointer: string | null;
  file_id: string | null;
  target_ref: string | null;
  before_hash: string;
  after_hash: string;
  before: unknown | null;
  after: unknown | null;
  operation_id: string;
  ui_locator: Record<string, string>;
  decision: FileProjectReviewOperationDecision;
}

export interface FileProjectReviewRecord {
  review_id: string;
  round_id: string;
  request_id: string;
  request_message_seq: number;
  interrupted_run_id: string;
  baseline_generation: number;
  baseline_etag: string;
  candidate_generation: number;
  candidate_etag: string;
  decision_token: string;
  status: FileProjectReviewStatus;
  operations: FileProjectReviewOperation[];
  created_at: string;
  updated_at: string;
}

export type FileProjectReviewDecision = "ACCEPT" | "REJECT";

export interface FileProjectReviewDecisionItem {
  operation_id: string;
  decision: FileProjectReviewDecision;
}

export interface FileProjectReviewDecisionRequest {
  decisionId: string;
  decisionToken: string;
  decisions: FileProjectReviewDecisionItem[];
}

export type FileProjectReviewPollResult =
  | {
      kind: "updated";
      review: FileProjectReviewRecord;
      etag: string;
    }
  | {
      kind: "not_modified";
      etag: string | null;
    }
  | {
      kind: "empty";
    };
