import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Empty, message, Modal, Select, Slider } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined, CloseOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ArtifactVersionView, ComposeSelectionView, ComposeView, ViewEnvelope } from '@/contracts/creator';
import { presentationOf, useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { buildCreatorCommand, commandStatusCopy, useCreatorCommand } from '@/hooks/useCreatorCommand';
import { getArtifactVersionMediaUrl, getFinalComposeView, submitCreatorCommand } from '@/api/creator';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import { reviewGroupForArtifactVersion } from '@/lib/artifactReview';

interface ComposeCandidate {
  id: string;
  sourceType: 'section' | 'unit';
  sourceId: string;
  sectionId: string;
  sourceRef: string;
  artifactRef: string;
  artifactVersionId: string;
  label: string;
  url: string;
  duration?: number;
  artifact: ArtifactVersionView;
}

function identifierOf(ref: string): string {
  return ref.split('/').at(-1) || ref.split(':').at(-1) || ref;
}

export default function FinalComposePanel({ projectId, visible, onClose, focusVersion, focusPulse }: {
  projectId: string;
  visible: boolean;
  onClose: () => void;
  focusVersion?: string | null;
  focusPulse?: string | null;
}) {
  const envelope = useWorkspaceViewStore((state) => state.finalCompose);
  const planEnvelope = useWorkspaceViewStore((state) => state.plan);
  const load = useWorkspaceViewStore((state) => state.loadFinalCompose);
  const view = presentationOf(envelope);
  const plan = presentationOf(planEnvelope);
  const events = useCreatorSessionStore((state) => state.events);
  const lastViewSeq = [...events].reverse().find((event) => event.type === 'workspace.head_changed' || ['task.completed', 'task.failed', 'task.quarantined', 'subagent.completed'].includes(event.type))?.seq;
  const reload = useCallback(() => load(projectId), [load, projectId]);
  const { submit, submitting } = useCreatorCommand(projectId, envelope, reload);
  const [selection, setSelection] = useState<ComposeSelectionView[]>([]);
  const [transitionDuration, setTransitionDuration] = useState(0.6);
  const [xfadeType, setXfadeType] = useState('fade');
  const [composing, setComposing] = useState(false);
  const lastFocusKey = useRef<string | null>(null);
  const initializedSelectionKey = useRef<string | null>(null);

  useEffect(() => {
    if (visible) void load(projectId).catch(() => undefined);
  }, [lastViewSeq, load, projectId, visible]);
  useEffect(() => {
    if (!focusVersion || !visible) return;
    const key = `${focusVersion}:${focusPulse || 'direct'}`;
    if (key === lastFocusKey.current) return;
    const target = document.querySelector<HTMLElement>(`[data-artifact-version="${CSS.escape(focusVersion)}"]`);
    if (!target) return;
    lastFocusKey.current = key;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.remove('review-flash');
    void target.offsetWidth;
    target.classList.add('review-flash');
  }, [focusPulse, focusVersion, view, visible]);

  const candidates = useMemo<ComposeCandidate[]>(() => (view?.candidates || []).map((artifact) => {
    const sourceId = identifierOf(artifact.ownerRef);
    const sourceType = artifact.sourceKind || (artifact.ownerRef.includes('://unit/') ? 'unit' : 'section');
    const sectionId = artifact.sectionId || (sourceType === 'section' ? sourceId : '');
    const section = view?.sections?.find((item) => item.id === sourceId);
    const unit = plan?.sections.flatMap((item) => item.units).find((item) => item.id === sourceId);
    const resolved = view?.resolvedRefs.find((item) => identifierOf(item.ref) === sourceId);
    return {
      id: artifact.artifactVersionId,
      sourceType,
      sourceId,
      sectionId,
      sourceRef: artifact.ownerRef,
      artifactRef: artifact.sourceRef,
      artifactVersionId: artifact.artifactVersionId,
      label: sourceType === 'section'
        ? `${section?.title || resolved?.name || artifact.name || `Section ${sourceId}`}（整段成片）`
        : unit?.title
          ? `${String(unit.number).padStart(2, '0')} ${unit.title}`
          : artifact.name || `生成单元 ${sourceId}`,
      url: getArtifactVersionMediaUrl(artifact.artifactVersionId),
      duration: artifact.durationSeconds,
      artifact,
    };
  }), [plan, view]);

  useEffect(() => {
    if (!visible || !view) return;
    const key = `${view.targetVersion}:${envelope?.reviewRevisionId || envelope?.approvedRevisionId || ''}`;
    if (initializedSelectionKey.current === key) return;
    initializedSelectionKey.current = key;
    if (view.selections.length > 0) {
      setSelection([...view.selections].sort((left, right) => left.order - right.order));
      return;
    }
    const sectionCandidates = candidates.filter((candidate) => candidate.sourceType === 'section');
    const fallback = sectionCandidates.length > 0 ? sectionCandidates : candidates;
    setSelection(fallback.map((candidate, order) => ({
      sourceRef: candidate.sourceRef,
      sourceKind: candidate.sourceType,
      artifactRef: candidate.artifactRef,
      artifactVersionId: candidate.artifactVersionId,
      slotId: candidate.artifact.slotId,
      order,
      uiLocator: candidate.artifact.uiLocator,
    })));
  }, [candidates, envelope?.approvedRevisionId, envelope?.reviewRevisionId, view, visible]);
  const candidateById = useMemo(() => new Map(candidates.map((candidate) => [candidate.artifactVersionId, candidate])), [candidates]);
  const groupedCandidates = useMemo(() => {
    if (view?.sections?.length) return view.sections.map((section) => ({
      id: section.id,
      number: section.number,
      title: section.title,
      items: candidates.filter((candidate) => candidate.sectionId === section.id),
    }));
    return candidates.map((candidate, index) => ({
      id: candidate.sourceId,
      number: index + 1,
      title: candidate.label,
      items: [candidate],
    }));
  }, [candidates, view?.sections]);
  const totalDuration = selection.reduce((sum, item) => sum + (candidateById.get(item.artifactVersionId)?.duration || 0), 0);
  const rendered = view?.resolvedRefs.find((item) => item.ref === view.renderedVideoRef);
  const manifest = useReviewManifestStore((state) => state.manifest);
  const renderedReviewGroup = reviewGroupForArtifactVersion(
    manifest,
    rendered?.artifactVersionId,
    rendered?.ref,
  );
  const selectedCandidatesValid = selection.every((item) => candidateById.has(item.artifactVersionId));
  const nonSelectionBlockers = view?.blockers.filter((blocker) => !blocker.startsWith('FINAL_COMPOSE_SOURCE_MISSING:')) ?? [];
  const canCompose = Boolean(selection.length > 0 && selectedCandidatesValid && nonSelectionBlockers.length === 0 && !submitting && !composing);

  const persistSelection = (next: ComposeSelectionView[]) => submit('SET_FINAL_COMPOSE_SELECTION', 'post:final', {
    selections: next.map((item, order) => ({
      sourceRef: item.sourceRef,
      artifactRef: item.artifactRef,
      artifactVersionId: item.artifactVersionId,
      order,
    })),
  }, view?.targetVersion);
  const toggleCandidate = (candidate: ComposeCandidate) => {
    const exists = selection.some((item) => item.artifactVersionId === candidate.artifactVersionId);
    const next = exists
      ? selection.filter((item) => item.artifactVersionId !== candidate.artifactVersionId)
      : [
          ...selection.filter((item) => item.sourceRef !== candidate.sourceRef),
          {
            sourceRef: candidate.sourceRef,
            sourceKind: candidate.sourceType,
            artifactRef: candidate.artifactRef,
            artifactVersionId: candidate.artifactVersionId,
            slotId: candidate.artifact.slotId,
            order: selection.length,
            uiLocator: candidate.artifact.uiLocator,
          },
        ];
    setSelection(next);
    void persistSelection(next);
  };
  const moveSelected = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= selection.length) return;
    const next = [...selection];
    [next[index], next[target]] = [next[target], next[index]];
    setSelection(next);
    void persistSelection(next);
  };
  const removeSelected = (index: number) => {
    const next = selection.filter((_, itemIndex) => itemIndex !== index);
    setSelection(next);
    void persistSelection(next);
  };
  const handleCompose = async () => {
    if (!envelope || !view || !canCompose) return;
    setComposing(true);
    try {
      let currentEnvelope: ViewEnvelope<ComposeView> = envelope;
      let currentView = view;
      const persistedSignature = currentView.selections
        .map((item) => `${item.sourceRef}:${item.artifactVersionId}`)
        .join('|');
      const selectionSignature = selection
        .map((item) => `${item.sourceRef}:${item.artifactVersionId}`)
        .join('|');
      if (persistedSignature !== selectionSignature) {
        await submitCreatorCommand(
          projectId,
          buildCreatorCommand(
            currentEnvelope,
            'SET_FINAL_COMPOSE_SELECTION',
            'post:final',
            {
              selections: selection.map((item, order) => ({
                sourceRef: item.sourceRef,
                artifactRef: item.artifactRef,
                artifactVersionId: item.artifactVersionId,
                slotId: item.slotId,
                order,
              })),
            },
            currentView.targetVersion,
          ),
        );
        currentEnvelope = await getFinalComposeView(projectId);
        currentView = presentationOf(currentEnvelope);
      }
      for (let index = 0; index < selection.length - 1; index += 1) {
        const command = buildCreatorCommand(
          currentEnvelope,
          'SET_FINAL_COMPOSE_TRANSITION',
          'post:final',
          {
            fromSourceRef: selection[index].sourceRef,
            toSourceRef: selection[index + 1].sourceRef,
            type: xfadeType,
            durationSeconds: transitionDuration,
          },
          currentView.targetVersion,
        );
        await submitCreatorCommand(projectId, command);
        currentEnvelope = await getFinalComposeView(projectId);
        currentView = presentationOf(currentEnvelope);
      }
      const result = await submitCreatorCommand(
        projectId,
        buildCreatorCommand(currentEnvelope, 'COMPOSE_FINAL_VIDEO', 'post:final', {}, currentView.targetVersion),
      );
      message.success(commandStatusCopy(result, currentEnvelope.uiPhase));
      await reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setComposing(false);
    }
  };
  const decideRendered = async (decision: 'ACCEPT' | 'REJECT') => {
    const current = useReviewManifestStore.getState().manifest?.decisionGroups.find(
      (group) => group.id === renderedReviewGroup?.id && group.decision === 'PENDING',
    );
    if (!current) return;
    await useReviewManifestStore.getState().decide(current.id, {
      decisionToken: current.decisionToken,
      decision,
    });
    message.success(decision === 'ACCEPT' ? '已接受最终成片' : '已撤销最终成片');
    await reload();
  };

  return (
    <Modal
      title="最终剪辑视频合成"
      open={visible}
      onCancel={() => !submitting && !composing && onClose()}
      width={960}
      maskClosable={!submitting && !composing}
      footer={(
        <div className="flex items-center justify-between">
          <span className="text-xs text-[var(--color-text-tertiary)]">已选 {selection.length} 段{totalDuration > 0 ? ` · 预计 ${totalDuration}s` : ''}</span>
          <div className="flex gap-2">
            <Button onClick={onClose} disabled={submitting || composing}>关闭</Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={composing}
              disabled={!canCompose}
              onClick={() => void handleCompose()}
            >
              {composing ? '合成中...' : '执行合成'}
            </Button>
          </div>
        </div>
      )}
    >
      {rendered?.artifactVersionId && (
        <div className="mb-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <div className="mb-2 text-sm font-semibold text-[var(--color-text-secondary)]">当前最终成片</div>
          <video
            data-artifact-version={rendered.artifactVersionId}
            src={getArtifactVersionMediaUrl(rendered.artifactVersionId)}
            controls
            className="w-full rounded-lg"
            style={{ maxHeight: '320px' }}
          >
            您的浏览器不支持视频播放
          </video>
          <div className="mt-2 text-xs text-[var(--color-text-tertiary)]">输出路径：{view?.renderedVideoUrl || view?.renderedVideoRef}</div>
          {renderedReviewGroup?.decision === 'PENDING' && (
            <div className="mt-2 flex items-center justify-between rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] px-2.5 py-1.5">
              <span className="text-[11px] text-[var(--color-warning)]">该最终成片待审阅</span>
              <div className="flex items-center gap-1">
                <Button size="small" type="primary" onClick={() => void decideRendered('ACCEPT')} className="!text-[11px]">接受</Button>
                <Button size="small" onClick={() => void decideRendered('REJECT')} className="!text-[11px]">撤销</Button>
              </div>
            </div>
          )}
        </div>
      )}

      {candidates.length === 0 ? (
        <Empty description="暂无可用成片：请先生成并接受 Unit 视频，或先完成 Section 拼接" />
      ) : (
        <div className="grid grid-cols-2 gap-4" style={{ minHeight: '360px' }}>
          <div className="min-h-0 overflow-y-auto rounded-lg border border-[var(--color-border)] p-3">
            <div className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">可选成片（按结构段分组）</div>
            <div className="space-y-3">
              {groupedCandidates.map((group) => (
                <div key={group.id}>
                  <div className="mb-1 text-xs font-bold text-[var(--color-text-primary)]">{group.number}. {group.title}</div>
                  {group.items.length === 0 ? (
                    <div className="pl-6 text-[11px] text-[var(--color-text-tertiary)]">本段无已接受成片</div>
                  ) : (
                    <div className="space-y-1">
                      {group.items.map((candidate) => (
                        <CandidateRow
                          key={candidate.id}
                          candidate={candidate}
                          checked={selection.some((item) => item.artifactVersionId === candidate.artifactVersionId)}
                          onToggle={() => toggleCandidate(candidate)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto rounded-lg border border-[var(--color-border)] p-3">
            <div className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">合成顺序（从上到下）</div>
            {selection.length === 0 ? (
              <Empty description="从左侧勾选成片" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div className="space-y-1">
                {selection.map((item, index) => {
                  const candidate = candidateById.get(item.artifactVersionId);
                  return (
                    <SelectedRow
                      key={`${item.sourceRef}:${item.artifactVersionId}`}
                      index={index}
                      total={selection.length}
                      label={candidate?.label || item.sourceRef}
                      duration={candidate?.duration}
                      missing={!candidate}
                      artifactVersionId={item.artifactVersionId}
                      onMoveUp={() => moveSelected(index, -1)}
                      onMoveDown={() => moveSelected(index, 1)}
                      onRemove={() => removeSelected(index)}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mt-4 flex items-center gap-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
        <div className="text-xs font-semibold text-[var(--color-text-secondary)]">拼接点平滑</div>
        <div className="flex min-w-[200px] flex-1 items-center gap-3">
          <span className="shrink-0 text-xs text-[var(--color-text-tertiary)]">转场时长</span>
          <Slider
            min={0}
            max={2}
            step={0.1}
            value={transitionDuration}
            onChange={setTransitionDuration}
            className="min-w-[140px] flex-1"
            tooltip={{ formatter: (value) => value === 0 ? '硬切' : `${value?.toFixed(1)}s` }}
          />
          <span className="w-12 shrink-0 text-right text-xs font-medium text-[var(--color-text-primary)]">{transitionDuration === 0 ? '硬切' : `${transitionDuration.toFixed(1)}s`}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="shrink-0 text-xs text-[var(--color-text-tertiary)]">转场类型</span>
          <Select
            size="small"
            value={xfadeType}
            onChange={setXfadeType}
            style={{ width: 130 }}
            options={[
              { value: 'fade', label: '交叉淡化' },
              { value: 'fadeblack', label: '黑场过渡' },
              { value: 'fadewhite', label: '白场过渡' },
              { value: 'dissolve', label: '溶解' },
              { value: 'wipeleft', label: '左擦除' },
            ]}
          />
        </div>
      </div>

      {(view?.blockers.length || 0) > 0 && (
        <Alert
          type="warning"
          showIcon
          className="mt-3"
          message="存在阻断项"
          description={<ul className="mt-1 list-inside list-disc space-y-1 text-xs">{view?.blockers.map((blocker, index) => <li key={index}>{blocker}</li>)}</ul>}
        />
      )}
    </Modal>
  );
}

function CandidateRow({ candidate, checked, onToggle }: { candidate: ComposeCandidate; checked: boolean; onToggle: () => void }) {
  return (
    <label
      data-artifact-version={candidate.artifactVersionId}
      className={`flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 transition-colors ${checked ? 'border-[var(--color-primary)] bg-[var(--color-bg-secondary)]' : 'border-transparent hover:bg-[var(--color-bg-secondary)]'}`}
    >
      <Checkbox checked={checked} onChange={onToggle} />
      <div className="h-10 w-16 shrink-0 overflow-hidden rounded bg-[var(--color-bg-secondary)]">
        <video src={candidate.url} className="h-full w-full object-cover" preload="metadata" muted />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-[var(--color-text-primary)]">{candidate.label}</div>
        <div className="text-[11px] text-[var(--color-text-tertiary)]">{candidate.sourceType === 'section' ? '整段成片' : '单元成片'}{candidate.duration ? ` · ${candidate.duration}s` : ''}</div>
      </div>
    </label>
  );
}

function SelectedRow({ index, total, label, duration, missing, artifactVersionId, onMoveUp, onMoveDown, onRemove }: {
  index: number;
  total: number;
  label: string;
  duration?: number;
  missing: boolean;
  artifactVersionId: string;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}) {
  return (
    <div
      data-artifact-version={artifactVersionId}
      className={`flex items-center gap-2 rounded-md border px-2 py-1.5 ${missing ? 'border-[var(--color-danger)]/40 bg-[var(--color-danger-soft)]' : 'border-[var(--color-border)] bg-[var(--color-bg-card)]'}`}
    >
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-xs font-semibold text-white">{index + 1}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-[var(--color-text-primary)]">{missing ? `${label}（已失效）` : label}</div>
        {duration ? <div className="text-[11px] text-[var(--color-text-tertiary)]">{duration}s</div> : null}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <Button size="small" type="text" disabled={index === 0} onClick={onMoveUp} title="上移"><ArrowUpOutlined /></Button>
        <Button size="small" type="text" disabled={index === total - 1} onClick={onMoveDown} title="下移"><ArrowDownOutlined /></Button>
        <Button size="small" type="text" danger onClick={onRemove} title="移除"><CloseOutlined /></Button>
      </div>
    </div>
  );
}
