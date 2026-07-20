import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, InputNumber, message, Modal, Upload } from 'antd';
import { PlusOutlined, ScissorOutlined, UploadOutlined } from '@ant-design/icons';
import { LayoutList, Sparkles } from 'lucide-react';
import type { SectionView } from '@/contracts/creator';
import { navigate, useParams, useSearchParams } from '@/routing/navigation';
import { selectPlanDetail, selectPlanTerms, selectPlanTotalDuration } from '@/selectors/planViewSelectors';
import { presentationOf, useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { useCreatorSessionStore } from '@/store/creatorSessionStore';
import { useCreatorInteractionStore } from '@/store/creatorInteractionStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { useNavigationStore } from '@/store/navigationStore';
import { useCreatorCommand } from '@/hooks/useCreatorCommand';
import { taskProgressPercent } from '@/lib/taskPresentation';
import { useReviewFieldFocus } from '@/routing/reviewFocus';
import { ReviewFocusPulseProvider } from '@/components/agent/ReviewFieldText';
import PageSkeleton from '@/components/PageSkeleton';
import EmptyState from '@/components/EmptyState';
import PlanCard from '@/components/plan/PlanCard';
import SectionDetail from '@/components/plan/SectionDetail';
import UnitDetail from '@/components/plan/UnitDetail';
import FinalComposePanel from '@/components/plan/FinalComposePanel';
import PageLoadError from '@/components/PageLoadError';
import { projectJsonPointer } from '@/lib/projectJsonPointer';

interface ScriptConfig {
  theme: string;
  episodeCount: number;
  durationSeconds: number;
  durationHint: string;
  style?: string;
}

type ScriptFormValues = Omit<ScriptConfig, 'durationHint'>;

const TASK_TITLES = {
  asset_ingest: '附件入库中',
  asset_import: '素材导入中',
  source_intelligence: '素材理解中',
  image_generation: '图片生成中',
  r2v_generation: '视频生成中',
  ai_edit_plan: 'AI 剪辑规划中',
  ai_edit_execute: 'AI 剪辑执行中',
  compose: '视频合成中',
} as const;

const TASK_KINDS_WITH_MEASURABLE_PROGRESS = new Set<keyof typeof TASK_TITLES>([
  'asset_ingest',
  'asset_import',
]);

function taskUpdatedAt(value?: string): number {
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function taskDetail(task: { kind: keyof typeof TASK_TITLES; status: string; progress: number | null; result?: Record<string, unknown> | null; error?: Record<string, unknown> | null }): string {
  if (task.status === 'RUNNING' || task.status === 'QUEUED') {
    if (!TASK_KINDS_WITH_MEASURABLE_PROGRESS.has(task.kind)) return '处理中…';
    const percent = taskProgressPercent(task.progress);
    return percent == null ? '处理中…' : `进度 ${percent}%`;
  }
  if (task.status === 'SUCCEEDED') {
    const summary = task.result?.summary;
    return typeof summary === 'string' && summary ? summary : '已完成';
  }
  const detail = task.error?.message || task.error?.detail || task.error?.code;
  return typeof detail === 'string' && detail ? detail : '任务失败';
}

function ScriptGeneratePanel({
  visible,
  onClose,
  onGenerate,
  loading,
  initialTheme,
}: {
  visible: boolean;
  onClose: () => void;
  onGenerate: (config: ScriptConfig) => void;
  loading: boolean;
  initialTheme?: string;
}) {
  const [form] = Form.useForm<ScriptFormValues>();
  useEffect(() => {
    if (visible) form.setFieldsValue({ theme: initialTheme || '' });
  }, [form, initialTheme, visible]);
  const handleClose = () => {
    if (loading) return;
    form.resetFields();
    onClose();
  };
  const handleSubmit = () => {
    void form.validateFields().then((values) => onGenerate({
      ...values,
      durationHint: `${values.durationSeconds}秒`,
    })).catch(() => undefined);
  };
  return (
    <Modal
      title="从主题生成剧本"
      open={visible}
      onCancel={handleClose}
      width={640}
      maskClosable={!loading}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button onClick={handleClose} disabled={loading} className="!rounded-lg">取消</Button>
          <Button type="primary" onClick={handleSubmit} loading={loading} className="!rounded-lg">开始生成</Button>
        </div>
      )}
    >
      <Form form={form} layout="vertical" initialValues={{ episodeCount: 1, durationSeconds: 60 }}>
        <Form.Item label="故事主题和想法" name="theme" rules={[{ required: true, message: '请输入原始大剧本或故事主题' }]}>
          <Input.TextArea rows={10} placeholder="写下故事主题、核心人物、冲突或大概剧情，AI 会生成分集剧本。" showCount />
        </Form.Item>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Form.Item label="集数" name="episodeCount" rules={[{ required: true, message: '请输入集数' }]}>
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="每集时长" name="durationSeconds" rules={[{ required: true, message: '请输入每集时长' }]}>
            <InputNumber min={1} precision={0} addonAfter="秒" style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <Form.Item label="视觉风格" name="style" tooltip="例如：动漫风格、写实电影风、水彩手绘风等">
          <Input placeholder="如：动漫风格" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function splitScript(text: string): Array<{ number: number; title: string; script: string }> {
  const cnNumMap: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
  const pattern = /第\s*([\d一二三四五六七八九十]+)\s*集[：:\s]*(.*)/g;
  const matches: Array<{ number: number; title: string; startIdx: number; headerEnd: number }> = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    matches.push({
      number: Number.parseInt(match[1], 10) || cnNumMap[match[1]] || matches.length + 1,
      title: match[2].trim() || `第${match[1]}集`,
      startIdx: match.index,
      headerEnd: pattern.lastIndex,
    });
  }
  if (matches.length > 0) return matches.map((item, index) => ({
    number: item.number,
    title: item.title,
    script: text.slice(item.headerEnd, matches[index + 1]?.startIdx ?? text.length).trim(),
  }));
  const parts = text.split(/\n\s*\n/).filter((item) => item.trim());
  return (parts.length ? parts : [text]).map((item, index) => ({
    number: index + 1,
    title: parts.length === 1 ? '导入剧本' : `第${index + 1}集`,
    script: item.trim(),
  }));
}

function ScriptImportDialog({ visible, onClose, onImport }: {
  visible: boolean;
  onClose: () => void;
  onImport: (text: string, sections: ReturnType<typeof splitScript>) => void;
}) {
  const [text, setText] = useState('');
  const handleOk = () => {
    if (!text.trim()) {
      message.warning('请输入或上传剧本内容');
      return;
    }
    const sections = splitScript(text);
    onImport(text, sections);
    setText('');
    onClose();
    message.success(`已导入 ${sections.length} 集剧本`);
  };
  return (
    <Modal title="导入剧本" open={visible} onCancel={onClose} onOk={handleOk} okText="导入" cancelText="取消" width={600}>
      <div className="space-y-4">
        <p className="text-sm text-[var(--color-text-secondary)]">粘贴文本或上传 .txt 文件，按“第X集”或空行拆分。</p>
        <Upload
          accept=".txt,.text"
          beforeUpload={(file) => {
            const reader = new FileReader();
            reader.onload = (event) => setText(String(event.target?.result || ''));
            reader.readAsText(file);
            return false;
          }}
          showUploadList={false}
        >
          <Button icon={<UploadOutlined />}>上传文本文件</Button>
        </Upload>
        <Input.TextArea value={text} onChange={(event) => setText(event.target.value)} rows={12} placeholder="在此粘贴剧本内容..." className="!text-sm" />
        {text.trim() && <p className="text-xs text-[var(--color-text-tertiary)]">预览：将拆分为 {splitScript(text).length} 集</p>}
      </div>
    </Modal>
  );
}

export default function PlanPage() {
  const { id = '' } = useParams();
  const query = useSearchParams();
  const envelope = useWorkspaceViewStore((state) => state.plan);
  const headerEnvelope = useWorkspaceViewStore((state) => state.header);
  const load = useWorkspaceViewStore((state) => state.loadPlan);
  const loadWorkbench = useWorkspaceViewStore((state) => state.loadWorkbench);
  const workbenches = useWorkspaceViewStore((state) => state.workbenches);
  const loading = useWorkspaceViewStore((state) => state.loading.plan);
  const workspaceLoading = useWorkspaceViewStore((state) => state.loading);
  const error = useWorkspaceViewStore((state) => state.errors.plan);
  const workspaceErrors = useWorkspaceViewStore((state) => state.errors);
  const events = useCreatorSessionStore((state) => state.events);
  const creatorSession = useCreatorSessionStore((state) => state.session);
  const view = presentationOf(envelope);
  const header = presentationOf(headerEnvelope);
  const [generatePanelVisible, setGeneratePanelVisible] = useState(false);
  const [importVisible, setImportVisible] = useState(false);
  const [finalComposeVisible, setFinalComposeVisible] = useState(query.get('finalCompose') === '1');
  const [regeneratingSectionIds, setRegeneratingSectionIds] = useState<Set<string>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);
  const tasks = useCreatorTaskViewStore((state) => state.tasks);
  const pendingRestore = useNavigationStore((state) => state.pendingRestore);
  const selectedUnitId = query.get('unit') ?? undefined;
  const selectedSectionId = query.get('section') ?? undefined;
  const reviewMode = query.get('review') === '1';
  const reviewField = query.get('field');
  const reviewPulse = query.get('reviewPulse');
  const refresh = useCallback(() => load(id), [id, load]);
  const { submit, submitting } = useCreatorCommand(id, envelope, refresh);
  const lastWorkspaceSeq = [...events].reverse().find((event) => (
    event.type === 'workspace.head_changed'
    || event.type === 'subagent.completed'
    || event.type === 'agent.run.completed'
  ))?.seq;

  useEffect(() => { void load(id).catch(() => undefined); }, [id, load, lastWorkspaceSeq]);
  useEffect(() => { setFinalComposeVisible(query.get('finalCompose') === '1'); }, [query]);
  useReviewFieldFocus({ path: `/project/${id}/plan`, field: reviewField, enabled: reviewMode, pulse: reviewPulse });

  // 与 origin/main 一致：跨上下文返回时恢复方案列表的滚动位置。
  useEffect(() => {
    if (!pendingRestore || pendingRestore.scrollTop == null || !listRef.current) return;
    listRef.current.scrollTop = pendingRestore.scrollTop;
    useNavigationStore.getState().consumeRestore();
  }, [pendingRestore, view?.sections.length]);

  const { selectedSection, selectedUnit, detailOpen } = useMemo(
    () => selectPlanDetail(view, selectedSectionId, selectedUnitId),
    [selectedSectionId, selectedUnitId, view],
  );
  const selectedWorkbenchKey = selectedUnit ? `workbench:${selectedUnit.id}` : null;
  const selectedEditWorkbench = selectedUnit?.taskType === 'edit'
    ? workbenches[selectedUnit.id]
    : undefined;
  const selectedWorkbenchView = selectedEditWorkbench ? presentationOf(selectedEditWorkbench) : null;
  const selectedEditWorkbenchView = selectedWorkbenchView?.kind === 'edit' ? selectedWorkbenchView : null;
  useEffect(() => {
    if (
      !selectedUnit
      || selectedUnit.taskType !== 'edit'
      || selectedEditWorkbench
      || !selectedWorkbenchKey
      || workspaceLoading[selectedWorkbenchKey]
      || workspaceErrors[selectedWorkbenchKey]
    ) return;
    void loadWorkbench(id, selectedUnit.id).catch(() => undefined);
  }, [id, loadWorkbench, selectedEditWorkbench, selectedUnit, selectedWorkbenchKey, workspaceErrors, workspaceLoading]);
  useEffect(() => {
    useCreatorInteractionStore.getState().select(selectedUnit ? `unit:${selectedUnit.id}` : selectedSection ? `section:${selectedSection.id}` : null);
  }, [selectedSection, selectedUnit]);
  const totalDuration = useMemo(() => selectPlanTotalDuration(view), [view]);
  const terms = selectPlanTerms(header?.scenario);
  const runningTask = useMemo(
    () => [...tasks]
      .filter((task) => task.status === 'RUNNING' || task.status === 'QUEUED')
      .sort((left, right) => taskUpdatedAt(right.updatedAt) - taskUpdatedAt(left.updatedAt))[0],
    [tasks],
  );
  const [taskClock, setTaskClock] = useState(0);
  const [dismissedTaskId, setDismissedTaskId] = useState<string | null>(null);
  const finishedTask = useMemo(
    () => [...tasks]
      .filter((task) => (
        task.status !== 'RUNNING'
        && task.status !== 'QUEUED'
        && task.id !== dismissedTaskId
        && Date.now() - taskUpdatedAt(task.updatedAt) < 5000
      ))
      .sort((left, right) => taskUpdatedAt(right.updatedAt) - taskUpdatedAt(left.updatedAt))[0],
    [dismissedTaskId, taskClock, tasks],
  );
  useEffect(() => {
    if (!finishedTask) return undefined;
    const remaining = 5000 - (Date.now() - taskUpdatedAt(finishedTask.updatedAt));
    if (remaining <= 0) {
      setTaskClock((value) => value + 1);
      return undefined;
    }
    const timer = window.setTimeout(() => setTaskClock((value) => value + 1), remaining + 50);
    return () => window.clearTimeout(timer);
  }, [finishedTask]);
  const activeTask = runningTask || finishedTask;
  const taskActive = Boolean(runningTask);
  const taskJustFinished = !runningTask && Boolean(finishedTask);

  if (error && !view) return <PageLoadError message={error} retry={() => void load(id)} />;
  if (loading && !view) return <PageSkeleton type="list" />;
  if (!view || !envelope) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--color-bg-secondary)]">
        <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-5 py-3 backdrop-blur">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">视频方案</h2>
          <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">先建立第一版视频结构，再逐步完善生成单元。</p>
        </div>
        {activeTask && (
          <div className="flex shrink-0 items-center gap-3 border-b border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] px-5 py-2 text-xs text-[var(--color-accent)]">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full bg-current ${taskActive ? 'animate-pulse' : ''}`} />
            <span className="min-w-0 shrink font-semibold">{TASK_TITLES[activeTask.kind]}</span>
            <span className="min-w-0 flex-1 truncate text-[var(--color-text-secondary)]">{taskDetail(activeTask)}</span>
            <span className="shrink-0 rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              {taskActive ? '进行中' : '已结束'}
            </span>
          </div>
        )}
        <div className="flex-1 overflow-auto">
          <EmptyState
            icon={LayoutList}
            title="准备创建视频结构"
            description="项目暂时还没有可展示的结构；可以重新加载，或在 AgentDock 中描述你想创建的内容。"
            actionText="重新加载"
            onAction={() => void load(id)}
          />
        </div>
      </div>
    );
  }

  const base = `/project/${id}/plan`;
  const selectSection = (sectionId: string) => navigate(`${base}?section=${encodeURIComponent(sectionId)}`);
  const selectUnit = (unitId: string) => navigate(`${base}?unit=${encodeURIComponent(unitId)}`);
  const clearSelection = () => navigate(base);
  const patchSection = (section: SectionView, field: 'narrative' | 'durationBudget' | 'constraints' | 'script', value: string | number | string[]) => (
    submit('SET_SECTION_TEXT', `section:${section.id}`, { field, value }, section.targetVersion)
  );
  const regenerateSection = async (section: SectionView) => {
    setRegeneratingSectionIds((previous) => new Set(previous).add(section.id));
    try {
      await submit('PLAN_UNITS', `section:${section.id}`, { regenerate: true }, section.targetVersion);
    } finally {
      setRegeneratingSectionIds((previous) => {
        const next = new Set(previous);
        next.delete(section.id);
        return next;
      });
    }
  };
  const creatorBusy = creatorSession != null && !['IDLE', 'PENDING_REVIEW', 'WAITING_USER_INPUT', 'WAITING_EXECUTION_AUTH', 'CANCELLED', 'ERROR'].includes(creatorSession.status);
  const requestAgentTaskPlan = () => {
    const selectedSection = selectedSectionId
      ? view.sections.find((section) => section.id === selectedSectionId)
      : undefined;
    return submit(
      'PLAN_UNITS',
      selectedSection ? `section:${selectedSection.id}` : 'project:plan',
      {},
      selectedSection?.targetVersion ?? view.targetVersion,
    );
  };

  return (
    <ReviewFocusPulseProvider field={reviewMode ? reviewField : null} pulse={reviewPulse}>
    <div className="flex h-full flex-col overflow-hidden bg-[var(--color-bg-layout)]">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-5 py-3 backdrop-blur">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">视频方案</h2>
          <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">先以{terms.structure}组织整支片子，再从具体{terms.unit}进入制作工作台。</p>
          {view.outline && (
            <details className="mt-1 max-w-3xl text-xs text-[var(--color-text-secondary)]">
              <summary className="cursor-pointer select-none text-[var(--color-accent)]">查看故事总纲与旁白</summary>
              <div
                data-creator-field="project:plan/outline"
                data-creator-path={projectJsonPointer('story', 'outline')}
                data-creator-field-label="故事总纲与旁白"
                className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] p-3 leading-5"
              >
                {view.outline}
              </div>
            </details>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {totalDuration > 0 && <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)]">{totalDuration}s</span>}
          <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)]">{view.aspectRatio}</span>
          <Button
            size="small"
            icon={<PlusOutlined />}
            disabled={submitting}
            onClick={() => void submit('CREATE_SECTION', 'project:plan', { title: `结构段 ${view.sections.length + 1}`, afterSectionId: view.sections.at(-1)?.id }, view.targetVersion)}
            className="!text-xs"
          >
            添加结构段
          </Button>
          <Button size="small" icon={<ScissorOutlined />} onClick={() => setFinalComposeVisible(true)} className="!text-xs">最终合成</Button>
          <Button
            size="small"
            icon={<Sparkles className="h-3 w-3" />}
            onClick={() => void requestAgentTaskPlan()}
            loading={creatorBusy}
            className="!text-xs"
          >
            Agent 规划任务
          </Button>
        </div>
      </div>

      {activeTask && (
        <div className={`flex shrink-0 items-center gap-3 border-b px-5 py-2 text-xs transition-colors ${
          taskJustFinished && activeTask.status !== 'SUCCEEDED'
            ? 'border-[var(--color-danger)]/30 bg-[var(--color-danger-soft)] text-[var(--color-danger)]'
            : taskJustFinished
              ? 'border-[var(--color-success)]/30 bg-[var(--color-success-soft)] text-[var(--color-success)]'
              : 'border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] text-[var(--color-accent)]'
        }`}>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${taskActive ? 'animate-pulse' : ''} bg-current`} />
          <span className="min-w-0 shrink font-semibold">{TASK_TITLES[activeTask.kind]}</span>
          <span className="min-w-0 flex-1 truncate text-[var(--color-text-secondary)]">{taskDetail(activeTask)}</span>
          {taskActive ? (
            <span className="shrink-0 rounded-full bg-[var(--color-accent)]/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">进行中</span>
          ) : (
            <button
              type="button"
              onClick={() => setDismissedTaskId(activeTask.id)}
              className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide opacity-70 transition-opacity hover:opacity-100"
              aria-label="关闭"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {view.sections.length === 0 ? (
        <div className="flex-1 overflow-auto">
          <EmptyState
            icon={LayoutList}
            title="还没有视频结构"
            description="用一句话描述目标生成第一版结构，或导入已有剧本"
            actionText="生成结构"
            onAction={() => setGeneratePanelVisible(true)}
            extra={<Button className="mt-3 !rounded-lg" onClick={() => setImportVisible(true)}>导入剧本</Button>}
          />
        </div>
      ) : (
        <div
          className="grid min-h-0 flex-1 gap-4 p-4 transition-[grid-template-columns] duration-300"
          style={{ gridTemplateColumns: detailOpen ? 'minmax(0,36fr) minmax(0,64fr)' : 'minmax(0,1fr) 0fr' }}
        >
          <div ref={listRef} className="min-h-0 space-y-3 overflow-y-auto pr-1" data-plan-list>
            {view.sections.map((section) => (
              <PlanCard
                key={section.id}
                section={section}
                terms={terms}
                isSingleUnit={section.units.length === 1 && !section.narrative && !section.constraints.length}
                selected={section.id === selectedSection?.id}
                selectedUnitId={selectedUnit?.id}
                uiPhase={envelope.uiPhase}
                activeUnitId={envelope.agentStatusBar.progress.unitId}
                onSelectSection={(sectionId) => sectionId === selectedSectionId ? clearSelection() : selectSection(sectionId)}
                onSelectUnit={(unitId) => unitId === selectedUnitId ? clearSelection() : selectUnit(unitId)}
              />
            ))}
          </div>
          <aside className={`min-h-0 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-primary)] shadow-sm transition-opacity duration-300 ${detailOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
            {selectedSection && selectedUnit ? (
              <UnitDetail
                projectId={id}
                section={selectedSection}
                unit={selectedUnit}
                uiPhase={envelope.uiPhase}
                activeUnitId={envelope.agentStatusBar.progress.unitId}
                editWorkbench={selectedEditWorkbenchView}
                editWorkbenchLoading={selectedWorkbenchKey ? workspaceLoading[selectedWorkbenchKey] : false}
                editWorkbenchError={selectedWorkbenchKey ? workspaceErrors[selectedWorkbenchKey] : undefined}
                onDelete={() => Modal.confirm({
                  title: '确认删除',
                  content: '删除后无法恢复，确定要删除该生成单元吗？',
                  okText: '删除',
                  okButtonProps: { danger: true },
                  onOk: async () => {
                    const result = await submit('DELETE_UNIT', `unit:${selectedUnit.id}`, {}, selectedUnit.targetVersion);
                    if (!result) throw new Error('删除命令未提交');
                    navigate(base);
                  },
                })}
              />
            ) : selectedSection ? (
              <SectionDetail
                projectId={id}
                section={selectedSection}
                terms={terms}
                onPatch={(field, value) => patchSection(selectedSection, field, value)}
                onSelectUnit={selectUnit}
                onRegenerateUnits={() => regenerateSection(selectedSection)}
                regenerating={regeneratingSectionIds.has(selectedSection.id)}
                onDelete={() => Modal.confirm({
                  title: '确认删除',
                  content: '删除结构段会同时删除其下所有生成单元，确定要删除吗？',
                  okText: '删除',
                  okButtonProps: { danger: true },
                  onOk: async () => {
                    const result = await submit('DELETE_SECTION', `section:${selectedSection.id}`, {}, selectedSection.targetVersion);
                    if (!result) throw new Error('删除命令未提交');
                    navigate(base);
                  },
                })}
              />
            ) : null}
          </aside>
        </div>
      )}

      <ScriptGeneratePanel
        visible={generatePanelVisible}
        onClose={() => setGeneratePanelVisible(false)}
        onGenerate={(config) => {
          setGeneratePanelVisible(false);
          void submit('GENERATE_SCRIPT', 'project:plan', { ...config }, view.targetVersion);
        }}
        loading={submitting}
        initialTheme={header?.masterScript}
      />
      <ScriptImportDialog
        visible={importVisible}
        onClose={() => setImportVisible(false)}
        onImport={(text, sections) => void submit('IMPORT_SCRIPT', 'project:plan', { text, sections }, view.targetVersion)}
      />
      <FinalComposePanel
        projectId={id}
        visible={finalComposeVisible}
        onClose={() => {
          setFinalComposeVisible(false);
          if (query.get('finalCompose') === '1') navigate(base);
        }}
        focusVersion={query.get('version')}
        focusPulse={reviewPulse}
      />
    </div>
    </ReviewFocusPulseProvider>
  );
}
