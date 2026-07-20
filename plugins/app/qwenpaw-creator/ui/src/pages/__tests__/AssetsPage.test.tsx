import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { message, Modal } from 'antd';
import { beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import AssetsPage from '@/pages/AssetsPage';
import type { AssetLibraryView } from '@/contracts/creator';
import { assetView, envelope } from '@/test/creatorFixtures';
import { installMockFetch } from '@/test/mockFetch';
import { useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { useNavigationStore } from '@/store/navigationStore';

function renderPage(entry = '/project/p1/assets') {
  return render(<MemoryRouter initialEntries={[entry]}><Routes><Route path="/project/:id/assets" element={<AssetsPage />} /></Routes></MemoryRouter>);
}

describe('AssetsPage', () => {
  beforeEach(() => {
    useWorkspaceViewStore.getState().reset();
    useCreatorSessionStore.setState({ events: [] });
    useCreatorTaskViewStore.getState().reset();
    useNavigationStore.getState().clear();
  });

  it('preserves the origin/main category-grid-inspector information architecture', async () => {
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(assetView) } }]);
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: '用户上传 1' })).toBeInTheDocument());
    expect(screen.getByRole('complementary', { name: '资产分类' })).toHaveClass('flex', 'w-52', 'shrink-0', 'flex-col');
    expect(screen.getByTestId('asset-grid-column')).toHaveClass('flex', 'min-w-0', 'flex-1', 'flex-col');
    expect(screen.getByRole('button', { name: '全部资产 1' })).toHaveClass('bg-[var(--color-accent-soft)]', 'text-[var(--color-accent)]');
    expect(screen.getByText('补充资料')).toBeInTheDocument();
    expect(screen.getByText('AI 生成所有资产描述')).toBeInTheDocument();
    const card = screen.getByText('素材一').closest('article');
    expect(card).toHaveClass('group', 'cursor-pointer', 'overflow-hidden', 'rounded-xl', 'border', 'bg-[var(--color-bg-card)]');
    fireEvent.click(card!);
    expect(card).toHaveClass('border-[var(--color-accent)]', 'shadow-[0_0_0_1px_var(--color-accent)]');
    expect(screen.getByText('来源')).toBeInTheDocument();
    expect(screen.getByText('被引用（0）')).toBeInTheDocument();
    expect(screen.getByText('作用约束')).toBeInTheDocument();
    expect(screen.getByText('来源').closest('aside')).toHaveClass('w-80', 'shrink-0');
  });

  it('requires the server presentation DTO and never reconstructs cards from availableAssets', async () => {
    type PresentationAssetsIsRequired = {} extends Pick<AssetLibraryView, 'presentationAssets'> ? false : true;
    expectTypeOf<PresentationAssetsIsRequired>().toEqualTypeOf<true>();

    const explicitEmptyPresentation: AssetLibraryView = { ...assetView, presentationAssets: [] };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(explicitEmptyPresentation) } }]);
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: '全部资产 0' })).toBeInTheDocument());
    expect(screen.getByText('资产库还是空的')).toBeInTheDocument();
    expect(screen.queryByText('素材一')).not.toBeInTheDocument();
  });

  it('serves selected visual artifacts through the Creator media endpoint instead of file URLs', async () => {
    const visualView: AssetLibraryView = {
      ...assetView,
      presentationAssets: [{
        id: 'orange-cat',
        name: '圆润大橘猫',
        category: 'subject_ref',
        existence: 'available',
        presentationStatus: 'accepted',
        mediaType: 'image',
        url: 'file:///private/runtime/orange-cat.png',
        sourceDescription: '角色锚点',
        sourceRef: 'artifact://slot-orange-cat@artifact-version-orange-cat-v1',
        referenceCount: 0,
        targetVersion: 'ov-orange-cat',
        detail: {
          id: 'orange-cat',
          name: '圆润大橘猫',
          kind: 'character',
          mediaType: 'image',
          primaryUrl: 'file:///private/runtime/orange-cat.png',
          images: [{ id: 'artifact-version-orange-cat-v1', name: '正面锚点', url: 'file:///private/runtime/orange-cat.png' }],
          refsNeeded: ['正面锚点'],
          prompts: ['圆润大橘猫'],
          referenceImageRefs: [[]],
        },
        uiLocator: { page: 'assets', assetId: 'orange-cat' },
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(visualView) } }]);
    renderPage();
    const image = await screen.findByRole('img', { name: '圆润大橘猫' });
    expect(image).toHaveAttribute('src', '/api/creator/media/artifacts/artifact-version-orange-cat-v1');
    expect(image).not.toHaveAttribute('src', expect.stringContaining('file://'));
  });

  it('resolves a visual selected from an uploaded version through the logical source Asset', async () => {
    const visualView: AssetLibraryView = {
      ...assetView,
      presentationAssets: [{
        id: 'hero-visual',
        name: '主角参考',
        category: 'subject_ref',
        existence: 'available',
        presentationStatus: 'accepted',
        mediaType: 'image/png',
        url: '/media/assets/av-hero',
        sourceDescription: '上传参考图',
        sourceRef: 'asset://hero-source@av-hero',
        referenceCount: 0,
        assetVersionId: 'av-hero',
        uiLocator: { page: 'assets', assetId: 'hero-visual' },
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(visualView) } }]);
    renderPage();

    const image = await screen.findByRole('img', { name: '主角参考' });
    expect(image).toHaveAttribute('src', '/api/creator/projects/p1/assets/hero-source/content?versionId=av-hero');
  });

  it('does not mount uploaded media before its durable ingest succeeds', async () => {
    const runningView: AssetLibraryView = {
      ...assetView,
      ingestItems: [{
        taskId: 'task-video', assetId: 'a-video', assetVersionId: 'av-video', name: 'clip.mp4',
        status: 'RUNNING', progress: 0.42, error: null,
      }],
      presentationAssets: [{
        ...assetView.presentationAssets[0],
        id: 'a-video',
        name: 'clip.mp4',
        mediaType: 'video/mp4',
        sourceRef: 'asset://a-video@av-video',
        assetVersionId: 'av-video',
        uiLocator: { page: 'assets', assetId: 'a-video', versionId: 'av-video' },
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(runningView) } }]);
    renderPage();

    expect((await screen.findAllByText('入库中')).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByLabelText('clip.mp4 视频')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'clip.mp4' })).not.toBeInTheDocument();
  });

  it('renders successful uploaded and generated videos as real video elements and hides load failures', async () => {
    const successfulView: AssetLibraryView = {
      ...assetView,
      presentationAssets: [
        {
          ...assetView.presentationAssets[0],
          id: 'a-video',
          name: '上传片段',
          mediaType: 'video/mp4',
          sourceRef: 'asset://a-video@av-video',
          assetVersionId: 'av-video',
          uiLocator: { page: 'assets', assetId: 'a-video', versionId: 'av-video' },
        },
        {
          id: 'artifact-video',
          name: '生成片段',
          category: 'generated',
          existence: 'available',
          presentationStatus: 'accepted',
          mediaType: 'unit_video',
          url: '/legacy/generated.mp4',
          sourceDescription: '生成资产',
          sourceRef: 'artifact://unit-video@artifact-video',
          referenceCount: 0,
          generatedKind: 'unit_video',
          artifactVersionId: 'artifact-video',
          uiLocator: { page: 'workbench', unitId: 'unit-1', versionId: 'artifact-video' },
        },
      ],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(successfulView) } }]);
    renderPage();

    const uploadedVideo = await screen.findByLabelText('上传片段 视频');
    const generatedVideo = screen.getByLabelText('生成片段 视频');
    expect(uploadedVideo).toHaveAttribute('src', '/api/creator/projects/p1/assets/a-video/content?versionId=av-video');
    expect(generatedVideo).toHaveAttribute('src', '/api/creator/media/artifacts/artifact-video');

    fireEvent.error(uploadedVideo);
    expect(screen.getByText('预览不可用')).toBeInTheDocument();
    expect(screen.queryByLabelText('上传片段 视频')).not.toBeInTheDocument();
  });

  it('detaches only the exact immutable source ref through the origin delete interaction', async () => {
    const attached = {
      ...assetView,
      attachedSources: [{ assetId: 'a1', assetVersionId: 'av1', sourceRef: 'asset://a1@av1', name: '素材一', sourceLabel: '用户上传', mediaType: 'video', referenceCount: 0, targetVersion: 'ov-a1', uiLocator: { page: 'assets', assetId: 'a1', versionId: 'av1' } }],
      availableAssets: [{ ...assetView.availableAssets[0], attached: true, presentationStatus: 'accepted' as const }],
      presentationAssets: [{ ...assetView.presentationAssets[0], presentationStatus: 'accepted' as const, uiLocator: { page: 'assets', assetId: 'a1', versionId: 'av1' } }],
    };
    const { calls } = installMockFetch([
      { match: '/projects/p1/commands', response: { json: { commandId: 'c1', status: 'APPLIED', eventSeq: 1 } } },
      { match: '/projects/p1/assets', response: { json: envelope(attached) } },
    ]);
    const confirm = vi.spyOn(Modal, 'confirm').mockImplementation((config) => {
      void config.onOk?.();
      return { destroy: vi.fn(), update: vi.fn() };
    });
    renderPage();
    await waitFor(() => expect(screen.getByText('素材一')).toBeInTheDocument());
    fireEvent.click(screen.getByText('素材一'));
    fireEvent.click(screen.getByRole('button', { name: '删除资产' }));
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ title: '删除「素材一」？', okText: '删除' }));
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    const command = calls.find((call) => call.method === 'POST')!;
    expect(command.body).toMatchObject({ type: 'DETACH_SOURCE_ASSETS', targetRef: 'project:assets', arguments: { assetVersionRefs: ['asset://a1@av1'] } });
  });

  it('honors the exact immutable version locator for the selected logical Asset', async () => {
    const view = {
      ...assetView,
      availableAssets: [
        assetView.availableAssets[0],
        { ...assetView.availableAssets[0], assetVersionId: 'av2', sourceRef: 'asset://a1@av2', objectVersion: 'ov-a2', checksum: 'sha2', createdAt: 'later', uiLocator: { page: 'assets', assetId: 'a1', versionId: 'av2' } },
      ],
      presentationAssets: [{ ...assetView.presentationAssets[0], sourceRef: 'asset://a1@av2', targetVersion: 'ov-a2', uiLocator: { page: 'assets', assetId: 'a1', versionId: 'av2' } }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(view) } }]);
    renderPage('/project/p1/assets?asset=a1&version=av2&review=1&reviewPulse=2');
    await waitFor(() => expect(document.querySelector('[data-asset-version="av2"]')).toBeInTheDocument());
    expect(document.querySelector('[data-asset-version="av2"]')).toHaveClass('border-[var(--color-accent)]');
    expect(document.querySelector('[data-asset-version="av1"]')).not.toBeInTheDocument();
  });

  it('replays the asset-card review flash when View targets the same deep link again', async () => {
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(assetView) } }]);
    renderPage('/project/p1/assets?asset=a1&version=av1');
    await waitFor(() => expect(document.querySelector('[data-asset-id="a1"]')).toBeInTheDocument());
    const card = document.querySelector<HTMLElement>('[data-asset-id="a1"]')!;

    vi.useFakeTimers();
    try {
      act(() => {
        useNavigationStore.getState().setReviewFocus({
          path: '/project/p1/assets',
          ref: 'a1',
          query: { asset: 'a1', version: 'av1', review: '1', reviewPulse: 'first' },
        });
      });
      act(() => {
        vi.advanceTimersByTime(250);
      });
      expect(card).toHaveClass('review-flash');

      act(() => {
        vi.advanceTimersByTime(2_600);
      });
      expect(card).not.toHaveClass('review-flash');

      act(() => {
        useNavigationStore.getState().setReviewFocus({
          path: '/project/p1/assets',
          ref: 'a1',
          query: { asset: 'a1', version: 'av1', review: '1', reviewPulse: 'second' },
        });
      });
      act(() => {
        vi.advanceTimersByTime(250);
      });
      expect(card).toHaveClass('review-flash');
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses the origin supplement dialog while durably attaching each uploaded immutable version', async () => {
    const { calls } = installMockFetch([
      { match: '/projects/p1/assets', response: { json: envelope(assetView) } },
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText('补充资料')).toBeInTheDocument());
    fireEvent.click(screen.getByText('补充资料'));
    await waitFor(() => expect(document.querySelector('.ant-modal')).toHaveStyle({ width: '480px' }));
    const input = document.querySelector<HTMLInputElement>('.ant-modal input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [new File(['source'], 'source.txt', { type: 'text/plain' })] } });
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true));
    const uploaded = calls.find((call) => call.method === 'POST')!;
    expect(uploaded.body).toMatchObject({ postIngestAction: 'ATTACH_SOURCE' });
  });

  it('keeps the supplement close behavior but reports a remote 202 as processing', async () => {
    const info = vi.spyOn(message, 'info').mockImplementation(() => ({}) as ReturnType<typeof message.info>);
    const success = vi.spyOn(message, 'success').mockImplementation(() => ({}) as ReturnType<typeof message.success>);
    installMockFetch([
      {
        match: '/projects/p1/assets',
        method: 'POST',
        response: { json: { assetId: 'a-url', taskId: 'task-url', status: 'RUNNING', progress: 0, assetVersionId: null } },
      },
      { match: '/projects/p1/assets', method: 'GET', response: { json: envelope(assetView) } },
    ]);
    renderPage();
    fireEvent.click(await screen.findByText('补充资料'));
    fireEvent.click(screen.getByRole('tab', { name: '链接' }));
    fireEvent.change(screen.getByPlaceholderText('https://…'), { target: { value: 'https://cdn.example.com/large.mp4' } });
    fireEvent.click(screen.getByRole('button', { name: /入\s*库/ }));

    await waitFor(() => expect(info).toHaveBeenCalledWith('链接已接收，正在入库'));
    expect(success).not.toHaveBeenCalledWith('链接已入库');
    await waitFor(() => expect(document.querySelector('.ant-modal')).toHaveClass('ant-zoom-leave'));
  });

  it('reuses the ingest banner for the latest durable structured failure', async () => {
    useCreatorTaskViewStore.setState({
      projectId: 'p1',
      tasks: [{
        id: 'task-failed', projectId: 'p1', transactionId: null, specialistRunId: null,
        kind: 'asset_ingest', targetRef: 'asset:a-url', status: 'FAILED', progress: 0.37,
        resultRefs: [], result: null,
        error: { kind: 'ASSET_INGEST_FAILED', items: [{ name: 'large.mp4', error: '远程素材下载连接超时' }] },
        updatedAt: '2026-07-11T12:00:00Z',
      }],
    });
    const failedView: AssetLibraryView = {
      ...assetView,
      ingestItems: [{
        taskId: 'task-failed', assetId: 'a-url', assetVersionId: null, name: 'large.mp4',
        status: 'FAILED', progress: 0.37, error: 'ASSET_INGEST_FAILED',
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(failedView) } }]);
    renderPage();
    expect(await screen.findByText('入库失败「large.mp4」 · 远程素材下载连接超时')).toBeInTheDocument();
  });

  it('keeps active ingest progress in the local asset status bar', async () => {
    const runningView: AssetLibraryView = {
      ...assetView,
      ingestItems: [{
        taskId: 'task-running', assetId: 'a-url', assetVersionId: null, name: 'large.mp4',
        status: 'RUNNING', progress: 0.42, error: null,
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(runningView) } }]);
    renderPage();

    expect(await screen.findByText('正在入库「large.mp4」 · 42%')).toBeInTheDocument();
  });

  it('reports optional cache failure without presenting the public asset as unusable', async () => {
    const cacheFailedView: AssetLibraryView = {
      ...assetView,
      ingestItems: [{
        taskId: 'task-cache-failed', assetId: 'a-url', assetVersionId: 'av-url', name: 'large.mp4',
        status: 'CACHE_FAILED', progress: 1, error: '远程缓存连接超时',
      }],
    };
    installMockFetch([{ match: '/projects/p1/assets', response: { json: envelope(cacheFailedView) } }]);
    renderPage();
    expect(await screen.findByText('本地缓存失败，公网素材仍可用于模型 · 「large.mp4」：远程缓存连接超时')).toBeInTheDocument();
    expect(screen.queryByText(/入库失败「large\.mp4」/)).not.toBeInTheDocument();
  });
});
