import type { GenerationUnitView, SectionView, UiPhase } from '@/contracts/creator';

type Progress = 'idle' | 'generating' | 'pending_review' | 'accepted' | 'stale';

const PROGRESS_TONES: Record<Progress, string> = {
  idle: 'border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-tertiary)]',
  generating: 'border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] text-[var(--color-warning)]',
  pending_review: 'border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  accepted: 'border-[var(--color-success)]/25 bg-[var(--color-success-soft)] text-[var(--color-success)]',
  stale: 'border-[var(--color-danger)]/25 bg-[var(--color-danger-soft)] text-[var(--color-danger)]',
};

const PROGRESS_LABELS: Record<Progress, string> = {
  idle: '未生成',
  generating: '生成中',
  pending_review: '待审',
  accepted: '已接受',
  stale: '需复核',
};

function progressOf(unit: GenerationUnitView, uiPhase?: UiPhase, activeUnitId?: string): Progress {
  if (activeUnitId === unit.id && ['executing', 'finalizing', 'resuming'].includes(uiPhase || '')) return 'generating';
  if (unit.blockers.length > 0 || unit.readiness.blockers.length > 0) return 'stale';
  const hasOutput = Boolean(unit.videoUrl || unit.storyboardImageUrl);
  if (hasOutput && uiPhase === 'waiting_review') return 'pending_review';
  return hasOutput ? 'accepted' : 'idle';
}

function unitDisplayName(unit: GenerationUnitView): string {
  const prefix = unit.taskType === 'edit' ? '剪辑单元' : '生成单元';
  return unit.title
    ? `${String(unit.number).padStart(2, '0')} ${unit.title}`
    : `${prefix} ${String(unit.number).padStart(2, '0')}`;
}

interface PlanCardProps {
  section: SectionView;
  terms?: { section: string; unit: string };
  isSingleUnit: boolean;
  selected: boolean;
  selectedUnitId?: string;
  uiPhase?: UiPhase;
  activeUnitId?: string;
  onSelectSection: (sectionId: string) => void;
  onSelectUnit: (unitId: string) => void;
}

/**
 * The origin/main Plan card, with its data source narrowed to PlanView.
 * No Project aggregate or parallel graph is reconstructed in the browser.
 */
export default function PlanCard({
  section,
  terms = { section: 'Section', unit: '生成单元' },
  isSingleUnit,
  selected,
  selectedUnitId,
  uiPhase,
  activeUnitId,
  onSelectSection,
  onSelectUnit,
}: PlanCardProps) {
  const kickerType = isSingleUnit ? terms.unit : terms.section;
  const kickerChip = isSingleUnit ? '单层' : section.units.length > 1 ? '多单元' : '段落';
  const totalDuration = section.units.reduce((sum, unit) => sum + unit.duration, 0);

  const handleCardClick = () => {
    if (isSingleUnit && section.units[0]) onSelectUnit(section.units[0].id);
    else onSelectSection(section.id);
  };

  return (
    <article
      data-creator-module={isSingleUnit ? 'unit-card' : 'section-card'}
      data-creator-module-id={isSingleUnit ? section.units[0]?.id ?? section.id : section.id}
      data-creator-module-ref={isSingleUnit ? `unit:${section.units[0]?.id ?? section.id}` : `section:${section.id}`}
      onClick={handleCardClick}
      className={`cursor-pointer rounded-xl border bg-[var(--color-bg-card)] p-4 transition-all ${
        selected
          ? 'border-[var(--color-accent)] shadow-[0_0_0_1px_var(--color-accent)]'
          : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:shadow-sm'
      }`}
    >
      <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wide text-[var(--color-text-tertiary)]">
        <span>{String(section.number).padStart(2, '0')} {kickerType}</span>
        <span className="flex items-center gap-1.5">
          <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-0.5 font-medium normal-case">
            {kickerChip}
          </span>
          {totalDuration > 0 && (
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-0.5 font-medium normal-case">
              {totalDuration}s
            </span>
          )}
        </span>
      </div>

      <div className="mt-2">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{section.title}</h3>
        {section.narrative && (
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-secondary)]">
            {section.narrative}
          </p>
        )}
      </div>

      {section.units.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {section.units.map((unit) => {
            const progress = progressOf(unit, uiPhase, activeUnitId);
            const isUnitSelected = unit.id === selectedUnitId;
            const materialNames = unit.resolvedRefs
              .filter((item) => unit.materialRefs.includes(item.ref))
              .map((item) => item.name);
            return (
              <div
                key={unit.id}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectUnit(unit.id);
                }}
                className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors ${
                  isUnitSelected
                    ? 'border-[var(--color-accent)]/40 bg-[var(--color-accent-soft)]'
                    : 'border-transparent bg-[var(--color-bg-secondary)]/60 hover:bg-[var(--color-bg-secondary)]'
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <strong className="text-xs font-semibold text-[var(--color-text-primary)]">
                      {unitDisplayName(unit)}
                    </strong>
                    <span className={`shrink-0 rounded border px-1.5 py-px text-[10px] ${PROGRESS_TONES[progress]}`}>
                      {PROGRESS_LABELS[progress]}
                    </span>
                    <span className="shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-1.5 py-px text-[10px] text-[var(--color-text-tertiary)]">
                      {unit.taskType === 'edit' ? 'AI剪辑' : 'R2V生成'}
                    </span>
                  </div>
                  {materialNames.length > 0 && (
                    <p
                      className="mt-0.5 line-clamp-1 text-[10px] text-[var(--color-text-tertiary)]"
                      title={materialNames.join('、')}
                    >
                      素材：{materialNames.join('、')}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  {unit.duration}s
                </span>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}
