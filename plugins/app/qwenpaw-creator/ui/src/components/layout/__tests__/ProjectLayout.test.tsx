import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { CREATOR_ROUTE_OBJECTS } from '@/app/router';
import { installMockFetch } from '@/test/mockFetch';
import { editView, envelope, headerView, planView, status } from '@/test/creatorFixtures';
import type { FileProjectReviewRecord } from '@/contracts/creator';
import { useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { useAgentDockUiStore } from '@/store/agentDockUiStore';
import { useProjectSnapshotStore } from '@/store/projectSnapshotStore';
import { useFileProjectReviewStore } from '@/store/fileProjectReviewStore';
import AgentStatusBar from '@/components/layout/AgentStatusBar';
import ProjectLayout from '@/components/layout/ProjectLayout';

function clipReview(): FileProjectReviewRecord {
  return {
    review_id: 'review-clip-1',
    round_id: 'round-clip-1',
    request_id: 'request-clip-1',
    request_message_seq: 2,
    interrupted_run_id: 'run-clip-1',
    baseline_generation: 1,
    baseline_etag: 'base-1',
    candidate_generation: 2,
    candidate_etag: 'candidate-2',
    decision_token: 'review-token-1',
    status: 'PENDING',
    operations: [{
      kind: 'update',
      json_pointer: '/production/units_by_id/u1/plan/timeline/items/clip-01/source_in_seconds',
      file_id: null,
      target_ref: null,
      before_hash: 'before',
      after_hash: 'after',
      before: 1,
      after: 2,
      operation_id: 'operation-clip-1',
      ui_locator: {},
      decision: 'PENDING',
    }],
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:01Z',
  };
}

describe('ProjectLayout visible shell', () => {
  beforeEach(() => {
    useWorkspaceViewStore.getState().reset();
    useCreatorSessionStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
    useAgentDockUiStore.getState().reset();
    useProjectSnapshotStore.getState().reset();
    useFileProjectReviewStore.getState().reset();
  });
  it('preserves the 58/42 shell and default-open 440px AgentDock sidebar on a formal route', async () => {
    const { calls } = installMockFetch([
      { match: '/projects/p1/runtime/reviews/active', response: { status: 204 } },
      { match: '/projects/p1/conversations/c1/messages', response: { json: { items: [] } } },
      { match: '/projects/p1/specialist-runs', response: { json: { items: [] } } },
      { match: '/projects/p1/conversations', response: { json: { items: [{ conversationId: 'c1', title: '默认对话', isDefault: true, createdAt: 'now' }] } } },
      { match: '/projects/p1/session', response: { json: { session: { id: 's1', projectId: 'p1', status: 'RUNNING', activeTransactionId: 'tx1', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 0 }, agentStatusBar: status } } },
      { match: '/projects/p1/header', response: { json: envelope(headerView) } },
      { match: '/projects/p1/plan', response: { json: envelope(planView) } },
      { match: '/projects/p1/tasks', response: { json: { items: [] } } },
      { match: '/models/config', response: { json: { llm: { enabled: true, model_name: 'qwen3.7-plus', api_key: '', base_url: '', protocol: 'OpenAI 协议', custom_protocol: '', multimodal: true }, vlm: { enabled: true, model_name: 'qwen3.7-plus', api_key: '', base_url: '', protocol: 'OpenAI 协议', custom_protocol: '', use_llm: true, multimodal: true }, image: { enabled: true, model_name: 'qwen-image-2.0-pro', api_key: '', base_url: '', protocol: 'DashScope', custom_protocol: '' }, video: { enabled: true, model_name: 'wan2.7-r2v', api_key: '', base_url: '', protocol: 'DashScope', custom_protocol: '' } } } },
    ]);
    const router = createMemoryRouter(CREATOR_ROUTE_OBJECTS, { initialEntries: ['/project/p1/plan'] });
    const rendered = render(<RouterProvider router={router} />);
    await waitFor(() => expect(screen.getByText('测试项目')).toBeInTheDocument());
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/project'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/runtime/reviews/active'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.includes('/transactions/'))).toHaveLength(0);
    expect(useFileProjectReviewStore.getState().polling).toBe(true);
    const shell = document.querySelector('[data-project-shell]')!;
    expect(shell).toHaveAttribute('data-top-nav-height', '58');
    expect(shell).toHaveAttribute('data-agent-status-bar-height', '42');
    expect(document.querySelector('[data-agent-status-bar]')).toHaveClass('h-[42px]');
    const dock = document.querySelector('[data-agent-dock]')!;
    expect(useAgentDockUiStore.getState().open).toBe(true);
    expect(dock).toHaveAttribute('data-agent-dock-width', '440');
    expect(dock).toHaveAttribute('data-agent-dock-height', '620');
    expect(dock).toHaveClass('relative', 'h-full', 'border-l');
    expect(dock).not.toHaveClass('fixed', 'rounded-2xl');
    expect(document.querySelector('[title="拖拽调整高度"]')).not.toBeInTheDocument();
    expect(document.querySelector('[title="拖拽调整宽度"]')).toHaveClass('left-0');

    act(() => useCreatorSessionStore.getState().ingestEvents([
      { eventId: 'event-message-1', seq: 1, type: 'message.appended', projectId: 'p1', creatorSessionId: 's1', at: 'now', data: { messageSeq: 1 } },
      { eventId: 'event-message-2', seq: 2, type: 'message.completed', projectId: 'p1', creatorSessionId: 's1', at: 'now', data: { messageSeq: 2 } },
      { eventId: 'event-review-legacy', seq: 3, type: 'transaction.pending_review', projectId: 'p1', creatorSessionId: 's1', transactionId: 'tx1', at: 'now', data: {} },
      { eventId: 'event-file-run', seq: 4, type: 'agent.run.completed', projectId: 'p1', creatorSessionId: 's1', at: 'now', data: { runId: 'run-file-1', reviewIds: [] } },
    ]));
    await waitFor(() => expect(
      calls.filter((call) => call.url.includes('/conversations/c1/messages')),
    ).toHaveLength(2));
    await waitFor(() => expect(
      calls.filter((call) => call.url.endsWith('/projects/p1/session')),
    ).toHaveLength(2));
    expect(calls.filter((call) => call.url.includes('/transactions/'))).toHaveLength(0);
    rendered.unmount();
    expect(useFileProjectReviewStore.getState().projectId).toBeNull();
    expect(useFileProjectReviewStore.getState().polling).toBe(false);
  });

  it('renders progress and badges without duplicating the authoritative activity label', () => {
    useCreatorSessionStore.setState({
      connected: true,
      session: { id: 's1', projectId: 'p1', status: 'RUNNING', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 5 },
      agentStatusBar: {
        progress: { phase: 'review', label: '后端聚合进度', sourceEventSeq: 5, updatedAt: 'now' },
        activity: { label: '后端聚合活动', runningTaskCount: 2 },
        badges: [{ kind: 'review', label: '待处理 3', count: 3 }],
      },
    });
    useCreatorTaskViewStore.setState({ runs: [], tasks: [] });
    render(<AgentStatusBar />);
    expect(screen.getByText(/后端聚合进度/)).toBeInTheDocument();
    expect(screen.queryByText('后端聚合活动')).not.toBeInTheDocument();
    expect(screen.getByText('待处理 3')).toBeInTheDocument();
    expect(screen.queryByText(/Run ·/)).not.toBeInTheDocument();
  });

  it('keeps the active Outlet mounted while an existing Header is revalidated', async () => {
    useWorkspaceViewStore.setState({
      projectId: 'p1',
      header: envelope(headerView),
      plan: envelope(planView),
    });
    const { calls } = installMockFetch([
      { match: '/projects/p1/conversations/c1/messages', response: { json: { items: [] } } },
      { match: '/projects/p1/specialist-runs', response: { json: { items: [] } } },
      { match: '/projects/p1/conversations', response: { json: { items: [{ conversationId: 'c1', title: '默认对话', isDefault: true, createdAt: 'now' }] } } },
      { match: '/projects/p1/session', response: { json: { session: { id: 's1', projectId: 'p1', status: 'IDLE', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 0 }, agentStatusBar: status } } },
      { match: '/projects/p1/header', response: { json: envelope(headerView) } },
      { match: '/projects/p1/plan', response: { json: envelope(planView) } },
      { match: '/projects/p1/tasks', response: { json: { items: [] } } },
      { match: '/models/config', response: { json: { llm: { enabled: true, model_name: 'qwen3.7-plus' }, vlm: { enabled: true, model_name: 'qwen3.7-plus', use_llm: true }, image: { enabled: true, model_name: 'qwen-image-2.0-pro' }, video: { enabled: true, model_name: 'wan2.7-r2v' } } } },
    ]);
    const router = createMemoryRouter([
      {
        path: '/project/:id',
        element: <ProjectLayout />,
        children: [{ path: 'plan', element: <div data-testid="active-project-route">Active route</div> }],
      },
    ], { initialEntries: ['/project/p1/plan'] });

    render(<RouterProvider router={router} />);
    expect(await screen.findByTestId('active-project-route')).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((call) => call.url.includes('/models/config'))).toHaveLength(1));

    act(() => {
      useWorkspaceViewStore.setState((state) => ({
        loading: { ...state.loading, header: true },
      }));
    });
    expect(screen.getByTestId('active-project-route')).toBeInTheDocument();
    expect(calls.filter((call) => call.url.includes('/models/config'))).toHaveLength(1);

    act(() => {
      useWorkspaceViewStore.setState((state) => ({
        loading: { ...state.loading, header: false },
      }));
    });
    expect(screen.getByTestId('active-project-route')).toBeInTheDocument();
    expect(calls.filter((call) => call.url.includes('/models/config'))).toHaveLength(1);

    const dock = document.querySelector('[data-agent-dock]');
    act(() => {
      useWorkspaceViewStore.setState((state) => ({
        errors: { ...state.errors, header: '瞬时 Header 重校验失败' },
      }));
      useCreatorSessionStore.setState({ error: '瞬时 Session 重校验失败' });
    });
    expect(screen.getByTestId('active-project-route')).toBeInTheDocument();
    expect(document.querySelector('[data-agent-dock]')).toBe(dock);

    expect(calls.filter((call) => call.url.endsWith('/projects/p1/header'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/plan'))).toHaveLength(1);
    act(() => useProjectSnapshotStore.setState({
      projectId: 'p1', generation: 1, etag: 'sha256:g1',
    }));
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/header'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/plan'))).toHaveLength(1);

    act(() => useProjectSnapshotStore.setState({
      projectId: 'p1', generation: 2, etag: 'sha256:g2',
    }));
    await waitFor(() => expect(
      calls.filter((call) => call.url.endsWith('/projects/p1/header')),
    ).toHaveLength(2));
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/plan'))).toHaveLength(2);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/assets'))).toHaveLength(0);
  });

  it('does not close AgentDock when the same project shell mounts again', async () => {
    useWorkspaceViewStore.setState({
      projectId: 'p1',
      header: envelope(headerView),
      plan: envelope(planView),
    });
    useCreatorSessionStore.setState({
      projectId: 'p1',
      session: { id: 's1', projectId: 'p1', status: 'IDLE', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 4 },
      activeConversationId: 'c1',
      events: [
        { eventId: 'e3', seq: 3, type: 'workspace.head_changed', projectId: 'p1', creatorSessionId: 's1', at: 'now', data: {} },
        { eventId: 'e4', seq: 4, type: 'task.progress_updated', projectId: 'p1', creatorSessionId: 's1', at: 'now', data: {} },
      ],
      lastEventSeq: 4,
    });
    useAgentDockUiStore.getState().setOpen(true);
    const { calls } = installMockFetch([
      { match: '/projects/p1/conversations/c1/messages', response: { json: { items: [] } } },
      { match: '/projects/p1/specialist-runs', response: { json: { items: [] } } },
      { match: '/projects/p1/conversations', response: { json: { items: [{ conversationId: 'c1', title: '默认对话', isDefault: true, createdAt: 'now' }] } } },
      { match: '/projects/p1/session', response: { json: { session: { id: 's1', projectId: 'p1', status: 'IDLE', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 4 }, agentStatusBar: status } } },
      { match: '/projects/p1/header', response: { json: envelope(headerView) } },
      { match: '/projects/p1/plan', response: { json: envelope(planView) } },
      { match: '/projects/p1/tasks', response: { json: { items: [] } } },
      { match: '/models/config', response: { json: { llm: { enabled: true, model_name: 'qwen3.7-plus' }, vlm: { enabled: true, model_name: 'qwen3.7-plus', use_llm: true }, image: { enabled: true, model_name: 'qwen-image-2.0-pro' }, video: { enabled: true, model_name: 'wan2.7-r2v' } } } },
    ]);
    const router = createMemoryRouter([
      {
        path: '/project/:id',
        element: <ProjectLayout />,
        children: [{ path: 'plan', element: <div data-testid="same-project-route">Same project</div> }],
      },
    ], { initialEntries: ['/project/p1/plan'] });

    render(<RouterProvider router={router} />);

    expect(await screen.findByTestId('same-project-route')).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('[data-agent-dock]')).toBeInTheDocument());
    expect(useAgentDockUiStore.getState().open).toBe(true);
    await waitFor(() => expect(calls.filter((call) => call.url.includes('/projects/p1/tasks'))).toHaveLength(1));
    expect(calls.filter((call) => call.url.includes('/projects/p1/header'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/session'))).toHaveLength(1);

    await act(async () => {
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: 'nested-message-delta', seq: 5, type: 'subagent.message_delta', projectId: 'p1',
          creatorSessionId: 's1', at: 'now', data: {
            parentActionId: 'delegate-1', runId: 'run-1', role: 'story_planning_agent',
            messageId: 'sub-message-1', deltaIndex: 0, delta: '实时内容',
          },
        },
        {
          eventId: 'nested-tool-started', seq: 6, type: 'subagent.tool_started', projectId: 'p1',
          creatorSessionId: 's1', at: 'now', data: {
            parentActionId: 'delegate-1', runId: 'run-1', role: 'story_planning_agent',
            toolCallId: 'tool-1', tool: 'read_project_file', arguments: {}, state: 'started',
          },
        },
        {
          eventId: 'nested-tool-completed', seq: 7, type: 'subagent.tool_completed', projectId: 'p1',
          creatorSessionId: 's1', at: 'now', data: {
            parentActionId: 'delegate-1', runId: 'run-1', role: 'story_planning_agent',
            toolCallId: 'tool-1', tool: 'read_project_file', result: {}, state: 'succeeded',
          },
        },
        {
          eventId: 'nested-message-completed', seq: 8, type: 'subagent.message_completed', projectId: 'p1',
          creatorSessionId: 's1', at: 'now', data: {
            parentActionId: 'delegate-1', runId: 'run-1', role: 'story_planning_agent',
            messageId: 'sub-message-1', text: '[SUCCESS]\n完成', finishReason: 'stop',
          },
        },
      ]);
      await Promise.resolve();
    });
    expect(calls.filter((call) => call.url.includes('/projects/p1/tasks'))).toHaveLength(1);
    expect(calls.filter((call) => call.url.endsWith('/projects/p1/session'))).toHaveLength(1);
  });

  it('navigates to and queues the changed clip only for a completed run with a Review', async () => {
    const review = clipReview();
    const { calls } = installMockFetch([
      {
        match: '/projects/p1/runtime/reviews/active',
        response: {
          json: review,
          headers: { ETag: `"${review.decision_token}"` },
        },
      },
      { match: '/projects/p1/conversations/c1/messages', response: { json: { items: [] } } },
      { match: '/projects/p1/specialist-runs', response: { json: { items: [] } } },
      { match: '/projects/p1/conversations', response: { json: { items: [{ conversationId: 'c1', title: '默认对话', isDefault: true, createdAt: 'now' }] } } },
      { match: '/projects/p1/session', response: { json: { session: { id: 's1', projectId: 'p1', status: 'RUNNING', lastMessageSeq: 0, lastConsumedMessageSeq: 0, lastEventSeq: 0 }, agentStatusBar: status } } },
      { match: '/projects/p1/header', response: { json: envelope(headerView) } },
      { match: '/projects/p1/plan', response: { json: envelope(planView) } },
      { match: '/projects/p1/units/u1/workbench', response: { json: envelope(editView) } },
      { match: '/projects/p1/tasks', response: { json: { items: [] } } },
      { match: '/models/config', response: { json: { llm: { enabled: true, model_name: 'qwen3.7-plus' }, vlm: { enabled: true, model_name: 'qwen3.7-plus', use_llm: true }, image: { enabled: true, model_name: 'qwen-image-2.0-pro' }, video: { enabled: true, model_name: 'wan2.7-r2v' } } } },
    ]);
    const router = createMemoryRouter([
      {
        path: '/project/:id',
        element: <ProjectLayout />,
        children: [
          { path: 'plan', element: <div data-testid="review-plan-route">Plan</div> },
          { path: 'plan/unit/:unitId/workbench', element: <div data-testid="review-workbench-route">Workbench</div> },
        ],
      },
    ], { initialEntries: ['/project/p1/plan'] });

    render(<RouterProvider router={router} />);
    expect(await screen.findByTestId('review-plan-route')).toBeInTheDocument();
    await waitFor(() => expect(
      calls.filter((call) => call.url.endsWith('/projects/p1/runtime/reviews/active')),
    ).toHaveLength(1));
    act(() => {
      useCreatorSessionStore.getState().ingestEvents([{
        eventId: 'run-without-review',
        seq: 1,
        type: 'agent.run.completed',
        projectId: 'p1',
        creatorSessionId: 's1',
        at: 'now',
        data: { runId: 'run-initial', reviewIds: [] },
      }]);
    });
    await Promise.resolve();
    expect(screen.getByTestId('review-plan-route')).toBeInTheDocument();
    expect(calls.filter((call) => call.url.includes('/units/u1/workbench'))).toHaveLength(0);

    act(() => useCreatorSessionStore.getState().ingestEvents([{
      eventId: 'run-with-review',
      seq: 2,
      type: 'agent.run.completed',
      projectId: 'p1',
      creatorSessionId: 's1',
      at: 'now',
      data: { runId: 'run-clip-1', reviewIds: ['review-clip-1'] },
    }]));

    expect(await screen.findByTestId('review-workbench-route')).toBeInTheDocument();
    expect(useWorkspaceViewStore.getState().clipHighlights.u1).toEqual(['clip-01']);
  });
});
