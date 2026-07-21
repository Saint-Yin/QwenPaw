import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, message } from "antd";
import { Film, Plus, Scissors, Sparkles } from "lucide-react";
import { navigate, useParams, useSearchParams } from "@/routing/navigation";
import { useProjectSnapshotStore } from "@/store/projectSnapshotStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import {
  selectPrimaryTimeline,
  timelineEndTick,
} from "@/selectors/timelineElementSelectors";
import { projectJsonPointer } from "@/lib/projectJsonPointer";
import { useReviewFieldFocus } from "@/routing/reviewFocus";
import TimelineCanvas from "@/components/timeline/TimelineCanvas";
import ElementList from "@/components/timeline/ElementList";
import ElementDetail from "@/components/timeline/ElementDetail";
import PageSkeleton from "@/components/PageSkeleton";
import PageLoadError from "@/components/PageLoadError";
import type { TimelineElementDocument } from "@/contracts/creator";

function sec(tick: number, ticksPerSecond: number): string {
  return (tick / ticksPerSecond).toFixed(1).replace(/\.0$/, "");
}

export default function PlanPage() {
  const { id = "" } = useParams();
  const query = useSearchParams();
  const project = useProjectSnapshotStore((state) =>
    state.projectId === id ? state.project : null,
  );
  const syncStatus = useProjectSnapshotStore((state) => state.syncStatus);
  const syncError = useProjectSnapshotStore((state) => state.syncError);
  const requestInFlight = useProjectSnapshotStore(
    (state) => state.requestInFlight,
  );
  const patching = useProjectSnapshotStore((state) => state.patching);
  const patchProject = useProjectSnapshotStore((state) => state.patch);
  const pollOnce = useProjectSnapshotStore((state) => state.pollOnce);
  const tasks = useCreatorTaskViewStore((state) => state.tasks);
  const timeline = useMemo(() => selectPrimaryTimeline(project), [project]);
  const selectedElementId = query.get("element");
  const selectedElement =
    selectedElementId && timeline
      ? timeline.elements_by_id[selectedElementId] ?? null
      : null;
  const [playheadTick, setPlayheadTick] = useState(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const durationTick = timelineEndTick(timeline);
  const displayDurationTick = timeline
    ? durationTick ||
      Math.round(
        (project?.settings.target_duration_seconds || 10) *
          timeline.ticks_per_second,
      )
    : 1;
  const reviewMode = query.get("review") === "1";
  const reviewField = query.get("field");
  const reviewPulse = query.get("reviewPulse");
  useReviewFieldFocus({
    path: `/project/${id}/plan`,
    field: reviewField,
    enabled: reviewMode,
    pulse: reviewPulse,
  });

  useEffect(() => {
    useCreatorInteractionStore
      .getState()
      .select(selectedElement ? `element:${selectedElement.element_id}` : null);
  }, [selectedElement]);

  useEffect(() => {
    if (
      !selectedElement ||
      (playheadTick >= selectedElement.span.start_tick &&
        playheadTick <
          selectedElement.span.start_tick + selectedElement.span.duration_tick)
    )
      return;
    setPlayheadTick(selectedElement.span.start_tick);
  }, [selectedElement]);

  const base = `/project/${id}/plan`;
  const selectElement = useCallback(
    (elementId: string) => {
      const element = timeline?.elements_by_id[elementId];
      if (element) setPlayheadTick(element.span.start_tick);
      navigate(
        selectedElementId === elementId
          ? base
          : `${base}?element=${encodeURIComponent(elementId)}`,
      );
    },
    [base, selectedElementId, timeline],
  );

  const focusAgent = useCallback((ref: string, prompt: string) => {
    useCreatorInteractionStore.getState().select(ref);
    useAgentDockUiStore.getState().setOpen(true);
    useAgentDockUiStore.getState().setTab("conversation");
    useAgentDockUiStore.getState().setDraft(prompt);
  }, []);

  if (!project) {
    if (syncStatus === "invalid" || syncStatus === "not_found") {
      return (
        <PageLoadError
          message={syncError || "Project 无法读取"}
          retry={() => void pollOnce(id)}
        />
      );
    }
    return <PageSkeleton type="list" />;
  }
  if (!timeline) {
    return (
      <PageLoadError
        message="Project 中没有可用的 Timeline"
        retry={() => void pollOnce(id)}
      />
    );
  }

  const patchValue = (path: string, before: unknown, value: unknown) =>
    patchProject(id, [{ op: "replace", path, before, value }]);
  const removeElement = async (element: TimelineElementDocument) => {
    await patchProject(id, [
      {
        op: "remove",
        path: projectJsonPointer(
          "timelines",
          "items",
          timeline.timeline_id,
          "elements_by_id",
          element.element_id,
        ),
        before: element,
      },
    ]);
    navigate(base);
    message.success("Element 已删除");
  };
  const openElementAgent = (
    element: TimelineElementDocument,
    instruction?: string,
  ) => {
    focusAgent(
      `element:${element.element_id}`,
      instruction ||
        `请修改 Element「${
          element.label || element.element_id
        }」，先读取现有内容并说明计划。`,
    );
  };
  const timelineTargetRef = `timeline:${timeline.timeline_id}`;
  const activeTask = tasks.find(
    (task) => task.status === "RUNNING" || task.status === "QUEUED",
  );

  return (
    <div
      className={`flex min-h-full flex-col bg-[var(--color-bg-layout)] ${
        previewOpen ? "overflow-y-auto" : "h-full overflow-hidden"
      }`}
    >
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-5 py-3 backdrop-blur">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
            视频方案
          </h2>
          <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">
            整支片子由时间线上的 Element
            组成——可重叠、独立创作，并在同一成片中合成。
          </p>
          {(project.strategy.creative_brief ||
            project.strategy.creative_direction) && (
            <details className="mt-1 max-w-3xl text-xs text-[var(--color-text-secondary)]">
              <summary className="w-fit cursor-pointer select-none text-[var(--color-accent)]">
                查看创作总纲
              </summary>
              <div
                data-creator-field="project:strategy/creative_brief"
                data-creator-path={projectJsonPointer(
                  "strategy",
                  "creative_brief",
                )}
                data-creator-field-label="创作总纲"
                className="mt-2 max-h-44 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] p-3 leading-5"
              >
                {project.strategy.creative_brief}
                {project.strategy.creative_direction &&
                  `\n\n创作方向：${project.strategy.creative_direction}`}
              </div>
            </details>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="rounded-full border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            {sec(durationTick, timeline.ticks_per_second)}s
          </span>
          <span className="rounded-full border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            {project.settings.aspect_ratio}
          </span>
          <span className="rounded-full border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)]">
            {Object.keys(timeline.elements_by_id).length} Elements
          </span>
          <Button
            size="small"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() =>
              focusAgent(
                timelineTargetRef,
                "请在当前 Timeline 中添加新的 Element。先根据项目目标判断类型、时间位置和持续时长，再写入 Project。",
              )
            }
          >
            添加 Element
          </Button>
          <Button
            size="small"
            icon={<Scissors className="h-3.5 w-3.5" />}
            onClick={() =>
              focusAgent(
                timelineTargetRef,
                "请检查当前 Timeline 的所有 Element 和产物状态，满足条件后渲染最终成片。",
              )
            }
          >
            渲染 Timeline
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<Sparkles className="h-3.5 w-3.5" />}
            onClick={() =>
              focusAgent(
                timelineTargetRef,
                "请根据当前项目目标规划并完善整条 Timeline。用带时间范围、位置、层级和产生方式的 Element 表达全部内容。",
              )
            }
          >
            Agent 规划
          </Button>
        </div>
      </header>

      {activeTask && (
        <div className="flex shrink-0 items-center gap-2 border-b border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] px-5 py-2 text-xs text-[var(--color-accent)]">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
          <b>{activeTask.kind}</b>
          <span className="min-w-0 flex-1 truncate text-[var(--color-text-secondary)]">
            {activeTask.targetRef}
          </span>
          <span>
            {activeTask.status === "RUNNING" ? "处理中…" : "等待执行"}
          </span>
        </div>
      )}
      {syncStatus === "degraded" && (
        <div className="shrink-0 border-b border-[var(--color-warning)]/20 bg-[var(--color-warning-soft)] px-5 py-1.5 text-[11px] text-[var(--color-warning)]">
          当前显示最后一次可用快照；后台同步暂时异常。
          {syncError ? ` ${syncError}` : ""}
        </div>
      )}

      <TimelineCanvas
        project={project}
        timeline={timeline}
        durationTick={displayDurationTick}
        playheadTick={Math.min(playheadTick, displayDurationTick)}
        selectedElementId={selectedElementId}
        previewOpen={previewOpen}
        onPreviewOpenChange={setPreviewOpen}
        onPlayheadChange={(tick) =>
          setPlayheadTick(Math.max(0, Math.min(displayDurationTick, tick)))
        }
        onSelectElement={selectElement}
      />

      <main
        className={`grid min-h-0 gap-4 p-4 ${
          previewOpen
            ? "h-[340px] shrink-0 grid-cols-[minmax(280px,36fr)_minmax(0,64fr)]"
            : "flex-1 grid-cols-[minmax(280px,36fr)_minmax(0,64fr)]"
        }`}
      >
        <ElementList
          timeline={timeline}
          playheadTick={playheadTick}
          selectedElementId={selectedElementId}
          tasks={tasks}
          onSelect={selectElement}
        />
        <ElementDetail
          project={project}
          timeline={timeline}
          element={selectedElement}
          tasks={tasks}
          patching={patching || requestInFlight}
          onClose={() => navigate(base)}
          onPatch={patchValue}
          onDelete={removeElement}
          onAgent={openElementAgent}
        />
      </main>
      {Object.keys(timeline.elements_by_id).length === 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-8 flex justify-center">
          <div className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white/92 px-4 py-2 text-xs text-[var(--color-text-secondary)] shadow-lg backdrop-blur">
            <Film className="h-3.5 w-3.5 text-[var(--color-accent)]" />从
            AgentDock 描述第一组画面，Agent 会直接创建 Element
          </div>
        </div>
      )}
    </div>
  );
}
