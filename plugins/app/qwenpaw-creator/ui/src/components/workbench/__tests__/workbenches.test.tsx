import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import R2VWorkbench from '@/components/workbench/R2VWorkbench';
import AiEditWorkbench from '@/components/workbench/AiEditWorkbench';
import ShotList from '@/components/workbench/ShotList';
import { editView, envelope, r2vView } from '@/test/creatorFixtures';
import { installMockFetch } from '@/test/mockFetch';
import type { ArtifactVersionView, EditWorkbenchView, R2VWorkbenchView } from '@/contracts/creator';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import { useWorkspaceViewStore } from '@/store/workspaceViewStore';

function artifact(id: string, kind: string, selected = false): ArtifactVersionView {
  return {
    id,
    name: id,
    slotId: `slot-${kind}`,
    kind,
    url: `/generated/${id}`,
    checksum: `sha256:${id}`,
    createdAt: 'now',
    provenanceRefs: [],
    selected,
    artifactVersionId: id,
    sourceRef: `artifact://slot-${kind}@${id}`,
    basedOnRevisionId: 'rev-1',
    ownerRef: 'project://unit/u1',
    uiLocator: { page: 'workbench', unitId: 'u1', versionId: id },
  };
}

describe('origin workbench UI backed by canonical Creator contracts', () => {
  beforeEach(() => {
    useCreatorSessionStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
    useReviewManifestStore.getState().reset();
    useWorkspaceViewStore.getState().reset();
  });
  it('restores the origin R2V toolbar, panel names, and 320px two-column shell', () => {
    const { container } = render(
      <R2VWorkbench
        projectId="p1"
        envelope={envelope(r2vView)}
        view={r2vView}
        reload={vi.fn()}
        sectionNumber={2}
        sectionTitle="追逐"
        aspectRatio="9:16"
      />,
    );
    expect(container.firstElementChild).toHaveClass('flex', 'h-full', 'flex-col', 'overflow-hidden');
    expect(container.querySelector('.lg\\:grid-cols-\\[minmax\\(0\\,1fr\\)_320px\\]')).toBeInTheDocument();
    expect(screen.getByText('视频方案 / 02 追逐 / 01 Unit 1 / 制作工作台')).toBeInTheDocument();
    ['生成分镜 Prompt', '生成分镜图', '生成视频 Prompt', '生成视频'].forEach((name) => {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    });
    ['Shot 列表（1）', '分镜Prompt与分镜图', '视频结果', '输入引用（0）', '资产绑定'].forEach((name) => {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    });
    expect(screen.queryByRole('heading', { name: '分镜文本' })).not.toBeInTheDocument();
    expect(screen.getByText('9:16')).toBeInTheDocument();
  });

  it('persists both origin prompt editors through SET_UNIT_TEXT semantic commands', async () => {
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-prompt', status: 'APPLIED', eventSeq: 1 } } },
    ]);
    render(<R2VWorkbench projectId="p1" envelope={envelope(r2vView)} view={r2vView} reload={vi.fn()} />);
    const storyboardPrompt = screen.getByPlaceholderText('生成分镜 Prompt 后可在此编辑…');
    fireEvent.change(storyboardPrompt, { target: { value: '新的分镜提示词' } });
    fireEvent.blur(storyboardPrompt);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      type: 'SET_UNIT_TEXT',
      targetRef: 'unit:u1',
      arguments: { field: 'storyboardPrompt', value: '新的分镜提示词' },
    });
  });

  it('keeps the origin free-form camera editor while retaining canonical camera and framing fields', async () => {
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-shot', status: 'APPLIED', eventSeq: 1 } } },
    ]);
    render(<R2VWorkbench projectId="p1" envelope={envelope(r2vView)} view={r2vView} reload={vi.fn()} />);
    const camera = screen.getByPlaceholderText('镜头运镜');
    fireEvent.change(camera, { target: { value: '↑ 推近' } });
    fireEvent.blur(camera);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      type: 'UPSERT_SHOT',
      arguments: { shot: { camera: '↑ 推近', framing: '中景', cameraDescription: '↑ 推近' } },
    });
  });

  it('shows the origin R2V running state and manual refresh affordance from durable Tasks', () => {
    useCreatorTaskViewStore.setState({
      projectId: 'p1',
      tasks: [{
        id: 'task-r2v', projectId: 'p1', transactionId: null, specialistRunId: null,
        kind: 'r2v_generation', targetRef: 'unit:u1', status: 'RUNNING', progress: 0.42,
        resultRefs: [], result: null, error: null, updatedAt: '2026-07-11T00:00:00Z',
      }],
    });
    render(<R2VWorkbench projectId="p1" envelope={envelope(r2vView)} view={{ ...r2vView, videoVersions: [] }} reload={vi.fn()} />);
    expect(screen.getByText('R2V 任务生成中…')).toBeInTheDocument();
    expect(screen.getByText('任务已提交，等待最新状态')).toBeInTheDocument();
    expect(screen.queryByText('进度 42%')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '手动刷新' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /视频生成中/ })).toBeDisabled();
  });

  it('adds a default 3-second canonical Shot from the unchanged origin button', async () => {
    const onUpsert = vi.fn().mockResolvedValue({ status: 'APPLIED' });
    render(
      <ShotList
        shots={r2vView.unit.shots}
        unitId="u1"
        onUpsert={onUpsert}
        onDelete={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /添加镜头/ }));
    expect(onUpsert).toHaveBeenCalledTimes(1);
    expect(onUpsert.mock.calls[0][0]).toMatchObject({
      number: 2,
      duration: 3,
      description: '',
      camera: '⊙ 静止',
      framing: '中景',
    });
  });

  it('switches artifact chips locally and submits selection only through 接受', async () => {
    const v1 = artifact('sb-v1', 'r2v_storyboard_image', true);
    const v2 = artifact('sb-v2', 'r2v_storyboard_image');
    const view: R2VWorkbenchView = {
      ...r2vView,
      storyboardVersions: [v1, v2],
      selectedStoryboardVersionId: v1.id,
      blockers: [],
    };
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-select', status: 'APPLIED', eventSeq: 1 } } },
    ]);
    render(<R2VWorkbench projectId="p1" envelope={envelope(view)} view={view} reload={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'v2' }));
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /接\s*受/ }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      type: 'SELECT_ARTIFACT_VERSION',
      targetRef: 'unit:u1',
      arguments: { slotId: v2.slotId, artifactVersionId: v2.id, artifactRef: v2.sourceRef },
    });
  });

  it('restores the origin AI Edit toolbar, VLM/timeline panels, and 340px right rail', () => {
    const { container } = render(
      <AiEditWorkbench
        projectId="p1"
        envelope={envelope(editView)}
        view={editView}
        reload={vi.fn()}
        sectionNumber={3}
        sectionTitle="高潮"
      />,
    );
    expect(container.querySelector('.lg\\:grid-cols-\\[minmax\\(0\\,1fr\\)_340px\\]')).toBeInTheDocument();
    expect(screen.getByText('视频方案 / 03 高潮 / 01 Unit 1 / AI 剪辑工作台')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成方案' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '一键AI剪辑' })).toBeEnabled();
    expect(screen.getByRole('heading', { name: '剪辑目标' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'VLM 关键帧分镜' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '剪辑时间线（1）' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '剪辑成片' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '剪辑素材' })).toBeInTheDocument();
    expect(container.querySelector('[data-creator-field="unit:u1/editPlan/storyboard/panel:panel-1/description"]')).toHaveAttribute(
      'data-creator-path',
      '/production/units_by_id/u1/plan/storyboard/items/panel-1/description',
    );
    expect(container.querySelector('[data-creator-field="unit:u1/editPlan/timeline/clip:clip-01/reason"]')).toHaveAttribute(
      'data-creator-path',
      '/production/units_by_id/u1/plan/timeline/items/clip-01/reason',
    );
    expect(container.querySelector('[data-creator-field="unit:u1/editPlan/timeline/clip:clip-01/overlay/text"]')).toHaveAttribute(
      'data-creator-path',
      '/production/units_by_id/u1/plan/timeline/items/clip-01/overlay/text',
    );
  });

  it('shows the origin two-phase thinking and execution bar from file-native Tasks', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({
          items: url.includes('/specialist-runs')
            ? []
            : useCreatorTaskViewStore.getState().tasks,
        }),
      } as Response;
    }));
    const taskBase = {
      projectId: 'p1', transactionId: null, specialistRunId: null,
      targetRef: 'unit:u1', resultRefs: [], result: null, error: null,
      updatedAt: '2026-07-16T00:00:00Z',
    };
    useCreatorTaskViewStore.setState({
      projectId: 'p1',
      tasks: [{
        ...taskBase,
        id: 'task-plan', kind: 'ai_edit_plan', status: 'RUNNING', progress: 0,
      }],
    });
    render(<AiEditWorkbench projectId="p1" envelope={envelope(editView)} view={editView} reload={vi.fn()} />);

    expect(screen.getByText('AI 思考中')).toBeInTheDocument();
    expect(screen.getByText('AI 执行')).toBeInTheDocument();

    act(() => {
      useCreatorTaskViewStore.setState({
        tasks: [{
          ...taskBase,
          id: 'task-execute', kind: 'ai_edit_execute', status: 'RUNNING', progress: 0.42,
        }],
      });
    });

    expect(await screen.findByText('AI 思考')).toBeInTheDocument();
    expect(screen.getByText('AI 执行 42%')).toBeInTheDocument();
    expect(screen.getByText('正在处理第 1 段 / 共 1 段')).toBeInTheDocument();
    expect(screen.getAllByText('处理中').length).toBeGreaterThan(0);
  });

  it('starts the thinking phase from an AgentDock edit run before an execution Task exists', async () => {
    const started = {
      eventId: 'event-agent-started',
      seq: 1,
      type: 'agent.run.started',
      projectId: 'p1',
      creatorSessionId: 'session-1',
      at: '2026-07-16T00:00:00Z',
      data: {
        runId: 'agent-run-1',
        origin: 'agentdock_idle_goal',
      },
    };
    useCreatorSessionStore.setState({ projectId: 'p1', events: [started] });
    render(<AiEditWorkbench projectId="p1" envelope={envelope(editView)} view={editView} reload={vi.fn()} />);

    expect(screen.getByText('AI 思考中')).toBeInTheDocument();
    expect(screen.getByText('AI 执行')).toBeInTheDocument();

    act(() => {
      useCreatorTaskViewStore.setState({
        projectId: 'p1',
        tasks: [{
          id: 'task-execute', projectId: 'p1', transactionId: null, specialistRunId: null,
          kind: 'ai_edit_execute', targetRef: 'unit:u1', status: 'RUNNING', progress: 0.42,
          resultRefs: [], result: null, error: null,
          createdAt: '2026-07-16T00:00:01Z', updatedAt: '2026-07-16T00:00:02Z',
        }],
      });
    });

    expect(await screen.findByText('AI 思考')).toBeInTheDocument();
    expect(screen.getByText('AI 执行 42%')).toBeInTheDocument();
  });

  it('does not treat initial project creation as an AgentDock thinking phase', () => {
    useCreatorSessionStore.setState({
      projectId: 'p1',
      events: [{
        eventId: 'event-initial-run',
        seq: 1,
        type: 'agent.run.started',
        projectId: 'p1',
        creatorSessionId: 'session-1',
        at: '2026-07-16T00:00:00Z',
        data: { runId: 'initial-run-1', origin: 'initial_creation' },
      }],
    });

    render(<AiEditWorkbench projectId="p1" envelope={envelope(editView)} view={editView} reload={vi.fn()} />);

    expect(screen.queryByText('AI 思考中')).not.toBeInTheDocument();
  });

  it('scrolls to and highlights the clip selected by a pending Review navigation', async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });
    const { container } = render(
      <AiEditWorkbench
        projectId="p1"
        envelope={envelope(editView)}
        view={editView}
        reload={vi.fn()}
      />,
    );

    act(() => {
      useWorkspaceViewStore.getState().setClipHighlights('u1', ['clip-01']);
    });

    const clipPanel = container.querySelector('[data-clip-panel-id="clip-01"]');
    await waitFor(() => expect(clipPanel).toHaveClass('border-[var(--color-accent)]'));
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'nearest',
    }));
    expect(screen.getAllByText('已更新').length).toBeGreaterThan(0);
    expect(useWorkspaceViewStore.getState().clipHighlights.u1).toEqual([]);
  });

  it('submits exact second values for AI Edit clip range without ms conversion', async () => {
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-range', status: 'APPLIED', eventSeq: 1 } } },
    ]);
    const { container } = render(<AiEditWorkbench projectId="p1" envelope={envelope(editView)} view={editView} reload={vi.fn()} />);
    const rangeInputs = container.querySelectorAll<HTMLInputElement>('input[type="number"]');
    expect(rangeInputs.length).toBeGreaterThanOrEqual(2);
    fireEvent.change(rangeInputs[0], { target: { value: '1.375' } });
    fireEvent.blur(rangeInputs[0]);
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '确认时间轴' }));
    await waitFor(() => expect(calls.some((call) => (call.body as { type?: string })?.type === 'SET_EDIT_CLIP_RANGE')).toBe(true));
    const rangeCall = calls.find((call) => (call.body as { type?: string })?.type === 'SET_EDIT_CLIP_RANGE');
    expect(rangeCall?.body).toMatchObject({
      type: 'SET_EDIT_CLIP_RANGE',
      targetRef: 'unit:u1',
      arguments: { clipId: 'clip-01', start: 1.375, end: 8.75 },
    });
    await waitFor(() => expect(screen.getByText('时间线已保存')).toBeInTheDocument());
    expect(calls.filter((call) => (call.body as { type?: string })?.type === 'EXECUTE_EDIT')).toHaveLength(0);
  });

  it('preserves origin cross-Unit timing bounds on the first and last clip', () => {
    const bounded: EditWorkbenchView = {
      ...editView,
      previousUnitLastClipEnd: 3.5,
      nextUnitFirstClipStart: 12.25,
    };
    const { container } = render(<AiEditWorkbench projectId="p1" envelope={envelope(bounded)} view={bounded} reload={vi.fn()} />);
    const rangeInputs = container.querySelectorAll<HTMLInputElement>('input[type="number"]');
    expect(rangeInputs[0]).toHaveAttribute('min', '3.5');
    expect(rangeInputs[1]).toHaveAttribute('max', '12.25');
    expect(screen.getByText('(最早 3.5s)')).toBeInTheDocument();
    expect(screen.getByText('(最長 12.25s)')).toBeInTheDocument();
  });

  it('persists origin OS timing controls through the extended semantic command', async () => {
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-os', status: 'APPLIED', eventSeq: 1 } } },
    ]);
    render(<AiEditWorkbench projectId="p1" envelope={envelope(editView)} view={editView} reload={vi.fn()} />);
    const osLabel = screen.getByText(/OS出现自第一分段/).closest('label');
    const input = osLabel?.querySelector('input');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { value: '2.5' } });
    fireEvent.blur(input!);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      type: 'SET_EDIT_CLIP_OS',
      arguments: {
        clipId: 'clip-01',
        text: '出发',
        vibe: 'action',
        appear_at: 2.5,
        duration: 5,
      },
    });
  });

  it('keeps the origin AI Edit material multi-select and binds an exact canonical source ref', async () => {
    const source = {
      ref: 'asset://video-source@asset-version-2',
      name: '新视频素材',
      type: 'asset' as const,
      version: 'asset-version-2',
      mediaType: 'video',
      logicalAssetId: 'video-source',
      assetVersionId: 'asset-version-2',
      uiLocator: { page: 'assets', assetId: 'video-source', versionId: 'asset-version-2' },
    };
    const view: EditWorkbenchView = {
      ...editView,
      unit: { ...editView.unit, materialRefs: [] },
      resolvedRefs: [source],
    };
    const { calls } = installMockFetch([
      { match: '/commands', response: { json: { commandId: 'c-bind', status: 'APPLIED', eventSeq: 1 } } },
      { match: '/refs?', response: { json: { items: [source] } } },
    ]);
    render(<AiEditWorkbench projectId="p1" envelope={envelope(view)} view={view} reload={vi.fn()} />);
    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('新视频素材'));
    await waitFor(() => expect(calls.some((call) => (call.body as { type?: string })?.type === 'BIND_REFERENCE')).toBe(true));
    const bind = calls.find((call) => (call.body as { type?: string })?.type === 'BIND_REFERENCE');
    expect(bind?.body).toMatchObject({
      type: 'BIND_REFERENCE',
      targetRef: 'unit:u1',
      arguments: { field: 'sources', referenceSet: 'unit', sourceRef: source.ref },
    });
  });

  it('routes the origin AI Edit storyboard fallback through the controlled media endpoint', () => {
    const view: EditWorkbenchView = {
      ...editView,
      plan: null,
      storyboard_image_url: '/generated/storyboard.png',
      planVersion: null,
      planRef: null,
      readiness: { ready: false, blockers: ['AI_EDIT_PLAN_VERSION_REQUIRED'] },
      blockers: ['AI_EDIT_PLAN_VERSION_REQUIRED'],
    };
    render(<AiEditWorkbench projectId="p1" envelope={envelope(view)} view={view} reload={vi.fn()} />);
    expect(screen.getByAltText('AI 剪辑关键帧分镜')).toHaveAttribute('src', '/api/creator/generated/storyboard.png');
  });

  it('renders a richer canonical migrated AI Edit envelope in the origin surface', () => {
    const migratedView: EditWorkbenchView = {
      kind: 'edit',
      unit: { ...editView.unit, id: 'edit-e2e-long-highlight' },
      goal: '从长视频剪出高光',
      plan: {
        summary: '迁移出的剪辑摘要',
        target_duration: 56,
        timeline: [{ clip_id: 'clip-01', asset_id: 'source-01', asset_name: '十分钟足球素材', source_url: '/generated/source.mp4', asset_version_id: 'asset-version-01', start: 0, end: 8, duration: 8, order: 1, transition: 'cut' }],
        storyboard: [{ panel_id: 'panel-01', order: 1, title: '真实关键帧', description: '迁移的真实时间码画面', source_asset_id: 'source-01', timestamp: 4, timeline_start: 0, timeline_end: 8 }],
        audio_plan: { bgm: '保留' },
      },
      storyboard_image_url: '/generated/migrated-board.png',
      material_assets: [{ id: 'source-01', name: '十分钟足球素材', url: '/generated/source.mp4' }],
      workflow_trace: [],
      videoVersions: [],
      planVersion: { id: 'plan-version-01', checksum: 'sha256:plan', createdAt: 'now' },
      planRef: 'ai-edit-plan://edit-e2e-long-highlight@plan-version-01',
      resolvedRefs: [],
      relations: [],
      readiness: { ready: true },
      blockers: [],
      targetVersion: 'ov-edit',
      uiLocator: { page: 'workbench', unitId: 'edit-e2e-long-highlight', route: 'edit' },
    };

    const { container } = render(<AiEditWorkbench projectId="p1" envelope={envelope(migratedView)} view={migratedView} reload={vi.fn()} />);
    expect(screen.getAllByText(/十分钟足球素材/).length).toBeGreaterThan(0);
    expect(screen.getByText('真实关键帧')).toBeInTheDocument();
    expect(screen.getByAltText('#1 真实关键帧 关键帧')).toHaveAttribute(
      'src',
      '/api/creator/media/assets/asset-version-01/frame?timestamp=4.000&width=640',
    );
    expect(container.querySelector('video[data-clip-start]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '播放分镜片段 #1 真实关键帧' }));
    const clipPreview = container.querySelector<HTMLVideoElement>('video[src="/api/creator/media/assets/asset-version-01#t=0,8"]');
    expect(clipPreview).toBeInTheDocument();
    expect(clipPreview).toHaveAttribute('playsinline');
    expect(clipPreview).toHaveAttribute('data-clip-start', '0');
    expect(clipPreview).toHaveAttribute('data-clip-end', '8');
    expect(clipPreview?.muted).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '显示关键帧 #1 真实关键帧' }));
    expect(container.querySelector('video[data-clip-start]')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /一键AI剪辑/ })).toBeEnabled();
  });

  it('matches storyboard panels to timeline clips by the latest origin/main clip_id contract', () => {
    const view: EditWorkbenchView = {
      ...editView,
      plan: {
        ...editView.plan!,
        timeline: [
          { clip_id: 'clip-a', asset_id: 'a1', asset_name: '源视频', source_url: '/generated/source.mp4', start: 0, end: 4, duration: 4, order: 1 },
          { clip_id: 'clip-b', asset_id: 'a1', asset_name: '源视频', source_url: '/generated/source.mp4', start: 10, end: 15, duration: 5, order: 2 },
        ],
        storyboard: [
          { panel_id: 'panel-b', clip_id: 'clip-b', order: 1, title: '后段画面', description: '后段', source_asset_id: 'a1', timestamp: 12 },
          { panel_id: 'panel-a', clip_id: 'clip-a', order: 2, title: '前段画面', description: '前段', source_asset_id: 'a1', timestamp: 2 },
        ],
      },
    };

    render(<AiEditWorkbench projectId="p1" envelope={envelope(view)} view={view} reload={vi.fn()} />);
    const laterCard = screen.getByText('#1 后段画面').parentElement!.parentElement!;
    const earlierCard = screen.getByText('#2 前段画面').parentElement!.parentElement!;
    const laterInputs = laterCard.querySelectorAll<HTMLInputElement>('input[type="number"]');
    const earlierInputs = earlierCard.querySelectorAll<HTMLInputElement>('input[type="number"]');
    expect([...laterInputs].map((input) => input.value)).toEqual(['10', '15']);
    expect([...earlierInputs].map((input) => input.value)).toEqual(['0', '4']);
    expect(earlierInputs[1]).toHaveAttribute('max', '10');
    expect(screen.getAllByText('后段画面').length).toBeGreaterThan(0);
    expect(screen.getAllByText('前段画面').length).toBeGreaterThan(0);
  });

  it('renders the exact origin empty states for a canonical workbench before its plan exists', () => {
    const sparseView: EditWorkbenchView = {
      kind: 'edit',
      unit: { ...editView.unit, id: 'empty-edit' },
      plan: null,
      storyboard_image_url: null,
      material_assets: [],
      workflow_trace: [],
      videoVersions: [],
      planVersion: null,
      planRef: null,
      resolvedRefs: [],
      relations: [],
      readiness: { ready: false, blockers: ['AI_EDIT_PLAN_VERSION_REQUIRED'] },
      blockers: ['AI_EDIT_PLAN_VERSION_REQUIRED'],
      targetVersion: 'ov-empty-edit',
      uiLocator: { page: 'workbench', unitId: 'empty-edit', route: 'edit' },
    };

    render(<AiEditWorkbench projectId="p1" envelope={envelope(sparseView)} view={sparseView} reload={vi.fn()} />);
    expect(screen.getByText('尚未生成关键帧分镜')).toBeInTheDocument();
    expect(screen.getByText('生成剪辑方案后会显示素材取舍、时间段和转场建议。')).toBeInTheDocument();
    expect(screen.getByText('暂无视频素材。请在新建项目处选择文件夹或上传视频。')).toBeInTheDocument();
    expect(screen.getByText('尚未执行剪辑')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /一键AI剪辑/ })).toBeEnabled();
  });
});
