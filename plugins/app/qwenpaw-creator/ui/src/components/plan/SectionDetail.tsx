import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, InputNumber, message, Tooltip } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { AlertTriangle, Clapperboard, Film, Trash2 } from 'lucide-react';
import type { SectionView } from '@/contracts/creator';
import { navigate } from '@/routing/navigation';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import ReviewFieldText, { ReviewDiffPreview } from '@/components/agent/ReviewFieldText';
import { projectJsonPointer } from '@/lib/projectJsonPointer';

const { TextArea } = Input;

type EditableSectionField = 'narrative' | 'durationBudget' | 'constraints' | 'script';

interface SectionDetailProps {
  projectId: string;
  section: SectionView;
  terms?: { section: string; unit: string };
  onPatch: (field: EditableSectionField, value: string | number | string[]) => Promise<unknown> | void;
  onSelectUnit: (unitId: string) => void;
  onRegenerateUnits: () => Promise<unknown> | void;
  regenerating: boolean;
  onDelete?: () => void;
}

function Block({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-bold text-[var(--color-text-secondary)]">{title}</h4>
        {extra}
      </div>
      {children}
    </section>
  );
}

function useDebouncedField(
  delay: number,
  callback: (field: EditableSectionField, value: string | number | string[]) => Promise<unknown> | void,
) {
  const callbackRef = useRef(callback);
  const timers = useRef(new Map<EditableSectionField, ReturnType<typeof setTimeout>>());
  const pending = useRef(new Map<EditableSectionField, string | number | string[]>());
  callbackRef.current = callback;
  useEffect(() => () => {
    for (const timer of timers.current.values()) clearTimeout(timer);
    timers.current.clear();
    for (const [field, value] of pending.current) void callbackRef.current(field, value);
    pending.current.clear();
  }, []);
  return (field: EditableSectionField, value: string | number | string[]) => {
    pending.current.set(field, value);
    const previous = timers.current.get(field);
    if (previous) clearTimeout(previous);
    timers.current.set(field, setTimeout(() => {
      timers.current.delete(field);
      const latest = pending.current.get(field);
      pending.current.delete(field);
      if (latest !== undefined) void callbackRef.current(field, latest);
    }, delay));
  };
}

