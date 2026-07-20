import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ExecutionAuthorizationCard, RunReviewPanel, ReviewDecisionCard } from '@/components/agent';
import AgentDecisionCenter from '@/components/agent/AgentDecisionCenter';
import { presentReviewGroup } from '@/components/agent/reviewPresentation';
import { installMockFetch } from '@/test/mockFetch';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import { useNavigationStore } from '@/store/navigationStore';
import { useAgentDockUiStore } from '@/store/agentDockUiStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import type { IntegrationPreview, MediaComparison, PlanView, ReviewDecisionGroup, ReviewMediaVersion, ReviewOperation } from '@/contracts/creator';

const group: ReviewDecisionGroup = { id: 'g1', title: 'Unit 文案', operationIds: ['op1'], groupingReasons: ['硬依赖闭包'], decisionToken: 'token-1', decision: 'PENDING' };
const operation: ReviewOperation = { id: 'op1', decisionGroupId: 'g1', mutationIds: ['m1'], kind: 'update', targetRef: 'unit:u1', artifactKind: 'markdown', path: 'story/sections/s1/units/u1/narrative.md', beforeVersionRef: 'workspace-content://before@ov1', afterVersionRef: 'workspace-content://after@ov2', causalRefs: [], source: 'user_direct', actorRunIds: [], triggerMessageSeqs: [1], dependencyReasons: [], uiLocator: { page: 'workbench', unitId: 'u1' } };

function mediaVersion(overrides: Partial<ReviewMediaVersion> = {}): ReviewMediaVersion {
  return {
    versionRef: 'artifact://unit-video@video-v1',
    versionKind: 'artifact',
    versionId: 'video-v1',
    ownerId: 'unit-video',
    version: 1,
    mediaType: 'video',
    mimeType: 'video/mp4',
    artifactKind: 'unit_video',
    targetRef: 'unit:u1',
    checksum: 'a'.repeat(64),
    durationSeconds: 8,
    createdBy: 'video_generation',
    createdAt: '2026-07-11T00:00:00Z',
    provenanceRefs: ['artifact://unit-storyboard@storyboard-v2', 'asset://source-video@source-v1'],
    inputFingerprint: 'fingerprint-1',
    modelRunId: 'run-1',
    selectedInBaseRevision: true,
    selectedInReviewRevision: false,
    candidateState: 'PREVIOUSLY_SELECTED',
    ...overrides,
  };
}

