import type {
  AgentStatusBarView,
  AssetLibraryView,
  ComposeView,
  EditWorkbenchView,
  PlanView,
  ProjectHeaderView,
  R2VWorkbenchView,
  ViewEnvelope,
} from '@/contracts/creator';

export const status: AgentStatusBarView = {
  progress: { phase: 'unit_production', label: '正在制作 Unit 1/2', sourceEventSeq: 1, updatedAt: '2026-07-10T00:00:00Z' },
  badges: [],
};

export function envelope<T>(view: T, overrides: Partial<ViewEnvelope<T>> = {}): ViewEnvelope<T> {
  return { projectId: 'p1', approvedRevisionId: 'rev-1', workingBranchId: 'branch-1', workingHead: 'head-1', activeTransactionId: 'tx-1', uiPhase: 'executing', agentStatusBar: status, view, ...overrides };
}

export const headerView: ProjectHeaderView = { id: 'p1', name: '测试项目', description: '说明', masterScript: '说明', scenario: 'general', aspectRatio: '16:9', resolution: '720P', contentType: null, platform: '', language: '', targetDuration: null, resolvedRefs: [], relations: [], readiness: { ready: true }, blockers: [], targetVersion: 'ov-header', uiLocator: { page: 'project' } };

export const unit = {
  id: 'u1', number: 1, title: 'Unit 1', taskType: 'r2v' as const, duration: 6, storyText: '雪夜汽车驶过', shots: [{ id: 'shot-1', number: 1, description: '汽车驶过', camera: '→ 横摇右' as const, framing: '中景' as const, duration: 6, targetVersion: 'ov-shot-1' }], characterRefs: [], propRefs: [], materialRefs: [], resolvedRefs: [], relations: [], readiness: { ready: true, blockers: [] }, blockers: [], targetVersion: 'ov-u1', uiLocator: { page: 'workbench', unitId: 'u1' },
};

export const planView: PlanView = { title: '测试方案', aspectRatio: '16:9', sections: [{ id: 's1', number: 1, title: '开场', narrative: '开场叙事', constraints: [], units: [unit], resolvedRefs: [], relations: [], targetVersions: {}, targetVersion: 'ov-s1', readiness: { ready: true, blockers: [] }, blockers: [], uiLocator: { page: 'plan', sectionId: 's1' } }], resolvedRefs: [], relations: [], readiness: { ready: true }, blockers: [], targetVersion: 'ov-plan', uiLocator: { page: 'plan' } };

export const r2vView: R2VWorkbenchView = { kind: 'r2v', unit, storyboardPrompt: '分镜提示词', videoPrompt: '视频提示词', storyboardVersions: [], videoVersions: [], inputReferenceBindings: [], providerConstraints: { provider: 'dashscope', minDuration: 1, maxDuration: 15, maxReferenceImages: 5, model: 'wan2.7-r2v', version: '2026-07', capturedAt: 'now', allowedDurations: [] }, resolvedRefs: [], relations: [], readiness: { ready: false }, blockers: ['STORYBOARD_VERSION_REQUIRED'], continuity: '', targetVersion: 'ov-u1', uiLocator: { page: 'workbench', unitId: 'u1', route: 'r2v' }, selectionSource: { revisionId: 'rev-1' } };

export const editView: EditWorkbenchView = { kind: 'edit', unit: { ...unit, taskType: 'edit', duration: 32 }, goal: '剪辑成预告', plan: { summary: '剪辑摘要', target_duration: 32.25, timeline: [{ clip_id: 'clip-01', asset_id: 'a1', asset_name: '源视频', start: 1.25, end: 8.75, duration: 7.5, order: 1, transition: 'cut', overlay_copy: { kind: 'pet_os', text: '出发', vibe: 'action', appear_at: 0, duration: 7.5 } }], storyboard: [{ panel_id: 'panel-1', order: 1, title: '关键帧', description: '源视频关键帧', source_asset_id: 'a1', timestamp: 4.5, timeline_start: 0, timeline_end: 7.5 }], audio_plan: { bgm: '保留' } }, storyboard_image_url: null, material_assets: [{ id: 'a1', name: '源视频', duration: 60 }], workflow_trace: [{ step: 'vlm' }], videoVersions: [], planVersion: { id: 'plan-v1', checksum: 'sha256:plan-v1', createdAt: 'now' }, planRef: 'ai-edit-plan://u1@plan-v1', resolvedRefs: [], relations: [], readiness: { ready: true }, blockers: [], targetVersion: 'ov-u1', uiLocator: { page: 'workbench', unitId: 'u1', route: 'edit' } };

export const assetView: AssetLibraryView = { attachedSources: [], ingestItems: [], availableAssets: [{ assetId: 'a1', assetVersionId: 'av1', sourceRef: 'asset://a1@av1', name: '素材一', category: 'upload', existence: 'available', presentationStatus: 'draft', mediaType: 'video', checksum: 'sha', url: '/media/a1', objectVersion: 'ov-a1', createdAt: 'now', referenceCount: 0, attached: false, uiLocator: { page: 'assets', assetId: 'a1' } }], visualAssets: [], presentationAssets: [{ id: 'a1', name: '素材一', category: 'upload', existence: 'available', presentationStatus: 'draft', mediaType: 'video', url: '/media/a1', sourceDescription: '用户上传', sourceRef: 'asset://a1@av1', referenceCount: 0, targetVersion: 'ov-a1', uiLocator: { page: 'assets', assetId: 'a1' } }], resolvedRefs: [], relations: [], readiness: { ready: true }, blockers: [], targetVersion: 'ov-assets', uiLocator: { page: 'assets' } };

export const composeView: ComposeView = { kind: 'section', sectionId: 's1', sectionNumber: 1, sectionTitle: '开场', selections: [], candidates: [{ id: 'art-v1', name: 'Unit 1 video', artifactVersionId: 'art-v1', ownerRef: 'project://unit/u1', sourceRef: 'artifact://slot-u1@art-v1', slotId: 'slot-u1', kind: 'unit_video', url: '/media/u1', checksum: 'sha', createdAt: 'now', basedOnRevisionId: 'rev-1', provenanceRefs: [], selected: false, uiLocator: { page: 'workbench', unitId: 'u1', versionId: 'art-v1' } }], transitions: [], resolvedRefs: [], relations: [], readiness: { ready: true }, blockers: [], targetVersion: 'ov-compose', uiLocator: { page: 'section-compose', sectionId: 's1' } };
