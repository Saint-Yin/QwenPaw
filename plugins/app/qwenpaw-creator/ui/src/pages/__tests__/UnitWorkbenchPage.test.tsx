import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, RouterProvider, Routes, createMemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import UnitWorkbenchPage from '@/pages/UnitWorkbenchPage';
import { assetView, envelope, headerView, planView, r2vView, status } from '@/test/creatorFixtures';
import { installMockFetch } from '@/test/mockFetch';
import { useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { CREATOR_ROUTE_OBJECTS } from '@/app/router';

describe('UnitWorkbenchPage origin presentation routing', () => {
  beforeEach(() => {
    useWorkspaceViewStore.getState().reset();
    useCreatorSessionStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
  });

  it('derives the original section/unit breadcrumb from canonical Header + Plan Views', async () => {
    const assetsWithPlannedVisual = {
      ...assetView,
      visualAssets: [{
        id: 'planned-scene',
        name: '待生成场景',
        category: 'scene' as const,
        selectedRef: null,
        resolvedRef: null,
        existence: 'planned' as const,
        presentationStatus: 'draft' as const,
        mediaType: 'image',
        referenceRefs: [],
        referenceCount: 0,
        uiLocator: { page: 'assets', assetId: 'planned-scene' },
      }],
    };
    useWorkspaceViewStore.setState({
      projectId: 'p1',
      header: envelope(headerView),
      plan: envelope(planView),
    });
    const { calls } = installMockFetch([
      { match: '/projects/p1/assets', response: { json: envelope(assetsWithPlannedVisual) } },
      { match: '/projects/p1/units/u1/workbench', response: { json: envelope(r2vView) } },
    ]);

    render(
      <MemoryRouter initialEntries={['/project/p1/plan/unit/u1/workbench']}>
        <Routes>
          <Route path="/project/:id/plan/unit/:unitId/workbench" element={<UnitWorkbenchPage />} />
          <Route path="/project/:id/plan" element={<div>视频方案页</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('视频方案 / 01 开场 / 01 Unit 1 / 制作工作台')).toBeInTheDocument();
    });
    expect(calls.filter((call) => call.url.endsWith('/header'))).toHaveLength(0);
    expect(calls.filter((call) => call.url.endsWith('/plan'))).toHaveLength(0);
    expect(calls.filter((call) => call.url.endsWith('/assets'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/units/u1/workbench'))).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '返回视频方案' }));
    expect(await screen.findByText('视频方案页')).toBeInTheDocument();
  });

  it('settles the formal Workbench route without remounting or repeating bootstrap requests', async () => {
    const { calls } = installMockFetch([
      { match: '/projects/p1/conversations/c1/messages', response: { json: { items: [] } } },
      { match: '/projects/p1/specialist-runs', response: { json: { items: [] } } },
      { match: '/projects/p1/conversations', response: { json: { items: [{ conversationId: 'c1', title: '默认对话', isDefault: true, createdAt: 'now' }] } } },
      { match: '/projects/p1/session', response: { json: { session: { id: 's1', projectId: 'p1', status: 'IDLE', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 0 }, agentStatusBar: status } } },
      { match: '/projects/p1/header', response: { json: envelope(headerView) } },
      { match: '/projects/p1/plan', response: { json: envelope(planView) } },
      { match: '/projects/p1/assets', response: { json: envelope(assetView) } },
      { match: '/projects/p1/units/u1/workbench', response: { json: envelope(r2vView) } },
      { match: '/projects/p1/tasks', response: { json: { items: [] } } },
      { match: '/models/config', response: { json: { llm: { enabled: true, model_name: 'qwen3.7-plus' }, vlm: { enabled: true, model_name: 'qwen3.7-plus', use_llm: true }, image: { enabled: true, model_name: 'qwen-image-2.0-pro' }, video: { enabled: true, model_name: 'wan2.7-r2v' } } } },
    ]);
    const router = createMemoryRouter(CREATOR_ROUTE_OBJECTS, {
      initialEntries: ['/project/p1/plan/unit/u1/workbench'],
    });

    render(<RouterProvider router={router} />);
    expect(await screen.findByRole('heading', { name: 'Shot 列表（1）' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '分镜文本' })).not.toBeInTheDocument();
    const breadcrumb = screen.getByRole('navigation', { name: '面包屑' });
    expect(breadcrumb).toHaveTextContent('视频方案');
    expect(breadcrumb).toHaveTextContent('01 开场');
    expect(breadcrumb).toHaveTextContent('01 Unit 1');
    expect(breadcrumb).toHaveTextContent('制作工作台');
    await waitFor(() => {
      expect(calls.filter((call) => call.url.endsWith('/header'))).toHaveLength(1);
      expect(calls.filter((call) => call.url.endsWith('/plan'))).toHaveLength(1);
      expect(calls.filter((call) => call.url.endsWith('/assets'))).toHaveLength(1);
      expect(calls.filter((call) => call.url.endsWith('/units/u1/workbench'))).toHaveLength(1);
      expect(calls.filter((call) => call.url.includes('/models/config'))).toHaveLength(1);
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(calls.filter((call) => call.url.endsWith('/header'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/plan'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/assets'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/units/u1/workbench'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.includes('/models/config'))).toHaveLength(1);
  });
});