/** origin/main Section detail layout backed exclusively by semantic Commands. */
export default function SectionDetail({
  projectId,
  section,
  terms = { section: 'Section', unit: '生成单元' },
  onPatch,
  onSelectUnit,
  onRegenerateUnits,
  regenerating,
  onDelete,
}: SectionDetailProps) {
  const manifest = useReviewManifestStore((state) => state.manifest);
  const [narrativeDraft, setNarrativeDraft] = useState(section.narrative ?? '');
  const [scriptDraft, setScriptDraft] = useState(section.script ?? '');
  const [constraintDrafts, setConstraintDrafts] = useState(section.constraints);
  const [scriptExpanded, setScriptExpanded] = useState(false);

  useEffect(() => {
    setNarrativeDraft(section.narrative ?? '');
    setScriptDraft(section.script ?? '');
    setConstraintDrafts(section.constraints);
  }, [section.id, section.narrative, section.script, section.constraints]);

  const debouncedPatch = useDebouncedField(600, onPatch);
  const actualDuration = section.units.reduce((sum, unit) => sum + unit.duration, 0);
  const overBudget = Boolean(section.durationBudget && actualDuration > section.durationBudget);
  const pendingOperationIds = useMemo(() => new Set(
    manifest?.decisionGroups.filter((group) => group.decision === 'PENDING').flatMap((group) => group.operationIds) ?? [],
  ), [manifest]);
  const removedUnitIds = useMemo(() => new Set(
    manifest?.operations.filter((operation) => (
      pendingOperationIds.has(operation.id)
      && operation.kind === 'delete'
      && operation.targetRef.startsWith('unit:')
      && Boolean(operation.path?.includes(`--${section.id}--`))
    )).map((operation) => operation.targetRef.slice(5).split('/', 1)[0]) ?? [],
  ), [manifest, pendingOperationIds, section.id]);
  const addedUnitOperations = useMemo(() => {
    const operations = manifest?.operations.filter((operation) => (
      pendingOperationIds.has(operation.id)
      && operation.kind === 'create'
      && operation.targetRef.startsWith('unit:')
      && Boolean(operation.path?.includes(`--${section.id}--`))
    )) ?? [];
    return [...new Map(operations.map((operation) => [operation.targetRef, operation])).values()];
  }, [manifest, pendingOperationIds, section.id]);

  const updateConstraint = (index: number, value: string) => {
    const next = constraintDrafts.map((constraint, itemIndex) => itemIndex === index ? value : constraint);
    setConstraintDrafts(next);
    debouncedPatch('constraints', next);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {String(section.number).padStart(2, '0')}{' '}
            <span
              data-creator-field={`section:${section.id}/title`}
              data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'title')}
              data-creator-field-label="标题"
            >
              <ReviewFieldText field={`section:${section.id}/title`}>{section.title}</ReviewFieldText>
            </span>
          </h3>
          <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">
            {terms.section}定义整体叙事与约束，不直接进入制作工作台。
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="shrink-0 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            {terms.section}
          </span>
          {onDelete && (
            <Tooltip title="删除结构段">
              <button
                type="button"
                onClick={onDelete}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <Block title="叙事定位">
          <TextArea
            data-creator-field={`section:${section.id}/narrative`}
            data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'narrative')}
            data-creator-field-label="叙事定位"
            value={narrativeDraft}
            onChange={(event) => {
              setNarrativeDraft(event.target.value);
              debouncedPatch('narrative', event.target.value);
            }}
            autoSize={{ minRows: 3, maxRows: 10 }}
            placeholder="这一段在整支片子中的叙事作用、情绪与信息目标…"
            className="!rounded-lg !border-[var(--color-border)] !bg-[var(--color-bg-secondary)] !text-xs"
          />
          <ReviewDiffPreview field={`section:${section.id}/narrative`} />
        </Block>

        <Block
          title="时长预算"
          extra={overBudget && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--color-warning)]">
              <AlertTriangle className="h-3 w-3" />
              子单元总时长已超出预算
            </span>
          )}
        >
          <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
            <InputNumber
              data-creator-field={`section:${section.id}/durationBudget`}
              data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'duration_budget_seconds')}
              data-creator-field-label="时长预算"
              min={0}
              value={section.durationBudget}
              onChange={(value) => void onPatch('durationBudget', value ?? 0)}
              addonAfter="秒"
              size="small"
              className="!w-32"
              placeholder="不限"
            />
            <span>
              当前子单元合计 <b className={overBudget ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-primary)]'}>{actualDuration}s</b>
            </span>
          </div>
          <ReviewDiffPreview field={`section:${section.id}/durationBudget`} />
        </Block>

        <Block
          title="继承约束"
          extra={(
            <Button
              type="text"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                const next = [...constraintDrafts, ''];
                setConstraintDrafts(next);
                void onPatch('constraints', next);
              }}
              className="!text-xs !text-[var(--color-text-secondary)]"
            >
              添加
            </Button>
          )}
        >
          <div
            data-creator-field={`section:${section.id}/constraints`}
            data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'constraints')}
            data-creator-field-label="继承约束"
          >
            {constraintDrafts.length === 0 ? (
              <p className="text-xs text-[var(--color-text-tertiary)]">暂无约束。段落级约束会被其下所有{terms.unit}继承。</p>
            ) : (
              <div>
                <div
                  data-section-constraints-list
                  className="divide-y divide-[var(--color-border)] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/40"
                >
                  {constraintDrafts.map((constraint, index) => (
                    <div key={index} className="flex items-center gap-1 px-2 py-1 transition-colors hover:bg-[var(--color-bg-secondary)]">
                      <span className="w-5 shrink-0 text-center text-[10px] font-semibold text-[var(--color-text-tertiary)]">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <Input
                        value={constraint}
                        onChange={(event) => updateConstraint(index, event.target.value)}
                        size="small"
                        variant="borderless"
                        placeholder="如：保持真实产品质感，不允许 Logo 变形"
                        className="!bg-transparent !px-1 !text-xs !shadow-none"
                      />
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        aria-label={`删除约束 ${index + 1}`}
                        onClick={() => {
                          const next = constraintDrafts.filter((_, itemIndex) => itemIndex !== index);
                          setConstraintDrafts(next);
                          void onPatch('constraints', next);
                          message.info('约束已删除，影响分析将在后续版本生效');
                        }}
                        className="!shrink-0 !text-[var(--color-text-tertiary)] hover:!text-[var(--color-danger)]"
                      />
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-[var(--color-text-tertiary)]">段落级约束会统一传递给下属{terms.unit}。</p>
              </div>
            )}
          </div>
          <ReviewDiffPreview field={`section:${section.id}/constraints`} />
        </Block>

        <Block title={`子单元清单（${section.units.length}）`}>
          {section.units.length === 0 && addedUnitOperations.length === 0 ? (
            <p className="text-xs text-[var(--color-text-tertiary)]">尚无{terms.unit}，可从下方剧本原文生成分镜。</p>
          ) : (
            <div className="space-y-1.5">
              {section.units.map((unit) => {
                const removed = removedUnitIds.has(unit.id);
                return (
                <button
                  key={unit.id}
                  type="button"
                  onClick={() => onSelectUnit(unit.id)}
                  {...(removed ? { 'data-review-field': `unit:${unit.id}`, 'data-review-field-label': `删除${terms.unit}` } : {})}
                  className="flex w-full items-center gap-2 rounded-lg border border-transparent bg-[var(--color-bg-secondary)]/60 px-2.5 py-2 text-left transition-colors hover:border-[var(--color-border)] hover:bg-[var(--color-bg-secondary)]"
                >
                  <span className={`min-w-0 flex-1 truncate text-xs font-medium text-[var(--color-text-primary)] ${removed ? 'agent-diff-del' : ''}`}>
                    {unit.title ? `${String(unit.number).padStart(2, '0')} ${unit.title}` : `${unit.taskType === 'edit' ? '剪辑单元' : '生成单元'} ${String(unit.number).padStart(2, '0')}`}
                  </span>
                  <span className="shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-1.5 py-px text-[10px] text-[var(--color-text-tertiary)]">
                    {removed ? '待删除' : unit.taskType === 'edit' ? 'AI剪辑' : 'R2V生成'}
                  </span>
                  <span className="shrink-0 text-[11px] text-[var(--color-text-tertiary)]">{unit.duration}s</span>
                </button>
                );
              })}
              {addedUnitOperations.map((operation) => (
                <div key={operation.id} data-review-field={operation.path || operation.targetRef} data-review-field-label={`新增${terms.unit}`} className="flex w-full items-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-secondary)]/40 px-2.5 py-2 text-left">
                  <span className="agent-diff-add min-w-0 flex-1 truncate text-xs font-medium"><ReviewFieldText field={operation.path || operation.targetRef}>新增{terms.unit}</ReviewFieldText></span>
                  <span className="shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-1.5 py-px text-[10px] text-[var(--color-text-tertiary)]">待新增</span>
                </div>
              ))}
            </div>
          )}
        </Block>

        <Block
          title="剧本原文"
          extra={(
            <div className="flex items-center gap-2">
              <Button
                type="text"
                size="small"
                onClick={() => setScriptExpanded((value) => !value)}
                className="!text-xs !text-[var(--color-text-secondary)]"
              >
                {scriptExpanded ? '收起' : '展开'}
              </Button>
              <Tooltip title="按 15 秒生成窗口重新拆解本段的生成单元">
                <Button
                  size="small"
                  icon={<Clapperboard className="h-3 w-3" />}
                  loading={regenerating}
                  disabled={!scriptDraft.trim()}
                  onClick={() => void onRegenerateUnits()}
                  className="!text-xs"
                >
                  生成分镜
                </Button>
              </Tooltip>
            </div>
          )}
        >
          {scriptExpanded ? (
            <TextArea
              data-creator-field={`section:${section.id}/script`}
              data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'script')}
              data-creator-field-label="剧本原文"
              value={scriptDraft}
              onChange={(event) => {
                setScriptDraft(event.target.value);
                debouncedPatch('script', event.target.value);
              }}
              autoSize={{ minRows: 6, maxRows: 24 }}
              placeholder="本段剧本原文…"
              className="!rounded-lg !border-[var(--color-border)] !bg-[var(--color-bg-secondary)] !text-xs"
            />
          ) : (
            <p
              data-creator-field={`section:${section.id}/script`}
              data-creator-path={projectJsonPointer('story', 'sections', 'items', section.id, 'script')}
              data-creator-field-label="剧本原文"
              className="line-clamp-3 text-xs text-[var(--color-text-secondary)]"
            >
              <ReviewFieldText field={`section:${section.id}/script`}>{scriptDraft.trim() || '暂无剧本原文。'}</ReviewFieldText>
            </p>
          )}
          {scriptExpanded && <ReviewDiffPreview field={`section:${section.id}/script`} />}
        </Block>
      </div>

      <div className="border-t border-[var(--color-border)] p-4">
        <Button
          type="primary"
          block
          onClick={() => navigate(`/project/${projectId}/plan/section/${section.id}`)}
          className="!h-9 !font-semibold"
        >
          <span className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none">
            <span>拼接与预览</span>
            <Film className="h-3.5 w-3.5 shrink-0" />
          </span>
        </Button>
      </div>
    </div>
  );
}
