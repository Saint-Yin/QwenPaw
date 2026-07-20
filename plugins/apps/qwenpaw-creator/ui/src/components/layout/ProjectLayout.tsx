import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router-dom";
import { useShallow } from "zustand/react/shallow";
import { useParams, usePathname, useRouter } from "@/routing/navigation";
import type { FileProjectReviewOperation } from "@/contracts/creator";
import { useWorkspaceViewStore } from "@/store/workspaceViewStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import {
  CreatorPanel,
  useCreatorInteractionStore,
} from "@/store/creatorInteractionStore";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import { useNavigationStore } from "@/store/navigationStore";
import { useProjectSnapshotStore } from "@/store/projectSnapshotStore";
import { useFileProjectReviewStore } from "@/store/fileProjectReviewStore";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import TopNav from "./TopNav";
import AgentStatusBar from "./AgentStatusBar";
import ReturnBanner from "@/components/creator/ReturnBanner";
import { AgentDock, SelectionToolbar } from "@/components/agent";
import PageSkeleton from "@/components/PageSkeleton";

const SUBAGENT_LIFECYCLE_EVENTS = new Set([
  "subagent.accepted",
  "subagent.started",
  "subagent.waiting_runtime",
  "subagent.completed",
  "subagent.blocked",
  "subagent.failed",
  "subagent.stale",
  "subagent.continuation_started",
  "subagent.continuation_completed",
]);

const FILE_AGENT_LIFECYCLE_EVENTS = new Set([
  "agent.run.started",
  "agent.run.completed",
  "agent.run.failed",
  "agent.run.cancelled",
  "agent.review.resolved",
  "agent.interrupt.idle",
]);

function isSubagentLifecycleEvent(type: string): boolean {
  return SUBAGENT_LIFECYCLE_EVENTS.has(type);
}

function isFileAgentLifecycleEvent(type: string): boolean {
  return FILE_AGENT_LIFECYCLE_EVENTS.has(type);
}

function isProjectShellEvent(type: string): boolean {
  return (
    type === "workspace.head_changed" ||
    type === "workspace.manual_edit_committed" ||
    type.startsWith("session.") ||
    type.startsWith("task.") ||
    type.startsWith("task_") ||
    isSubagentLifecycleEvent(type) ||
    isFileAgentLifecycleEvent(type)
  );
}

function reviewIdsFromEvent(data: Record<string, unknown>): string[] {
  if (!Array.isArray(data.reviewIds)) return [];
  return data.reviewIds.filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
}

function reviewClipTargets(
  operations: FileProjectReviewOperation[],
): Array<{ unitId: string; clipIds: string[] }> {
  const byUnit = new Map<string, Set<string>>();
  operations.forEach((operation) => {
    if (operation.decision !== "PENDING" || !operation.json_pointer) return;
    const tokens = operation.json_pointer
      .slice(1)
      .split("/")
      .map((token) => token.replace(/~1/g, "/").replace(/~0/g, "~"));
    if (
      tokens[0] !== "production" ||
      tokens[1] !== "units_by_id" ||
      tokens[3] !== "plan" ||
      tokens[4] !== "timeline" ||
      tokens[5] !== "items" ||
      !tokens[2] ||
      !tokens[6]
    )
      return;
    const clipIds = byUnit.get(tokens[2]) ?? new Set<string>();
    clipIds.add(tokens[6]);
    byUnit.set(tokens[2], clipIds);
  });
  return [...byUnit].map(([unitId, clipIds]) => ({
    unitId,
    clipIds: [...clipIds],
  }));
}

function LayoutSkeleton() {
  return (
    <div
      data-project-shell
      data-top-nav-height="58"
      data-agent-status-bar-height="42"
      className="app-shell grid h-screen grid-rows-[58px_42px_minmax(0,1fr)]"
    >
      <TopNav />
      <AgentStatusBar />
      <main data-creator-workspace-root className="flex-1 overflow-hidden">
        <PageSkeleton type="list" />
      </main>
    </div>
  );
}

