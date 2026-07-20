/**
 * The persisted document keeps Pydantic's snake_case field names.  These
 * contracts deliberately type the stable Project root while leaving nested
 * domain payloads open until the Pydantic schema is generated at build time.
 */
export type ProjectJsonRecord = Record<string, unknown>;

export interface ProjectEntityCollection<T extends ProjectJsonRecord = ProjectJsonRecord>
  extends ProjectJsonRecord {
  items: Record<string, T>;
  order: string[];
}

export interface ProjectSettingsDocument extends ProjectJsonRecord {
  aspect_ratio: string;
  resolution: string;
  platform: string;
  language: string;
  target_duration_seconds: number | null;
  content_type: string | null;
}

export interface ProjectAssetIndexDocument extends ProjectJsonRecord {
  files_by_id: Record<string, ProjectJsonRecord>;
  source_versions_by_id: Record<string, ProjectJsonRecord>;
  intelligence_versions_by_id: Record<string, ProjectJsonRecord>;
  artifact_slots_by_id: Record<string, ProjectJsonRecord>;
  artifact_versions_by_id: Record<string, ProjectJsonRecord>;
}

export interface ProjectDocument extends ProjectJsonRecord {
  schema_version: number;
  project_id: string;
  generation: number;
  created_at: string;
  updated_at: string;
  name: string;
  description: string;
  scenario: 'short_drama' | 'video_edit' | 'general';
  settings: ProjectSettingsDocument;
  strategy: ProjectJsonRecord;
  sources: ProjectJsonRecord;
  visual: ProjectJsonRecord;
  story: ProjectJsonRecord;
  production: ProjectJsonRecord;
  post_production: ProjectJsonRecord;
  assets: ProjectAssetIndexDocument;
}

export type ProjectServerSyncStatus = 'healthy' | 'degraded' | 'invalid';

export interface ProjectSnapshotEnvelope {
  projectId: string;
  generation: number;
  etag: string;
  syncStatus: ProjectServerSyncStatus;
  project: ProjectDocument;
}

export interface ProjectInvalidSnapshotResponse {
  code: 'PROJECT_INVALID';
  syncStatus: 'invalid';
  lastGoodGeneration: number | null;
  message: string;
}

export type ProjectSnapshotPollResult =
  | ({ kind: 'updated' } & ProjectSnapshotEnvelope)
  | {
      kind: 'not_modified';
      etag: string | null;
      generation: number | null;
      syncStatus: ProjectServerSyncStatus;
    }
  | ({ kind: 'invalid' } & ProjectInvalidSnapshotResponse);
