import { useEffect, useMemo, useState } from 'react';
import { Button } from 'antd';
import { ArrowRight, Scissors, Trash2 } from 'lucide-react';
import type { EditWorkbenchView, GenerationUnitView, SectionView, UiPhase } from '@/contracts/creator';
import { navigate } from '@/routing/navigation';
import { getArtifactVersionMediaUrl, getGeneratedMediaUrl } from '@/api/creator';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import ReviewFieldText, { ReviewDiffPreview } from '@/components/agent/ReviewFieldText';
import { projectJsonPointer } from '@/lib/projectJsonPointer';

interface UnitDetailProps {
  projectId: string;
  section: SectionView;
  unit: GenerationUnitView;
  uiPhase?: UiPhase;
  activeUnitId?: string;
  editWorkbench?: EditWorkbenchView | null;
  editWorkbenchLoading?: boolean;
  editWorkbenchError?: string;
  onDelete?: () => void;
}

function unitDisplayName(unit: GenerationUnitView): string {
  const prefix = unit.taskType === 'edit' ? '剪辑单元' : '生成单元';
  return unit.title
    ? `${String(unit.number).padStart(2, '0')} ${unit.title}`
    : `${prefix} ${String(unit.number).padStart(2, '0')}`;
}

function progressLabel(unit: GenerationUnitView, uiPhase?: UiPhase, activeUnitId?: string): string {
  if (activeUnitId === unit.id && ['executing', 'finalizing', 'resuming'].includes(uiPhase || '')) return '生成中';
  if (unit.blockers.length > 0 || unit.readiness.blockers.length > 0) return '有阻塞';
  if (unit.videoUrl || unit.storyboardImageUrl) return uiPhase === 'waiting_review' ? '待审' : '已接受';
  return '未生成';
}

function formatTimecode(value?: number): string {
  if (value == null || !Number.isFinite(value)) return '--:--';
  const minutes = Math.floor(value / 60);
  const seconds = value - minutes * 60;
  const secondText = seconds.toFixed(seconds % 1 === 0 ? 0 : 1);
  return `${String(minutes).padStart(2, '0')}:${secondText.padStart(secondText.includes('.') ? 4 : 2, '0')}`;
}

