import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Empty, message } from 'antd';
import { ArrowLeftOutlined, PlayCircleOutlined, VideoCameraOutlined } from '@ant-design/icons';
import type { ComposeSelectionView, ComposeView, ViewEnvelope } from '@/contracts/creator';
import { useCreatorCommand } from '@/hooks/useCreatorCommand';
import { getArtifactVersionMediaUrl } from '@/api/creator';
import { navigate } from '@/routing/navigation';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import { reviewGroupForArtifactVersion } from '@/lib/artifactReview';
import { projectJsonPointer } from '@/lib/projectJsonPointer';

interface ClipView {
  unitId: string;
  unitName: string;
  artifactVersionId: string;
  artifactRef: string;
  ownerRef: string;
  url: string;
  duration?: number;
}

function identifierOf(ref: string): string {
  return ref.split('/').at(-1) || ref.split(':').at(-1) || ref;
}

function resolvedName(view: ComposeView, ref: string): string {
  const identifier = identifierOf(ref);
  return view.resolvedRefs.find((item) => item.ref === ref || identifierOf(item.ref) === identifier)?.name || ref;
}

function clipsOf(view: ComposeView, selections: ComposeSelectionView[]): ClipView[] {
  return selections.map((selection) => {
    const candidate = view.candidates.find((item) => item.artifactVersionId === selection.artifactVersionId);
    const ownerRef = candidate?.ownerRef || selection.sourceRef;
    return {
      unitId: identifierOf(ownerRef),
      unitName: candidate?.name || resolvedName(view, ownerRef),
      artifactVersionId: selection.artifactVersionId,
      artifactRef: selection.artifactRef,
      ownerRef,
      url: getArtifactVersionMediaUrl(selection.artifactVersionId),
      duration: candidate?.durationSeconds,
    };
  });
}