describe('review decisions and execution authorization', () => {
  beforeEach(() => {
    useAgentDockUiStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
    useReviewManifestStore.getState().reset();
    useReviewManifestStore.getState().bindTransaction('p1', 'tx1');
    useNavigationStore.setState({ stack: [], reviewFocus: null, expectedPath: null });
  });

  it('keeps origin rejection handoff two-step and does not issue REVISE on click', () => {
    const { calls } = installMockFetch([]);
    render(<ReviewDecisionCard projectId="p1" group={group} operations={[operation]} />);

    fireEvent.click(screen.getByText('要求修改'));

    expect(calls.some((call) => call.url.endsWith('/decision'))).toBe(false);
    expect(useAgentDockUiStore.getState().tab).toBe('conversation');
    expect(useAgentDockUiStore.getState().reviewRevisionHandoff).toEqual({
      groupId: 'g1',
      decisionToken: 'token-1',
      title: 'Unit 文案',
      targetRef: 'unit:u1',
      selection: undefined,
      prepared: false,
    });
  });

  it('rejects one review item directly as the visible undo action', async () => {
    const manifest = { id: 'r1', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'a', reviewRevisionId: 'b', manifestToken: 'mt', summary: '', journalSeqRange: { fromExclusive: 0, toInclusive: 1 }, decisionGroups: [group], operations: [operation], createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now' };
    const rejected = { ...group, decision: 'REJECTED' as const };
    const { calls } = installMockFetch([
      { match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', before: '旧文案', after: '新文案', contentType: 'markdown' } } } },
      { match: '/decision', response: { json: { group: rejected, manifest: { ...manifest, decisionGroups: [rejected] } } } },
    ]);

    render(<ReviewDecisionCard projectId="p1" group={group} operations={[operation]} />);
    fireEvent.click(screen.getByRole('button', { name: '撤销' }));

    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/decision'))).toBe(true));
    expect(calls.find((call) => call.url.endsWith('/decision'))?.body).toEqual({
      decisionToken: 'token-1',
      decision: 'REJECT',
    });
  });

  it('sends one group decision with its CAS token and replays repeated view highlighting', async () => {
    const manifest = { id: 'r1', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'a', reviewRevisionId: 'b', manifestToken: 'mt', summary: '', journalSeqRange: { fromExclusive: 0, toInclusive: 1 }, decisionGroups: [group], operations: [operation], createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now' };
    const { calls } = installMockFetch([
      { match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', beforeVersionRef: operation.beforeVersionRef, afterVersionRef: operation.afterVersionRef, before: '旧文案', after: '新文案', contentType: 'markdown' } } } },
      { match: '/decision', response: { json: { group: { ...group, decision: 'ACCEPTED_APPLIED' }, manifest: { ...manifest, decisionGroups: [{ ...group, decision: 'ACCEPTED_APPLIED' }] } } } },
    ]);
    render(<ReviewDecisionCard projectId="p1" group={group} operations={[operation]} />);
    fireEvent.click(screen.getByText('查看'));
    const firstPulse = useNavigationStore.getState().reviewFocus?.query.reviewPulse;
    expect(useNavigationStore.getState().reviewFocus?.query.field).toBe('unit:u1/storyText');
    fireEvent.click(screen.getByText('查看'));
    expect(useNavigationStore.getState().reviewFocus?.query.reviewPulse).not.toBe(firstPulse);
    fireEvent.click(screen.getByText('接受'));
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/decision'))).toBe(true));
    const decisionCall = calls.find((call) => call.url.endsWith('/decision'))!;
    expect(decisionCall.body).toEqual({ decisionToken: 'token-1', decision: 'ACCEPT' });
    expect(decisionCall.headers['idempotency-key']).toMatch(/^review-decision-/);
  });

  it('loads sealed add/update/delete text content and renders content rather than opaque refs', async () => {
    const operations: ReviewOperation[] = [
      { ...operation, id: 'op-create', kind: 'create', beforeVersionRef: undefined, afterVersionRef: 'workspace-content://create@ov1' },
      { ...operation, id: 'op-update', kind: 'update', beforeVersionRef: 'workspace-content://before@ov1', afterVersionRef: 'workspace-content://after@ov2' },
      { ...operation, id: 'op-delete', kind: 'delete', beforeVersionRef: 'workspace-content://delete@ov1', afterVersionRef: undefined },
    ];
    installMockFetch([
      { match: '/review-operation-op-create', response: { json: { view: { operationId: 'op-create', afterVersionRef: operations[0].afterVersionRef, after: '新增全文', contentType: 'markdown' } } } },
      { match: '/review-operation-op-update', response: { json: { view: { operationId: 'op-update', beforeVersionRef: operations[1].beforeVersionRef, afterVersionRef: operations[1].afterVersionRef, before: 'alpha', after: 'beta', contentType: 'markdown' } } } },
      { match: '/review-operation-op-delete', response: { json: { view: { operationId: 'op-delete', beforeVersionRef: operations[2].beforeVersionRef, before: '删除全文', contentType: 'markdown' } } } },
    ]);
    const reviewGroup = { ...group, operationIds: operations.map((item) => item.id) };
    useReviewManifestStore.setState({
      manifest: {
        id: 'review-content', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'revision-a', reviewRevisionId: 'revision-b', manifestToken: 'mt', summary: '',
        journalSeqRange: { fromExclusive: 0, toInclusive: 3 }, decisionGroups: [reviewGroup], operations,
        createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now',
      },
    });
    const { container } = render(<ReviewDecisionCard projectId="p1" group={reviewGroup} operations={operations} />);
    await waitFor(() => expect(screen.getByText('新增全文')).toBeInTheDocument());
    expect(container.querySelectorAll('.agent-diff-add')).toHaveLength(2);
    expect(container.querySelectorAll('.agent-diff-del')).toHaveLength(2);
    expect([...container.querySelectorAll('.agent-diff-del')].map((item) => item.textContent)).toContain('alph');
    expect([...container.querySelectorAll('.agent-diff-add')].map((item) => item.textContent)).toContain('bet');
    expect(container.textContent).toContain('删除全文');
    expect(container.textContent).not.toContain('workspace-content://');
  });

  it('keeps media evidence out of hidden card DOM and deep-links to the exact visible version chips', () => {
    const mediaOperations: ReviewOperation[] = [
      { ...operation, id: 'op-video', kind: 'replace_media', artifactKind: 'reference', path: 'production/video/selected.ref' },
      { ...operation, id: 'op-image', kind: 'create', artifactKind: 'reference', path: 'production/storyboard/selected.ref' },
      { ...operation, id: 'op-audio', kind: 'replace_media', artifactKind: 'reference', path: 'post/audio/selected.ref' },
    ];
    const oldVideo = mediaVersion();
    const newVideo = mediaVersion({ versionRef: 'artifact://unit-video@video-v2', versionId: 'video-v2', version: 2, selectedInBaseRevision: false, selectedInReviewRevision: true, candidateState: 'SELECTED' });
    const image = mediaVersion({ versionRef: 'artifact://unit-storyboard@storyboard-v2', versionId: 'storyboard-v2', ownerId: 'unit-storyboard', mediaType: 'image', mimeType: 'image/png', artifactKind: 'unit_storyboard', durationSeconds: null, selectedInBaseRevision: false, selectedInReviewRevision: true, candidateState: 'SELECTED' });
    const oldAudio = mediaVersion({ versionRef: 'artifact://section-audio@audio-v1', versionId: 'audio-v1', ownerId: 'section-audio', mediaType: 'audio', mimeType: 'audio/wav', artifactKind: 'section_audio', durationSeconds: 12 });
    const newAudio = mediaVersion({ ...oldAudio, versionRef: 'artifact://section-audio@audio-v2', versionId: 'audio-v2', version: 2, selectedInBaseRevision: false, selectedInReviewRevision: true, candidateState: 'SELECTED' });
    const comparisons: MediaComparison[] = [
      { id: 'cmp-video', operationIds: ['op-video'], targetRef: 'unit:u1', path: mediaOperations[0].path, changeKind: 'replace_media', before: oldVideo, after: newVideo, candidates: [newVideo], inputStoryboardRefs: ['artifact://unit-storyboard@storyboard-v2'], sourceRefs: ['asset://source-video@source-v1'] },
      { id: 'cmp-image', operationIds: ['op-image'], targetRef: 'unit:u1', path: mediaOperations[1].path, changeKind: 'create', after: image, candidates: [image], inputStoryboardRefs: [], sourceRefs: ['asset://source-image@source-v2'] },
      { id: 'cmp-audio', operationIds: ['op-audio'], targetRef: 'post:s1', path: mediaOperations[2].path, changeKind: 'replace_media', before: oldAudio, after: newAudio, candidates: [newAudio], inputStoryboardRefs: [], sourceRefs: ['asset://voice@voice-v1'] },
    ];
    const integration: IntegrationPreview = { id: 'preview-s1', scope: 'section', targetRef: 'post:s1', title: 'Section s1 集成预览', operationIds: ['op-video'], before: oldVideo, after: newVideo, affectedRefs: ['unit:u1', 'post:s1'], uiLocator: { page: 'section-compose', sectionId: 's1' } };
    const reviewGroup = { ...group, operationIds: mediaOperations.map((item) => item.id) };

    const { container } = render(<ReviewDecisionCard projectId="p1" group={reviewGroup} operations={mediaOperations} mediaComparisons={comparisons} integrationPreviews={[integration]} />);

    expect(container.querySelector('[data-review-media-version]')).not.toBeInTheDocument();
    expect(container.querySelector('video, audio, [hidden]')).not.toBeInTheDocument();
    expect(screen.queryByText('Section s1 集成预览')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('查看'));
    expect(useNavigationStore.getState().reviewFocus?.path).toBe('/project/p1/plan/section/s1');
    expect(useNavigationStore.getState().reviewFocus?.query.version).toBe('video-v2');
    expect(useNavigationStore.getState().reviewFocus?.query.focus).toBe('video');
  });

  it('approves the exact authorization token, cost and original run', async () => {
    const auth = { id: 'auth1', transactionId: 'tx1', specialistRunId: 'run1', executionRequestId: 'er1', targetRef: 'unit:u1', scope: {}, status: 'PENDING' as const, authorizationToken: 'auth-token', provider: 'dashscope', model: 'wan2.7-r2v', estimatedCost: 2.5, currency: 'CNY', maxCandidates: 2, createdAt: 'now' };
    const { calls } = installMockFetch([{ match: '/approve', response: { json: { ...auth, status: 'APPROVED' } } }]);
    render(<ExecutionAuthorizationCard authorization={auth} />);
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('生产确认')).toBeInTheDocument();
    expect(screen.getByText('端到端生产等待确认')).toBeInTheDocument();
    fireEvent.click(screen.getByText('继续'));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ authorizationToken: 'auth-token', provider: 'dashscope', model: 'wan2.7-r2v', maxCost: 2.5, maxCandidates: 2 });
    expect(calls[0].headers['idempotency-key']).toMatch(/^authorization-approve-/);
    expect(calls[0].url).toContain('/transactions/tx1/execution-authorizations/auth1/approve');
  });

  it('declines with the exact CAS token and a stable mutation key', async () => {
    const auth = { id: 'auth2', transactionId: 'tx1', specialistRunId: 'run2', executionRequestId: 'er2', targetRef: 'unit:u2', scope: {}, status: 'PENDING' as const, authorizationToken: 'decline-token', provider: 'dashscope', model: 'wan2.7-r2v', maxCandidates: 1, createdAt: 'now' };
    const { calls } = installMockFetch([{ match: '/decline', response: { json: { ...auth, status: 'DECLINED' } } }]);
    render(<ExecutionAuthorizationCard authorization={auth} />);
    fireEvent.click(screen.getByText('取消'));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ authorizationToken: 'decline-token' });
    expect(calls[0].headers['idempotency-key']).toMatch(/^authorization-decline-/);
  });

  it('renders the main-style per-item review list with decisions but without low-level refs', () => {
    const change = { ...group, id: 'change', title: '节奏改动', operationIds: ['change-op'], decisionToken: 'change-token' };
    const recheck = { ...group, id: 'recheck', title: '上游变化复核', operationIds: ['recheck-op'], groupingReasons: ['需复核'], decisionToken: 'recheck-token' };
    const storyboard = { ...group, id: 'storyboard', title: '镜头分镜', operationIds: ['storyboard-op'], decisionToken: 'storyboard-token' };
    const processed = { ...group, id: 'processed', title: '已处理视频', operationIds: ['processed-op'], decisionToken: 'processed-token', decision: 'ACCEPTED_APPLIED' as const };
    const operations: ReviewOperation[] = [
      { ...operation, id: 'change-op', decisionGroupId: 'change', artifactKind: 'markdown', path: 'story/outline.md' },
      { ...operation, id: 'recheck-op', decisionGroupId: 'recheck', artifactKind: 'reference', path: 'production/video.ref' },
      { ...operation, id: 'storyboard-op', decisionGroupId: 'storyboard', artifactKind: 'storyboard_image', path: 'production/storyboard.ref' },
      { ...operation, id: 'processed-op', decisionGroupId: 'processed', artifactKind: 'video', path: 'production/video.ref' },
    ];
    useReviewManifestStore.setState({
      manifest: {
        id: 'review-groups', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'a', reviewRevisionId: 'b', manifestToken: 'mt', summary: '',
        journalSeqRange: { fromExclusive: 0, toInclusive: 4 },
        decisionGroups: [change, recheck, storyboard, processed], operations,
        createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now',
      },
    });

    render(<AgentDecisionCenter projectId="p1" />);

    expect(screen.getAllByRole('button', { name: '查看' })).toHaveLength(3);
    expect(screen.getByText('节奏改动')).toBeInTheDocument();
    expect(screen.getByText('上游变化复核')).toBeInTheDocument();
    expect(screen.getByText('镜头分镜')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '接受' })).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: '撤销' })).toHaveLength(3);
    expect(document.querySelector('[data-review-thumbnail]')).not.toBeInTheDocument();
    expect(screen.queryByText('story/outline.md')).not.toBeInTheDocument();
    expect(screen.queryByText('production/storyboard.ref')).not.toBeInTheDocument();
    expect(screen.queryByText('已处理视频')).not.toBeInTheDocument();
  });

  it('presents text review titles as a complete Plan hierarchy down to shot and field', () => {
    const shotOperation: ReviewOperation = {
      ...operation,
      // Legacy manifests could carry an asset ref even though the authoritative
      // workspace path points at a Plan field.
      targetRef: 'asset:legacy-source',
      path: 'story/sections/s1/units/u1/shots/shot-2/dialogue.md',
      uiLocator: { page: 'plan', sectionId: 's1', unitId: 'u1' },
    };
    const shotGroup = { ...group, operationIds: [shotOperation.id] };
    const manifest = {
      id: 'hierarchy-review', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'a', reviewRevisionId: 'b', manifestToken: 'mt', summary: '',
      journalSeqRange: { fromExclusive: 0, toInclusive: 1 }, decisionGroups: [shotGroup], operations: [shotOperation],
      createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now',
    };
    const plan = {
      sections: [{
        id: 's1', number: 1, title: '开场',
        units: [{ id: 'u1', number: 1, title: '相遇', shots: [{ id: 'shot-2', number: 2 }] }],
      }],
    } as unknown as PlanView;

    const presentation = presentReviewGroup(shotGroup, manifest, plan, null);

    expect(presentation.locationSegments).toEqual(['视频方案', '01 开场', '01 相遇', '镜头 02', '对白']);
    expect(presentation.title).toBe('视频方案 / 01 开场 / 01 相遇 / 镜头 02 / 对白');
    expect(presentation.showPreview).toBe(false);
    expect(presentation.detail).toBe('');
  });

  it('does not expose an unsealed stale run as a review decision', () => {
    useReviewManifestStore.setState({ manifest: null });
    useCreatorTaskViewStore.setState({
      runs: [{
        id: 'stale-run', role: 'story_planning_agent', displayName: '故事规划 Agent', status: 'STALE',
        targetRefs: ['project:p1'], taskRefs: [], metadata: { reviewPending: true },
      }],
    });

    render(<AgentDecisionCenter projectId="p1" />);

    expect(screen.getByText('暂无待处理的决策')).toBeInTheDocument();
    expect(screen.queryByText('故事规划 Agent')).not.toBeInTheDocument();
  });

  it('projects the origin run review surface from run and decision-group authorities', async () => {
    const changeGroup = { ...group, id: 'change', title: '节奏改动', decisionToken: 'change-token' };
    const changeOperation = {
      ...operation,
      id: 'op1',
      decisionGroupId: 'change',
      artifactKind: 'json',
      actorRunIds: ['run-change'],
    };
    const manifest = {
      id: 'change-review', transactionId: 'tx1', reviewRound: 1, baseRevisionId: 'revision-a', reviewRevisionId: 'revision-b', manifestToken: 'mt', summary: '',
      journalSeqRange: { fromExclusive: 0, toInclusive: 1 }, decisionGroups: [changeGroup], operations: [changeOperation],
      createdArtifactVersionRefs: [], mediaComparisons: [], integrationPreviews: [], createdAt: 'now',
    };
    useReviewManifestStore.setState({ manifest });
    useCreatorTaskViewStore.setState({
      runs: [{
        id: 'run-change', role: 'story_planning_agent', displayName: '故事规划 Agent', status: 'SUCCEEDED',
        targetRefs: ['unit:u1'], finalMarker: 'SUCCESS', finalSummaryText: '已完成故事节奏调整', taskRefs: [], metadata: {},
      }],
    });
    const { calls } = installMockFetch([{ match: '/decision', response: { json: { group: { ...changeGroup, decision: 'ACCEPTED_APPLIED' }, manifest: { ...manifest, decisionGroups: [{ ...changeGroup, decision: 'ACCEPTED_APPLIED' }] } } } }]);

    render(<RunReviewPanel projectId="p1" />);
    expect(screen.getByText('Sub-Agent 运行')).toBeInTheDocument();
    fireEvent.click(screen.getByText('故事规划 Agent'));
    expect(screen.getByText('已完成故事节奏调整')).toBeInTheDocument();
    expect(screen.getByText('校验：通过')).toBeInTheDocument();
    expect(screen.getByText('节奏改动')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '应用选中（其余保留待审） · 1' }));

    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/decision'))).toBe(true));
    expect(calls.find((call) => call.url.endsWith('/decision'))?.body).toEqual({
      decisionToken: 'change-token',
      decision: 'ACCEPT',
    });
  });
});