function EditUnitOverview({
  section,
  unitId,
  workbench,
  loading,
  error,
}: {
  section: SectionView;
  unitId: string;
  workbench?: EditWorkbenchView | null;
  loading?: boolean;
  error?: string;
}) {
  const plan = workbench?.plan;
  const storyboard = plan?.storyboard ?? [];
  const fallbackText = section.narrative?.trim();

  if (loading && !workbench) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
        <h4 className="text-xs font-bold text-[var(--color-text-secondary)]">VLM 关键帧分镜</h4>
        <p className="mt-3 text-xs text-[var(--color-text-tertiary)]">正在加载剪辑方案…</p>
      </section>
    );
  }

  if (!plan) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
        <h4 className="text-xs font-bold text-[var(--color-text-secondary)]">素材理解摘要</h4>
        {fallbackText ? (
          <p
            data-creator-field={`section:${section.id}/narrative`}
            data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'narrative')}
            data-creator-field-label="素材理解摘要"
            className="mt-2 whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-primary)]"
          >
            {fallbackText}
          </p>
        ) : (
          <p className="mt-2 text-xs text-[var(--color-text-tertiary)]">
            {error ? '剪辑方案暂时无法加载，请进入工作台查看。' : '尚未生成 VLM 关键帧分镜。'}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-xs font-bold text-[var(--color-text-secondary)]">VLM 关键帧分镜</h4>
        <span className="shrink-0 rounded-full bg-[var(--color-bg-secondary)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-text-tertiary)]">
          {storyboard.length} 个分镜
        </span>
      </div>

      {plan.summary && (
        <div className="mt-3 rounded-lg bg-[var(--color-bg-secondary)]/70 p-3">
          <p className="text-[10px] font-semibold text-[var(--color-text-tertiary)]">剪辑摘要</p>
          <p
            data-creator-field={`unit:${unitId}/editPlan/summary`}
            data-creator-path={projectJsonPointer('production', 'units_by_id', unitId, 'plan', 'summary')}
            data-creator-field-label="剪辑摘要"
            className="mt-1 whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-primary)]"
          >
            {plan.summary}
          </p>
        </div>
      )}

      {storyboard.length > 0 ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {storyboard.map((panel) => (
            <article key={panel.panel_id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 p-3">
              <div className="flex items-start justify-between gap-2">
                <p
                  data-creator-field={`unit:${unitId}/editPlan/storyboard/panel:${panel.panel_id}/title`}
                  data-creator-path={projectJsonPointer('production', 'units_by_id', unitId, 'plan', 'storyboard', 'items', panel.panel_id, 'title')}
                  data-creator-field-label={`VLM 分镜 ${panel.order} · 标题`}
                  className="text-xs font-semibold text-[var(--color-text-primary)]"
                >
                  #{panel.order} {panel.title || '关键帧'}
                </p>
                <span
                  data-creator-field={`unit:${unitId}/editPlan/storyboard/panel:${panel.panel_id}/sourceTimestampSeconds`}
                  data-creator-path={projectJsonPointer('production', 'units_by_id', unitId, 'plan', 'storyboard', 'items', panel.panel_id, 'source_timestamp_seconds')}
                  data-creator-field-label={`VLM 分镜 ${panel.order} · 源时间点`}
                  className="shrink-0 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                >
                  {formatTimecode(panel.timestamp)}
                </span>
              </div>
              <p
                data-creator-field={`unit:${unitId}/editPlan/storyboard/panel:${panel.panel_id}/description`}
                data-creator-path={projectJsonPointer('production', 'units_by_id', unitId, 'plan', 'storyboard', 'items', panel.panel_id, 'description')}
                data-creator-field-label={`VLM 分镜 ${panel.order} · 描述`}
                className="mt-1 text-[11px] leading-4 text-[var(--color-text-secondary)]"
              >
                {panel.description}
              </p>
              {panel.timeline_start != null && panel.timeline_end != null && (
                <p
                  data-creator-field={`unit:${unitId}/editPlan/timeline/clip:${panel.clip_id ?? panel.panel_id}/sourceRange`}
                  data-creator-path={panel.clip_id ? projectJsonPointer('production', 'units_by_id', unitId, 'plan', 'timeline', 'items', panel.clip_id) : undefined}
                  data-creator-field-label={`VLM 分镜 ${panel.order} · 成片时间段`}
                  className="mt-2 text-[10px] text-[var(--color-text-tertiary)]"
                >
                  成片 {formatTimecode(panel.timeline_start)}–{formatTimecode(panel.timeline_end)}
                </p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs text-[var(--color-text-tertiary)]">该剪辑方案暂未包含分镜明细。</p>
      )}
    </section>
  );
}

/** origin/main Unit detail layout backed by GenerationUnitView. */
export default function UnitDetail({
  projectId,
  section,
  unit,
  uiPhase,
  activeUnitId,
  editWorkbench,
  editWorkbenchLoading,
  editWorkbenchError,
  onDelete,
}: UnitDetailProps) {
  const isEditUnit = unit.taskType === 'edit';
  const [storyboardLoadFailed, setStoryboardLoadFailed] = useState(false);
  // Reset the per-unit image-load state whenever the selected unit changes.
  // Without this, a transient load failure on one unit permanently hides the
  // storyboard image for every subsequently selected unit (direct unit→unit
  // clicks reuse this component instance, so local state would otherwise leak).
  useEffect(() => { setStoryboardLoadFailed(false); }, [unit.id]);
  const manifest = useReviewManifestStore((state) => state.manifest);
  const missingShotOperations = useMemo(() => {
    if (!manifest) return [];
    const existing = new Set(unit.shots.map((shot) => shot.id));
    return manifest.operations.filter((operation) => {
      if (!operation.path?.includes(`--${unit.id}--`) || !operation.path.includes('/shots/')) return false;
      const shotId = operation.targetRef.startsWith('shot:') ? operation.targetRef.slice(5).split('/', 1)[0] : '';
      return operation.kind === 'create' && Boolean(shotId) && !existing.has(shotId);
    });
  }, [manifest, unit.id, unit.shots]);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
        <div className="min-w-0">
          <h3
            data-creator-field={`unit:${unit.id}/title`}
            data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'title')}
            data-creator-field-label="标题"
            className="truncate text-sm font-semibold text-[var(--color-text-primary)]"
          >
            <ReviewFieldText field={`unit:${unit.id}/title`}>{unit.title || unitDisplayName(unit)}</ReviewFieldText>
          </h3>
          <p className="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]">
            所属：{section.title} ·{' '}
            <span
              data-creator-field={`unit:${unit.id}/duration`}
              data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'duration_seconds')}
              data-creator-field-label="时长"
            >
              <ReviewFieldText field={`unit:${unit.id}/duration`}>{unit.duration}</ReviewFieldText>
            </span>s{' '}
            · {isEditUnit ? 'AI 剪辑工作台' : '生成制作台'} · {progressLabel(unit, uiPhase, activeUnitId)}
          </p>
          {unit.sceneRef && (
            <p className="mt-0.5 truncate text-[11px] text-[var(--color-text-tertiary)]">
              场景：
              <span
                data-creator-field={`unit:${unit.id}/sceneRef`}
                data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'scene_ref')}
                data-creator-field-label="场景"
              >
                <ReviewFieldText field={`unit:${unit.id}/sceneRef`}>{unit.sceneRef}</ReviewFieldText>
              </span>
            </p>
          )}
          {!unit.sceneRef && <ReviewDiffPreview field={`unit:${unit.id}/sceneRef`} label="场景" focusTarget />}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="shrink-0 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            {isEditUnit ? 'AI剪辑' : 'R2V生成'}
          </span>
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
              title="删除单元"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {isEditUnit && (
          <EditUnitOverview
            section={section}
            unitId={unit.id}
            workbench={editWorkbench}
            loading={editWorkbenchLoading}
            error={editWorkbenchError}
          />
        )}

        {!isEditUnit && <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <h4 className="mb-2 text-xs font-bold text-[var(--color-text-secondary)]">
            Shot 列表（{unit.shots.length}）
          </h4>
          {unit.shots.length === 0 ? (
            <p className="text-xs text-[var(--color-text-tertiary)]">
              尚无镜头，进入工作台后可编辑。
            </p>
          ) : (
            <div className="space-y-2">
              {unit.shots.map((shot) => (
                <div key={shot.id} className="flex items-start gap-2.5 rounded-lg bg-[var(--color-bg-secondary)]/60 px-2.5 py-2">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-primary)] text-[10px] font-bold text-[var(--color-text-secondary)]">
                    {shot.number}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      data-creator-field={`unit:${unit.id}/shot:${shot.id}/description`}
                      data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'shots', 'items', shot.id, 'description')}
                      data-creator-field-label={`镜头${shot.number} · 描述`}
                      className="text-xs leading-5 text-[var(--color-text-primary)]"
                    >
                      <ReviewFieldText field={`unit:${unit.id}/shot:${shot.id}/description`}>{shot.description}</ReviewFieldText>
                    </p>
                    {shot.cameraDescription ? <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
                      镜头：
                      <span
                        data-creator-field={`unit:${unit.id}/shot:${shot.id}/cameraDescription`}
                        data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'shots', 'items', shot.id, 'camera_description')}
                        data-creator-field-label={`镜头${shot.number} · 运镜`}
                      >
                        <ReviewFieldText field={`unit:${unit.id}/shot:${shot.id}/cameraDescription`}>{shot.cameraDescription}</ReviewFieldText>
                      </span>
                    </p> : <ReviewDiffPreview field={`unit:${unit.id}/shot:${shot.id}/cameraDescription`} label={`镜头${shot.number} · 运镜`} focusTarget />}
                    {shot.dialogue ? <p className="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
                      台词：
                      <span
                        data-creator-field={`unit:${unit.id}/shot:${shot.id}/dialogue`}
                        data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'shots', 'items', shot.id, 'dialogue')}
                        data-creator-field-label={`镜头${shot.number} · 台词`}
                      >
                        <ReviewFieldText field={`unit:${unit.id}/shot:${shot.id}/dialogue`}>{shot.dialogue}</ReviewFieldText>
                      </span>
                    </p> : <ReviewDiffPreview field={`unit:${unit.id}/shot:${shot.id}/dialogue`} label={`镜头${shot.number} · 台词`} focusTarget />}
                  </div>
                  <span
                    data-creator-field={`unit:${unit.id}/shot:${shot.id}/duration`}
                    data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'units', 'items', unit.id, 'shots', 'items', shot.id, 'duration_seconds')}
                    data-creator-field-label={`镜头${shot.number} · 时长`}
                    className="shrink-0 text-[11px] font-medium text-[var(--color-text-tertiary)]"
                  >
                    <ReviewFieldText field={`unit:${unit.id}/shot:${shot.id}/duration`}>{shot.duration}</ReviewFieldText>s
                  </span>
                </div>
              ))}
            </div>
          )}
          {missingShotOperations.length > 0 && (
            <div className="mt-2 rounded-lg border border-dashed border-[var(--color-accent)]/35 bg-[var(--color-accent-soft)]/20 p-2">
              <p className="text-[10px] font-semibold text-[var(--color-text-tertiary)]">待新增镜头</p>
              {missingShotOperations.map((operation) => <ReviewDiffPreview key={operation.id} field={operation.path || operation.targetRef} label="新增镜头" focusTarget />)}
            </div>
          )}
        </section>}

        {unit.storyboardPrompt ? (
          <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
            <h4 className="mb-2 text-xs font-bold text-[var(--color-text-secondary)]">分镜 Prompt</h4>
            <p
              data-creator-field={`unit:${unit.id}/storyboardPrompt`}
              data-creator-path={projectJsonPointer('production', 'units_by_id', unit.id, 'storyboard_prompt')}
              data-creator-field-label="分镜 Prompt"
              className="whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-primary)]"
            >
              <ReviewFieldText field={`unit:${unit.id}/storyboardPrompt`}>{unit.storyboardPrompt}</ReviewFieldText>
            </p>
          </section>
        ) : <ReviewDiffPreview field={`unit:${unit.id}/storyboardPrompt`} label="分镜 Prompt" focusTarget />}

        {unit.storyboardImageUrl && (
          <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
            <h4 className="mb-2 text-xs font-bold text-[var(--color-text-secondary)]">分镜图</h4>
            {storyboardLoadFailed ? (
              <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                分镜图加载失败，可在工作台重新生成
              </div>
            ) : (
              <img
                key={unit.storyboardImageVersionId ?? unit.storyboardImageUrl ?? unit.id}
                src={unit.storyboardImageVersionId
                  ? getArtifactVersionMediaUrl(unit.storyboardImageVersionId)
                  : getGeneratedMediaUrl(unit.storyboardImageUrl)}
                alt="分镜图"
                className="w-full rounded-lg border border-[var(--color-border)]"
                onError={() => setStoryboardLoadFailed(true)}
              />
            )}
          </section>
        )}

        {unit.videoPrompt ? (
          <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
            <h4 className="mb-2 text-xs font-bold text-[var(--color-text-secondary)]">视频 Prompt</h4>
            <p
              data-creator-field={`unit:${unit.id}/videoPrompt`}
              data-creator-path={projectJsonPointer('production', 'units_by_id', unit.id, 'video_prompt')}
              data-creator-field-label="视频 Prompt"
              className="whitespace-pre-wrap text-xs leading-5 text-[var(--color-text-primary)]"
            >
              <ReviewFieldText field={`unit:${unit.id}/videoPrompt`}>{unit.videoPrompt}</ReviewFieldText>
            </p>
          </section>
        ) : <ReviewDiffPreview field={`unit:${unit.id}/videoPrompt`} label="视频 Prompt" focusTarget />}
      </div>

      <div className="border-t border-[var(--color-border)] p-4">
        <Button
          type="primary"
          block
          onClick={() => navigate(`/project/${projectId}/plan/unit/${unit.id}/workbench`)}
          className="!h-9 !font-semibold"
        >
          {isEditUnit ? (
            <span className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none">
              <Scissors className="h-3.5 w-3.5 shrink-0" />
              <span>进入 AI 剪辑工作台</span>
            </span>
          ) : (
            <span className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none">
              <span>进入制作工作台</span>
              <ArrowRight className="h-3.5 w-3.5 shrink-0" />
            </span>
          )}
        </Button>
      </div>
    </div>
  );
}