export default function ComposeWorkspace({ projectId, envelope, view, reload, onClose, focusVersion, focusPulse }: {
  projectId: string;
  envelope: ViewEnvelope<ComposeView>;
  view: ComposeView;
  reload: () => Promise<void>;
  onClose?: () => void;
  focusVersion?: string | null;
  focusPulse?: string | null;
}) {
  const sectionId = view.sectionId || '';
  const targetRef = `post:${sectionId}`;
  const { submit, submitting } = useCreatorCommand(projectId, envelope, reload);
  const selections = useMemo(() => [...view.selections].sort((left, right) => left.order - right.order), [view.selections]);
  const clips = useMemo(() => clipsOf(view, selections), [selections, view]);
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const lastFocusKey = useRef<string | null>(null);
  const sectionName = view.sectionTitle || resolvedName(view, `section:${sectionId}`);
  const selectedClip = clips.find((clip) => clip.unitId === selectedUnitId) || null;
  const rendered = view.resolvedRefs.find((item) => item.ref === view.renderedVideoRef);
  const renderedVersionId = rendered?.artifactVersionId;
  const manifest = useReviewManifestStore((state) => state.manifest);
  const renderedReviewGroup = reviewGroupForArtifactVersion(
    manifest,
    renderedVersionId,
    rendered?.ref,
  );

  const decideRendered = async (decision: 'ACCEPT' | 'REJECT') => {
    const current = useReviewManifestStore.getState().manifest?.decisionGroups.find(
      (group) => group.id === renderedReviewGroup?.id && group.decision === 'PENDING',
    );
    if (!current) return;
    await useReviewManifestStore.getState().decide(current.id, {
      decisionToken: current.decisionToken,
      decision,
    });
    message.success(decision === 'ACCEPT' ? '已接受该拼接成片' : '已撤销该拼接成片');
    await reload();
  };

  useEffect(() => setSelectedUnitId(null), [sectionId]);
  useEffect(() => {
    if (!focusVersion) return;
    const key = `${focusVersion}:${focusPulse || 'direct'}`;
    if (key === lastFocusKey.current) return;
    const target = document.querySelector<HTMLElement>(`[data-artifact-version="${CSS.escape(focusVersion)}"]`);
    if (!target) return;
    lastFocusKey.current = key;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.remove('review-flash');
    void target.offsetWidth;
    target.classList.add('review-flash');
  }, [focusPulse, focusVersion, view]);

  const applySelections = (next: ComposeSelectionView[]) => submit('SET_SECTION_COMPOSE_SELECTION', targetRef, {
    selections: next.map((item, order) => ({
      sourceRef: item.sourceRef,
      artifactVersionId: item.artifactVersionId,
      artifactRef: item.artifactRef,
      order,
    })),
  }, view.targetVersion);
  const moveClip = (unitId: string, direction: -1 | 1) => {
    const index = clips.findIndex((clip) => clip.unitId === unitId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= selections.length) return;
    const next = [...selections];
    [next[index], next[target]] = [next[target], next[index]];
    void applySelections(next);
  };

  return (
    <div
      data-creator-field={targetRef}
      data-creator-path={projectJsonPointer('post_production', 'sections_by_id', sectionId)}
      data-creator-field-label="合成工作区"
      className="flex h-full flex-col"
    >
      <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-6 py-4">
        <div className="mb-2 flex items-center gap-2">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => onClose ? onClose() : navigate(`/project/${projectId}/plan?section=${sectionId}`)}
          >
            返回
          </Button>
          <span className="text-xs text-[var(--color-text-tertiary)]">plan / {sectionName}</span>
        </div>
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
          <VideoCameraOutlined className="mr-2" />
          拼接与预览：{sectionName}
        </h1>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">将本段所有已接受的视频单元拼接为完整成片</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {view.blockers.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message="拼接前置条件未满足"
            description={(
              <ul className="mt-2 list-inside list-disc space-y-1">
                {view.blockers.map((blocker, index) => <li key={index}>{blocker}</li>)}
              </ul>
            )}
            className="mb-4"
          />
        )}

        <div className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)]">单元视频清单（{clips.length} 个）</h2>
          {clips.length === 0 ? (
            <Empty description="暂无可拼接的视频单元" />
          ) : (
            <div className="space-y-2">
              {clips.map((clip, index) => (
                <ClipCard
                  key={clip.unitId}
                  clip={clip}
                  order={index + 1}
                  projectId={projectId}
                  selected={clip.unitId === selectedUnitId}
                  isFirst={index === 0}
                  isLast={index === clips.length - 1}
                  onMoveUp={() => moveClip(clip.unitId, -1)}
                  onMoveDown={() => moveClip(clip.unitId, 1)}
                  onSelect={() => setSelectedUnitId((previous) => previous === clip.unitId ? null : clip.unitId)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="mb-6 flex items-center gap-4">
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            loading={submitting}
            disabled={!view.readiness.ready}
            onClick={() => void submit('STITCH_SECTION', targetRef, {}, view.targetVersion)}
          >
            {submitting ? '拼接中...' : '执行拼接'}
          </Button>
          {!view.readiness.ready && <span className="text-sm text-[var(--color-text-tertiary)]">请先处理上方阻断项</span>}
        </div>

        {selectedClip ? (
          <div>
            <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)]">单元预览：{selectedClip.unitName}</h2>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
              <video
                data-artifact-version={selectedClip.artifactVersionId}
                src={selectedClip.url}
                controls
                autoPlay
                className="w-full rounded-lg"
                style={{ maxHeight: '500px' }}
              >
                您的浏览器不支持视频播放
              </video>
            </div>
          </div>
        ) : renderedVersionId ? (
          <div>
            <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)]">拼接成片预览</h2>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
              <video
                data-artifact-version={renderedVersionId}
                src={getArtifactVersionMediaUrl(renderedVersionId)}
                controls
                className="w-full rounded-lg"
                style={{ maxHeight: '500px' }}
              >
                您的浏览器不支持视频播放
              </video>
              <div className="mt-2 text-xs text-[var(--color-text-tertiary)]">输出路径：{view.renderedVideoUrl || view.renderedVideoRef}</div>
              {renderedReviewGroup?.decision === 'PENDING' && (
                <div className="mt-2 flex items-center justify-between rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] px-2.5 py-1.5">
                  <span className="text-[11px] text-[var(--color-warning)]">该拼接成片待审阅</span>
                  <div className="flex items-center gap-1">
                    <Button size="small" type="primary" onClick={() => void decideRendered('ACCEPT')} className="!text-[11px]">接受</Button>
                    <Button size="small" onClick={() => void decideRendered('REJECT')} className="!text-[11px]">撤销</Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ClipCard({
  clip,
  order,
  projectId,
  selected,
  isFirst,
  isLast,
  onSelect,
  onMoveUp,
  onMoveDown,
}: {
  clip: ClipView;
  order: number;
  projectId: string;
  selected: boolean;
  isFirst: boolean;
  isLast: boolean;
  onSelect: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  return (
    <div
      data-artifact-version={clip.artifactVersionId}
      onClick={onSelect}
      className={`flex cursor-pointer items-center gap-4 rounded-lg border p-3 transition-colors ${selected ? 'border-[var(--color-primary)] bg-[var(--color-bg-secondary)]' : 'border-[var(--color-border)] bg-[var(--color-bg-card)] hover:border-[var(--color-primary)]'}`}
    >
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${selected ? 'bg-[var(--color-primary)] text-white' : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'}`}>{order}</div>
      <div className="h-16 w-24 shrink-0 overflow-hidden rounded-lg bg-[var(--color-bg-secondary)]">
        <video src={clip.url} className="h-full w-full object-cover" preload="metadata" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-[var(--color-text-primary)]">{clip.unitName}</div>
        <div className="mt-0.5 text-xs text-[var(--color-text-tertiary)]">{clip.duration ? `${clip.duration}s` : '时长未知'}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1" onClick={(event) => event.stopPropagation()}>
        <Button size="small" type="text" disabled={isFirst} onClick={onMoveUp} title="上移">↑</Button>
        <Button size="small" type="text" disabled={isLast} onClick={onMoveDown} title="下移">↓</Button>
        <Button type="link" size="small" onClick={() => navigate(`/project/${projectId}/plan/unit/${clip.unitId}/workbench`)}>编辑</Button>
      </div>
    </div>
  );
}