export default function ProjectLayout() {
  const { id = "" } = useParams();
  const pathname = usePathname();
  const router = useRouter();
  const header = useWorkspaceViewStore((state) => state.header);
  const loadHeader = useWorkspaceViewStore((state) => state.loadHeader);
  const loadPlan = useWorkspaceViewStore((state) => state.loadPlan);
  const loadWorkbench = useWorkspaceViewStore((state) => state.loadWorkbench);
  const revalidateLoadedViews = useWorkspaceViewStore(
    (state) => state.revalidateLoaded,
  );
  const bootstrap = useCreatorSessionStore((state) => state.bootstrap);
  const refreshSession = useCreatorSessionStore(
    (state) => state.refreshSession,
  );
  const disconnect = useCreatorSessionStore((state) => state.disconnect);
  const sessionStatus = useCreatorSessionStore(
    (state) => state.session?.status ?? null,
  );
  const events = useCreatorSessionStore(
    useShallow((state) =>
      state.events.filter((event) => isProjectShellEvent(event.type)),
    ),
  );
  const refreshTasks = useCreatorTaskViewStore((state) => state.refresh);
  const startProjectSnapshotPolling = useProjectSnapshotStore(
    (state) => state.startPolling,
  );
  const snapshotRevision = useProjectSnapshotStore(
    useShallow((state) => ({
      projectId: state.projectId,
      generation: state.generation,
      etag: state.etag,
    })),
  );
  const startFileReviewPolling = useFileProjectReviewStore(
    (state) => state.startPolling,
  );
  const activeFileReview = useFileProjectReviewStore((state) => state.review);
  const fileReviewSyncStatus = useFileProjectReviewStore(
    (state) => state.syncStatus,
  );
  const [pendingReviewNavigation, setPendingReviewNavigation] = useState<{
    reviewId: string;
    ready: boolean;
  } | null>(null);
  const lastConsumedEvent = useRef(0);
  const lastSnapshotRevision = useRef<{
    projectId: string;
    generation: number;
    etag: string;
  } | null>(null);

  useEffect(() => {
    lastSnapshotRevision.current = null;
    setPendingReviewNavigation(null);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    // Project snapshot is the new shared domain authority.  Legacy page Views
    // remain mounted during the migration, while this poller provides one
    // generation-aware source for all future selectors.
    return startProjectSnapshotPolling(id);
  }, [id, startProjectSnapshotPolling]);

  useEffect(() => {
    if (
      !id ||
      snapshotRevision.projectId !== id ||
      snapshotRevision.generation === null ||
      !snapshotRevision.etag
    )
      return;
    const current = {
      projectId: id,
      generation: snapshotRevision.generation,
      etag: snapshotRevision.etag,
    };
    const previous = lastSnapshotRevision.current;
    lastSnapshotRevision.current = current;
    // The first successful Snapshot and the initial route Views are loaded in
    // parallel.  Treat that Snapshot as the baseline so it does not duplicate
    // the first-frame Header/Plan requests.
    if (!previous || previous.projectId !== id) return;
    if (
      previous.generation === current.generation &&
      previous.etag === current.etag
    )
      return;
    void revalidateLoadedViews(id).catch(() => undefined);
  }, [id, revalidateLoadedViews, snapshotRevision]);

  useEffect(() => {
    if (!id) return;
    const stop = startFileReviewPolling(id);
    return () => {
      stop();
      const reviewStore = useFileProjectReviewStore.getState();
      if (reviewStore.projectId === id) reviewStore.reset();
    };
  }, [id, startFileReviewPolling]);

  useEffect(() => {
    if (!id) return;
    const reviewStore = useReviewManifestStore.getState();
    reviewStore.bindFileProject(id);
    const poll = () => {
      void useReviewManifestStore
        .getState()
        .loadFileAuthorizations(id)
        .catch(() => undefined);
    };
    poll();
    const timer = window.setInterval(poll, 1_000);
    return () => {
      window.clearInterval(timer);
      const current = useReviewManifestStore.getState();
      if (current.projectId === id && current.transactionId === null)
        current.reset();
    };
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const sessionState = useCreatorSessionStore.getState();
    const switchingProject = sessionState.projectId !== id;
    lastConsumedEvent.current = switchingProject
      ? 0
      : sessionState.lastEventSeq;
    if (switchingProject) {
      useCreatorTaskViewStore.getState().reset();
      useCreatorInteractionStore.getState().reset();
      useAgentDockUiStore.getState().reset();
      useNavigationStore.getState().clear();
    }
    void Promise.all([
      loadHeader(id),
      loadPlan(id),
      bootstrap(id),
      refreshTasks(id),
    ]).catch(() => undefined);
    return () => disconnect();
  }, [bootstrap, disconnect, id, loadHeader, loadPlan, refreshTasks]);

  useEffect(() => {
    if (
      !id ||
      !sessionStatus ||
      sessionStatus === "IDLE" ||
      sessionStatus === "CANCELLED"
    )
      return;
    // Runtime Tasks are file-native and no longer emit the legacy bridge's
    // in-process progress callbacks to the browser.  Poll their durable heads
    // so both AgentDock tools and direct workbench commands expose QUEUED /
    // RUNNING progress while the blocking command request is still active.
    const timer = window.setInterval(() => {
      void refreshTasks(id).catch(() => undefined);
    }, 750);
    return () => window.clearInterval(timer);
  }, [id, refreshTasks, sessionStatus]);

  useEffect(() => {
    let panel: CreatorPanel = "other";
    if (pathname.includes("/workbench")) panel = "workbench";
    else if (pathname.includes("/plan")) panel = "plan";
    else if (pathname.includes("/assets")) panel = "assets";
    useCreatorInteractionStore.getState().setPanel(panel);
  }, [pathname]);

  useEffect(() => {
    const pendingEvents = events.filter(
      (event) => event.seq > lastConsumedEvent.current,
    );
    if (!pendingEvents.length) return;
    lastConsumedEvent.current = pendingEvents.at(-1)!.seq;
    pendingEvents.forEach((event) =>
      useCreatorTaskViewStore.getState().consumeEvent(event),
    );
    if (
      pendingEvents.some(
        (event) =>
          event.type === "workspace.head_changed" ||
          event.type === "workspace.manual_edit_committed",
      )
    ) {
      void loadHeader(id);
    }
    const completedReviewIds = pendingEvents
      .filter((event) => event.type === "agent.run.completed")
      .flatMap((event) => reviewIdsFromEvent(event.data));
    const completedReviewId = completedReviewIds.at(-1);
    if (completedReviewId) {
      setPendingReviewNavigation({ reviewId: completedReviewId, ready: false });
      const reviewStore = useFileProjectReviewStore.getState();
      void reviewStore
        .pollOnce(id)
        // If this call joined a request that began before run completion, the
        // second poll is guaranteed to observe the completed Review boundary.
        .then(() => useFileProjectReviewStore.getState().pollOnce(id))
        .then(() =>
          setPendingReviewNavigation((current) =>
            current?.reviewId === completedReviewId
              ? { ...current, ready: true }
              : current,
          ),
        )
        .catch(() => undefined);
    }
    if (
      pendingEvents.some(
        (event) =>
          event.type.startsWith("task.") ||
          event.type.startsWith("task_") ||
          isSubagentLifecycleEvent(event.type),
      )
    ) {
      void refreshTasks(id);
    }
    if (
      pendingEvents.some(
        (event) =>
          event.type.startsWith("session.") ||
          event.type.startsWith("task.") ||
          event.type.startsWith("task_") ||
          isSubagentLifecycleEvent(event.type) ||
          isFileAgentLifecycleEvent(event.type),
      )
    ) {
      void refreshSession().catch(() => undefined);
    }
    // File-native Review is synchronized independently by
    // useFileProjectReviewStore.  Runtime events can refresh Session/Task
    // projections, but must never be interpreted as legacy Transaction IDs or
    // trigger requests to the removed Transaction/Review API.
  }, [events, id, loadHeader, refreshSession, refreshTasks]);

  useEffect(() => {
    if (
      !pendingReviewNavigation?.ready ||
      fileReviewSyncStatus !== "healthy" ||
      activeFileReview?.review_id !== pendingReviewNavigation.reviewId
    )
      return;
    setPendingReviewNavigation(null);
    const targets = reviewClipTargets(activeFileReview.operations);
    if (!targets.length) return;
    const [primary] = targets;
    void loadWorkbench(id, primary.unitId)
      .then(() => {
        const workspace = useWorkspaceViewStore.getState();
        targets.forEach(({ unitId, clipIds }) => {
          workspace.setClipHighlights(unitId, clipIds);
        });
        const targetPath = `/project/${id}/plan/unit/${encodeURIComponent(
          primary.unitId,
        )}/workbench`;
        if (!pathname.startsWith(targetPath)) router.push(targetPath);
      })
      .catch(() => undefined);
  }, [
    activeFileReview,
    fileReviewSyncStatus,
    id,
    loadWorkbench,
    pathname,
    pendingReviewNavigation,
    router,
  ]);

  // A background Header revalidation must not unmount the active route.  The
  // initial skeleton is only needed before the first authoritative Header is
  // available.  Transient background Header/Session failures keep the last
  // authoritative shell mounted so AgentDock and the active editor do not
  // disappear while the durable SSE connection catches up.
  if (!header) {
    return <LayoutSkeleton />;
  }

  return (
    <div
      data-project-shell
      data-top-nav-height="58"
      data-agent-status-bar-height="42"
      className="app-shell grid h-screen grid-rows-[58px_42px_minmax(0,1fr)]"
    >
      <TopNav />
      <AgentStatusBar />
      <div className="flex min-h-0 overflow-hidden">
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <ReturnBanner />
          <main
            data-creator-workspace-root
            key={pathname}
            className="panel-enter relative min-h-0 flex-1 overflow-hidden"
          >
            <Outlet />
          </main>
        </div>
        <AgentDock sidebar />
      </div>
      <SelectionToolbar />
    </div>
  );
}
