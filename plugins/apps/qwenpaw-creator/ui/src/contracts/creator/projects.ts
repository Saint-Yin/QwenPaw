export type CreatorScenario = "short_drama" | "video_edit" | "general";

export interface ProjectCreateRequest {
  clientRequestId: string;
  name: string;
  description?: string;
  scenario: CreatorScenario;
  aspectRatio: string;
  resolution: string;
  contentType?: string | null;
  /** Optional atomic bootstrap goal persisted in the file Runtime aggregate. */
  initialGoal?: string;
}

export interface ProjectCreateResponse {
  projectId: string;
  creatorSessionId: string;
  conversationId: string;
  /** Compatibility name for the initial project.json snapshot; not a SQL revision. */
  approvedRevisionId: string;
  header: ProjectCreateHeader;
}

export interface ProjectCreateHeader {
  id: string;
  name: string;
  description: string;
  scenario: CreatorScenario;
  aspectRatio: string;
  resolution: string;
  contentType: string | null;
}

export interface ProjectSummary {
  projectId: string;
  name: string;
  description: string;
  scenario: CreatorScenario;
  aspectRatio: string;
  resolution: string;
  contentType?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectListResponse {
  items: ProjectSummary[];
  limit: number;
  offset: number;
}

export interface ProjectHeaderView extends ProjectCreateHeader {
  /** Read-only TopNav presentation of the original project goal. */
  masterScript: string;
  platform: string;
  language: string;
  targetDuration: number | null;
  resolvedRefs: [];
  relations: [];
  readiness: { ready: boolean };
  blockers: string[];
  targetVersion: string;
  uiLocator: Record<string, string>;
}
