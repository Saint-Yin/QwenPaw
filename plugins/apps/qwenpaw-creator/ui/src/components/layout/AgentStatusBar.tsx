import { useEffect, useRef, useState } from "react";
import { message } from "antd";
import { Sparkles, Square } from "lucide-react";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";

const ACTIVE_RUN_STATUSES = new Set([
  "QUEUED",
  "QUEUED_CAPACITY",
  "RUNNING_MODEL",
  "WAITING_RUNTIME",
  "WAITING_AUTHORIZATION",
]);

export default function AgentStatusBar() {
  const status = useCreatorSessionStore((state) => state.agentStatusBar);
  const session = useCreatorSessionStore((state) => state.session);
  const runs = useCreatorTaskViewStore((state) => state.runs);
  const stopping = useCreatorSessionStore((state) => state.stopping);
  const stopAllAgents = useCreatorSessionStore((state) => state.stopAllAgents);
  const subagentActivities = useCreatorSessionStore(
    (state) => state.subagentActivities,
  );
  const open = useAgentDockUiStore((state) => state.open);
  const setOpen = useAgentDockUiStore((state) => state.setOpen);
  const setTab = useAgentDockUiStore((state) => state.setTab);
  const active = Boolean(
    (status?.activity?.runningTaskCount ?? 0) > 0 ||
      (session &&
        [
          "RUNNING",
          "RESUMING",
          "WAITING_RUNTIME",
          "INTERRUPT_REQUESTED",
        ].includes(session.status)),
  );
  const waitingInput = session?.status === "WAITING_USER_INPUT";
  const hasActiveRuns = runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status));
  const hasActiveSubagents = Object.values(subagentActivities).some(
    (a) => !a.completed,
  );
  const stoppable =
    hasActiveSubagents ||
    hasActiveRuns ||
    Boolean(
      session &&
        [
          "RUNNING",
          "RESUMING",
          "WAITING_RUNTIME",
          "WAITING_EXECUTION_AUTH",
          "WAITING_USER_INPUT",
          "PENDING_REVIEW",
          "INTERRUPT_REQUESTED",
        ].includes(session.status),
    );
  const [stoppableVisible, setStoppableVisible] = useState(stoppable);
  const stoppableHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  useEffect(() => {
    if (stoppable || stopping) {
      if (stoppableHideTimerRef.current)
        clearTimeout(stoppableHideTimerRef.current);
      setStoppableVisible(true);
    } else {
      stoppableHideTimerRef.current = setTimeout(
        () => setStoppableVisible(false),
        2000,
      );
    }
    return () => {
      if (stoppableHideTimerRef.current)
        clearTimeout(stoppableHideTimerRef.current);
    };
  }, [stoppable, stopping]);
  const pendingCount = (status?.badges || []).reduce(
    (sum, badge) =>
      badge.kind === "review" || badge.kind === "execution_authorization"
        ? sum + (badge.count ?? 1)
        : sum,
    0,
  );
  const openReview = () => setTab("review");
  const completed = status?.progress.completed;
  const total = status?.progress.total;
  const progressPercent =
    typeof completed === "number" && typeof total === "number" && total > 0
      ? Math.max(0, Math.min(100, Math.round((completed / total) * 100)))
      : null;

  return (
    <div
      data-agent-status-bar
      className="flex h-[42px] shrink-0 items-center gap-0 border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]/70 text-xs text-[var(--color-text-secondary)] backdrop-blur"
    >
      <div className="flex min-w-0 flex-1 items-center gap-2 pl-4">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            active
              ? "animate-pulse bg-[var(--color-warning)] shadow-[0_0_0_5px_var(--color-warning-soft)]"
              : "bg-[var(--color-accent)] shadow-[0_0_0_5px_var(--color-accent-soft)]"
          }`}
        />
        <span className="min-w-0 truncate whitespace-nowrap">
          <b className="font-semibold text-[var(--color-text-primary)]">
            Agent 状态：
          </b>
          {stopping || session?.status === "INTERRUPT_REQUESTED"
            ? "正在停止所有 Agent"
            : status?.progress.label || "待命中，可在下方工作区继续编辑。"}
        </span>
      </div>
      <div className="flex shrink-0 self-stretch items-center gap-2 px-4">
        {progressPercent != null && progressPercent < 100 && (
          <div
            className="hidden items-center gap-1.5 sm:flex"
            aria-label={`制作进度 ${progressPercent}%`}
          >
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--color-bg-secondary)]">
              <i
                className="block h-full rounded-full bg-[var(--color-accent)] transition-[width]"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-[10px] tabular-nums text-[var(--color-text-tertiary)]">
              {progressPercent}%
            </span>
          </div>
        )}
        {stoppableVisible && (
          <button
            type="button"
            aria-label="停止所有 Agent"
            disabled={stopping}
            onClick={() =>
              void stopAllAgents()
                .then(() => message.success("已停止所有 Agent 活动"))
                .catch((error) => message.error((error as Error).message))
            }
            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-danger)] transition-colors hover:bg-[var(--color-danger)]/20 disabled:cursor-wait disabled:opacity-60"
            title={
              session?.status === "INTERRUPT_REQUESTED"
                ? "停止请求已发送，点击再次停止"
                : "立即停止当前项目的主 Agent、子 Agent 与未完成任务"
            }
          >
            <Square className="h-2.5 w-2.5 fill-current" />
            {stopping ? "正在停止" : "停止"}
          </button>
        )}
        {open && waitingInput && (
          <button
            onClick={() => setOpen(true)}
            className="animate-pulse rounded-full border border-[var(--color-warning)]/30 bg-[var(--color-warning-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-warning)]"
            title="打开 Agent 浮层继续对话"
          >
            继续输入
          </button>
        )}
        {open && pendingCount > 0 && (
          <button
            onClick={openReview}
            className="rounded-full border border-[var(--color-accent)]/30 bg-[var(--color-accent-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--color-accent)]"
            title="打开审阅/决策处理待审、需复核与 Agent 改动"
          >
            待处理 {pendingCount}
          </button>
        )}
        <button
          onClick={() => setOpen(!open)}
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors ${
            open
              ? "border-[var(--color-accent)]/40 text-[var(--color-accent)]"
              : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent)]"
          }`}
          aria-label={open ? "关闭 Agent" : "打开 Agent"}
        >
          <Sparkles className="h-3 w-3" />
          Agent
        </button>
      </div>
    </div>
  );
}
