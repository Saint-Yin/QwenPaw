import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button, Input, Select, message } from "antd";
import {
  ArrowLeft,
  Check,
  ListVideo,
  PlayCircle,
  Scissors,
  Sparkles,
  Zap,
} from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import type {
  AiEditMaterialAsset,
  AiEditStoryboardPanel,
  AiEditTimelineClip,
  ArtifactVersionView,
  CreatorEvent,
  EditWorkbenchView,
  RefSearchItem,
  ViewEnvelope,
} from "@/contracts/creator";
import { useCreatorCommand } from "@/hooks/useCreatorCommand";
import {
  getArtifactVersionMediaUrl,
  getAssetVersionFrameUrl,
  getAssetVersionMediaUrl,
  getGeneratedMediaUrl,
  searchRefs,
} from "@/api/creator";
import { navigateToRefItem } from "@/routing/locators";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import { useWorkspaceViewStore } from "@/store/workspaceViewStore";
import { reviewGroupForArtifact } from "@/lib/artifactReview";
import { useDebouncedUnitFieldSave } from "@/hooks/useDebouncedUnitFieldSave";
import { projectJsonPointer } from "@/lib/projectJsonPointer";
import ArtifactVersionChips from "./ArtifactVersionChips";

const { TextArea } = Input;

const AGENT_RUN_LIFECYCLE_EVENTS = new Set([
  "agent.run.started",
  "agent.run.completed",
  "agent.run.failed",
  "agent.run.cancelled",
]);
const AGENTDOCK_RUN_ORIGINS = new Set([
  "agentdock_idle_goal",
  "agentdock_interrupt",
]);

function latestActiveAgentDockRun(
  events: CreatorEvent[],
): { runId: string; startedAt: string } | null {
  const active = new Map<
    string,
    { runId: string; startedAt: string; seq: number }
  >();
  events.forEach((event) => {
    const runId =
      typeof event.data.runId === "string" ? event.data.runId : null;
    if (!runId) return;
    if (event.type === "agent.run.started") {
      const origin =
        typeof event.data.origin === "string" ? event.data.origin : null;
      if (origin && AGENTDOCK_RUN_ORIGINS.has(origin)) {
        active.set(runId, { runId, startedAt: event.at, seq: event.seq });
      }
      return;
    }
    if (AGENT_RUN_LIFECYCLE_EVENTS.has(event.type)) active.delete(runId);
  });
  return (
    [...active.values()].sort((left, right) => right.seq - left.seq)[0] ?? null
  );
}

function ClipPreview({
  src,
  start,
  end,
  autoPlay = false,
}: {
  src: string;
  start: number;
  end: number;
  autoPlay?: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [muted, setMuted] = useState(true);
  const duration = Math.max(0.1, end - start);

  const seekToStartWhenOutsideClip = useCallback(
    (video: HTMLVideoElement) => {
      if (video.currentTime < start - 0.05 || video.currentTime >= end - 0.05) {
        video.currentTime = start;
        setProgress(0);
      }
    },
    [end, start],
  );

  const togglePlay = () => {
    const video = ref.current;
    if (!video) return;
    if (playing) {
      video.pause();
    } else {
      seekToStartWhenOutsideClip(video);
      void video.play();
    }
  };

  const toggleMute = () => {
    const video = ref.current;
    if (!video) return;
    video.muted = !muted;
    setMuted(!muted);
  };

  const seekToClientX = useCallback(
    (clientX: number) => {
      const bar = barRef.current;
      const video = ref.current;
      if (!bar || !video) return;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.min(
        1,
        Math.max(0, (clientX - rect.left) / rect.width),
      );
      video.currentTime = start + ratio * duration;
      setProgress(ratio);
    },
    [duration, start],
  );

  const onBarPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    ref.current?.pause();
    setDragging(true);
    seekToClientX(event.clientX);
  };

  const onBarPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragging) seekToClientX(event.clientX);
  };

  const onBarPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
    setDragging(false);
  };

  return (
    <div className="w-full bg-black" style={{ maxWidth: "400px" }}>
      <video
        ref={ref}
        src={`${src}#t=${start},${end}`}
        preload="metadata"
        autoPlay={autoPlay}
        muted={muted}
        playsInline
        data-clip-start={start}
        data-clip-end={end}
        onClick={togglePlay}
        onLoadedMetadata={() => {
          const video = ref.current;
          if (video) {
            video.currentTime = start;
            setProgress(0);
          }
        }}
        onCanPlay={() => {
          const video = ref.current;
          if (video) seekToStartWhenOutsideClip(video);
        }}
        onTimeUpdate={() => {
          const video = ref.current;
          if (!video || dragging) return;
          if (video.currentTime < start - 0.05) {
            video.currentTime = start;
            setProgress(0);
            return;
          }
          if (video.currentTime >= end) {
            video.pause();
            video.currentTime = start;
            setPlaying(false);
            setProgress(0);
          } else {
            setProgress(Math.max(0, (video.currentTime - start) / duration));
          }
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        className="w-full"
        style={{ aspectRatio: "16/9", objectFit: "cover" }}
      />
      <div className="flex items-center gap-2 bg-black/80 px-2 py-1.5">
        <button
          type="button"
          onClick={togglePlay}
          className="shrink-0 text-white hover:text-white/70"
        >
          {playing ? (
            <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor">
              <rect x="1" y="1" width="3.5" height="9" rx="0.5" />
              <rect x="6.5" y="1" width="3.5" height="9" rx="0.5" />
            </svg>
          ) : (
            <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor">
              <polygon points="1,0.5 10.5,5.5 1,10.5" />
            </svg>
          )}
        </button>
        <button
          type="button"
          onClick={toggleMute}
          className="shrink-0 text-white hover:text-white/70"
          aria-label={muted ? "取消静音" : "静音"}
        >
          {muted ? (
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <line x1="23" y1="9" x2="17" y2="15" />
              <line x1="17" y1="9" x2="23" y2="15" />
            </svg>
          ) : (
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
          )}
        </button>
        <div
          ref={barRef}
          className="group relative flex h-3 flex-1 cursor-pointer touch-none items-center"
          onPointerDown={onBarPointerDown}
          onPointerMove={onBarPointerMove}
          onPointerUp={onBarPointerUp}
          onPointerCancel={onBarPointerUp}
        >
          <div className="absolute inset-x-0 h-1 rounded bg-white/30" />
          <div
            className="absolute left-0 h-1 rounded bg-white"
            style={{ width: `${progress * 100}%` }}
          />
          <div
            className="absolute h-2.5 w-2.5 rounded-full bg-white shadow transition-transform group-hover:scale-110"
            style={{
              left: `calc(${progress * 100}% - 5px)`,
              opacity: dragging ? 1 : undefined,
            }}
          />
          {dragging && (
            <div
              className="pointer-events-none absolute bottom-full mb-1.5 -translate-x-1/2 rounded bg-black/80 px-1.5 py-0.5 text-[10px] tabular-nums text-white"
              style={{ left: `${progress * 100}%` }}
            >
              {(start + progress * duration).toFixed(1)}s
            </div>
          )}
        </div>
        <span className="shrink-0 tabular-nums text-[10px] text-white/60">
          {start}s – {end}s
        </span>
      </div>
    </div>
  );
}

function StoryboardClipPreview({
  active,
  videoSrc,
  imageSrc,
  start,
  end,
  label,
  eager,
  onActivate,
  onShowKeyframe,
}: {
  active: boolean;
  videoSrc: string;
  imageSrc: string | null;
  start: number;
  end: number;
  label: string;
  eager: boolean;
  onActivate: () => void;
  onShowKeyframe: () => void;
}) {
  if (active) {
    return (
      <div className="relative bg-black">
        <ClipPreview src={videoSrc} start={start} end={end} autoPlay />
        <button
          type="button"
          aria-label={`显示关键帧 ${label}`}
          onClick={onShowKeyframe}
          className="absolute right-2 top-2 rounded bg-black/70 px-2 py-1 text-[10px] font-medium text-white shadow hover:bg-black/85"
        >
          返回关键帧
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      aria-label={`播放分镜片段 ${label}`}
      onClick={onActivate}
      className="group relative block w-full overflow-hidden bg-black text-left"
      style={{ aspectRatio: "16/9" }}
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={`${label} 关键帧`}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          className="h-full w-full object-cover"
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-xs text-white/50">
          点击加载片段预览
        </span>
      )}
      <span className="absolute inset-0 flex items-center justify-center bg-black/10 transition-colors group-hover:bg-black/25">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-black/65 text-white shadow-lg transition-transform group-hover:scale-105">
          <PlayCircle className="h-5 w-5" />
        </span>
      </span>
      <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-[10px] tabular-nums text-white">
        {start}s – {end}s
      </span>
    </button>
  );
}

function Panel({
  title,
  badge,
  children,
  className,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] ${
        className ?? ""
      }`}
    >
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5">
        <h4 className="text-xs font-bold text-[var(--color-text-secondary)]">
          {title}
        </h4>
        {badge}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function arrayValue<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function unitDisplayName(unit: EditWorkbenchView["unit"]): string {
  return unit.title
    ? `${String(unit.number).padStart(2, "0")} ${unit.title}`
    : `剪辑单元 ${String(unit.number).padStart(2, "0")}`;
}

function currentVersion(
  versions: ArtifactVersionView[],
): ArtifactVersionView | null {
  return versions.find((version) => version.selected) ?? null;
}

function materialId(asset: AiEditMaterialAsset, index: number): string {
  return String(asset.id || `material-${index + 1}`);
}

function materialName(asset: AiEditMaterialAsset, index: number): string {
  return String(asset.name || asset.id || `素材 ${index + 1}`);
}

function materialUrl(asset: AiEditMaterialAsset): string | null {
  return typeof asset.url === "string" && asset.url
    ? getGeneratedMediaUrl(asset.url)
    : null;
}

export default function AiEditWorkbench({
  projectId,
  envelope,
  view,
  reload,
  focusVersion,
  reviewFocus,
  sectionNumber = 1,
  sectionTitle = "",
  materialReferenceOptions,
  onBack = () => undefined,
}: {
  projectId: string;
  envelope: ViewEnvelope<EditWorkbenchView>;
  view: EditWorkbenchView;
  reload: () => Promise<void>;
  focusVersion?: string | null;
  reviewFocus?: "storyboard" | "video" | null;
  sectionNumber?: number;
  sectionTitle?: string;
  materialReferenceOptions?: RefSearchItem[];
  onBack?: () => void;
}) {
  const { submit, submitting } = useCreatorCommand(projectId, envelope, reload);
  const stopping = useCreatorSessionStore((state) => state.stopping);
  const agentRunEvents = useCreatorSessionStore(
    useShallow((state) =>
      state.events.filter((event) =>
        AGENT_RUN_LIFECYCLE_EVENTS.has(event.type),
      ),
    ),
  );
  const tasks = useCreatorTaskViewStore((state) => state.tasks);
  const refreshTasks = useCreatorTaskViewStore((state) => state.refresh);
  const manifest = useReviewManifestStore((state) => state.manifest);
  const decideReview = useReviewManifestStore((state) => state.decide);
  const plan = view.plan;
  const timeline = arrayValue<AiEditTimelineClip>(plan?.timeline);
  const storyboard = arrayValue<AiEditStoryboardPanel>(plan?.storyboard);
  const materialAssets = arrayValue<AiEditMaterialAsset>(view.material_assets);
  const videoVersions = arrayValue<ArtifactVersionView>(view.videoVersions);
  const selectedVideo = currentVersion(videoVersions);
  const [viewedVideoId, setViewedVideoId] = useState<string | null>(null);
  const [goal, setGoal] = useState(view.goal || "");
  const [activeAction, setActiveAction] = useState<
    "plan" | "execute" | "full" | null
  >(null);
  const [autoExecute, setAutoExecute] = useState(false);
  const [completionFlash, setCompletionFlash] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [progressBarVisible, setProgressBarVisible] = useState(false);
  const progressBarHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  type ExecutionLogEntry = {
    index: number;
    title: string;
    start: number;
    end: number;
  };
  const [executionLog, setExecutionLog] = useState<ExecutionLogEntry[]>([]);
  const prevExecuteRunningRef = useRef(false);
  const prevPlanRunningRef = useRef(false);
  const prevClipIndexRef = useRef(-1);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [activePreviewPanelId, setActivePreviewPanelId] = useState<
    string | null
  >(null);
  const [pendingRanges, setPendingRanges] = useState<Array<{
    clipId: string;
    start: number;
    end: number;
  }> | null>(null);
  const [refOptions, setRefOptions] = useState<RefSearchItem[]>(
    materialReferenceOptions ?? view.resolvedRefs,
  );
  const [loadingRefs, setLoadingRefs] = useState(false);
  const timingDraftsRef = useRef<
    Record<string, { start: number; end: number }>
  >({});
  const rangeInFlightRef = useRef(false);
  const prevTimelineRef = useRef<
    Map<string, { start: number; end: number; fp: string }>
  >(new Map());
  const [changedClips, setChangedClips] = useState<
    Map<string, { oldStart: number; oldEnd: number } | null>
  >(new Map());
  const changedFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const prevUnitIdForChangeRef = useRef(view.unit.id);
  const clipHighlights = useWorkspaceViewStore(
    (state) => state.clipHighlights[view.unit.id],
  );
  const clipStateKey = `${view.unit.id}|${timeline
    .map((c) => {
      const os = c.overlay_copy;
      return `${c.clip_id}:${c.start}:${c.end}:${os?.text ?? ""}:${
        os?.vibe ?? ""
      }:${os?.appear_at ?? ""}:${os?.duration ?? ""}`;
    })
    .join("|")}`;

  const { schedule: scheduleUnitField } = useDebouncedUnitFieldSave<string>(
    (field, value) =>
      submit(
        "SET_UNIT_TEXT",
        `unit:${view.unit.id}`,
        { field, value },
        view.unit.targetVersion,
      ),
  );

  useEffect(() => setGoal(view.goal || ""), [view.goal]);
  useEffect(() => {
    setViewedVideoId(null);
    setActivePreviewPanelId(null);
    timingDraftsRef.current = {};
    // Reset the local history/timing draft only when the workbench Unit changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.unit.id]);
  useEffect(() => {
    const isUnitSwitch = prevUnitIdForChangeRef.current !== view.unit.id;
    prevUnitIdForChangeRef.current = view.unit.id;
    if (isUnitSwitch) {
      setChangedClips(new Map());
      if (changedFlashTimerRef.current) {
        clearTimeout(changedFlashTimerRef.current);
        changedFlashTimerRef.current = null;
      }
    } else {
      const prevMap = prevTimelineRef.current;
      const newChanges = new Map<
        string,
        { oldStart: number; oldEnd: number } | null
      >();
      for (const clip of timeline) {
        const prev = prevMap.get(clip.clip_id);
        if (prev) {
          const os = clip.overlay_copy;
          const currentFp = `${clip.start}:${clip.end}:${os?.text ?? ""}:${
            os?.vibe ?? ""
          }:${os?.appear_at ?? ""}:${os?.duration ?? ""}`;
          if (prev.fp !== currentFp) {
            const timingChanged =
              Math.abs(prev.start - clip.start) > 0.04 ||
              Math.abs(prev.end - clip.end) > 0.04;
            newChanges.set(
              clip.clip_id,
              timingChanged ? { oldStart: prev.start, oldEnd: prev.end } : null,
            );
          }
        }
      }
      if (newChanges.size > 0) {
        setChangedClips(newChanges);
        if (changedFlashTimerRef.current)
          clearTimeout(changedFlashTimerRef.current);
        changedFlashTimerRef.current = setTimeout(
          () => setChangedClips(new Map()),
          3500,
        );
      }
    }
    const newMap = new Map<
      string,
      { start: number; end: number; fp: string }
    >();
    for (const clip of timeline) {
      const os = clip.overlay_copy;
      const fp = `${clip.start}:${clip.end}:${os?.text ?? ""}:${
        os?.vibe ?? ""
      }:${os?.appear_at ?? ""}:${os?.duration ?? ""}`;
      newMap.set(clip.clip_id, { start: clip.start, end: clip.end, fp });
    }
    prevTimelineRef.current = newMap;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipStateKey]);
  useEffect(
    () => () => {
      if (changedFlashTimerRef.current)
        clearTimeout(changedFlashTimerRef.current);
    },
    [],
  );
  useEffect(() => {
    if (!clipHighlights?.length) return;
    const unitId = view.unit.id;
    setChangedClips(new Map(clipHighlights.map((clipId) => [clipId, null])));
    if (changedFlashTimerRef.current)
      clearTimeout(changedFlashTimerRef.current);
    changedFlashTimerRef.current = setTimeout(
      () => setChangedClips(new Map()),
      5000,
    );
    useWorkspaceViewStore.getState().clearClipHighlights(unitId);
  }, [clipHighlights, view.unit.id]);
  useEffect(() => {
    if (changedClips.size === 0) return;
    const firstClipId = changedClips.keys().next().value;
    if (!firstClipId) return;
    requestAnimationFrame(() => {
      const target = Array.from(
        document.querySelectorAll<HTMLElement>("[data-clip-panel-id]"),
      ).find((element) => element.dataset.clipPanelId === firstClipId);
      target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, [changedClips]);
  useEffect(() => {
    if (
      focusVersion &&
      videoVersions.some((version) => version.id === focusVersion)
    )
      setViewedVideoId(focusVersion);
  }, [focusVersion, videoVersions]);
  useEffect(() => {
    setRefOptions((current) => {
      const byRef = new Map(current.map((item) => [item.ref, item]));
      materialReferenceOptions?.forEach((item) => byRef.set(item.ref, item));
      view.resolvedRefs.forEach((item) => byRef.set(item.ref, item));
      return [...byRef.values()];
    });
  }, [materialReferenceOptions, view.resolvedRefs]);

  const effectiveVideoId =
    viewedVideoId ?? selectedVideo?.id ?? videoVersions.at(-1)?.id ?? null;
  const viewedVideo =
    videoVersions.find((version) => version.id === effectiveVideoId) ?? null;
  const unitTasks = tasks.filter(
    (task) => task.targetRef === `unit:${view.unit.id}`,
  );
  const activeAgentDockRun = useMemo(
    () => latestActiveAgentDockRun(agentRunEvents),
    [agentRunEvents],
  );
  const planTaskRunning = unitTasks.some(
    (task) =>
      task.kind === "ai_edit_plan" &&
      ["QUEUED", "RUNNING"].includes(task.status),
  );
  const executeTaskRunning = unitTasks.some(
    (task) =>
      task.kind === "ai_edit_execute" &&
      ["QUEUED", "RUNNING"].includes(task.status),
  );
  const agentDockExecutionObserved =
    activeAgentDockRun != null &&
    unitTasks.some(
      (task) =>
        task.kind === "ai_edit_execute" &&
        task.createdAt != null &&
        Date.parse(task.createdAt) >= Date.parse(activeAgentDockRun.startedAt),
    );
  const agentDockThinkingRunning =
    activeAgentDockRun != null &&
    !executeTaskRunning &&
    !agentDockExecutionObserved;
  const agentDockPostExecute =
    activeAgentDockRun != null &&
    !executeTaskRunning &&
    agentDockExecutionObserved;
  const thinkingRunning = planTaskRunning || agentDockThinkingRunning;
  const executeTaskProgress =
    unitTasks.find(
      (task) =>
        task.kind === "ai_edit_execute" &&
        ["QUEUED", "RUNNING"].includes(task.status),
    )?.progress ?? null;
  const processingClipIndex =
    executeTaskRunning && executeTaskProgress != null && timeline.length > 0
      ? Math.min(
          Math.floor(executeTaskProgress * timeline.length),
          timeline.length - 1,
        )
      : -1;

  const shouldShowProgressBar =
    planTaskRunning ||
    executeTaskRunning ||
    autoExecute ||
    completionFlash ||
    reloading ||
    agentDockPostExecute ||
    changedClips.size > 0;
  useEffect(() => {
    if (stopping) {
      if (progressBarHideTimerRef.current)
        clearTimeout(progressBarHideTimerRef.current);
      setProgressBarVisible(false);
      return;
    }
    if (shouldShowProgressBar) {
      if (progressBarHideTimerRef.current) {
        clearTimeout(progressBarHideTimerRef.current);
        progressBarHideTimerRef.current = null;
      }
      setProgressBarVisible(true);
    } else {
      progressBarHideTimerRef.current = setTimeout(
        () => setProgressBarVisible(false),
        500,
      );
    }
    return () => {
      if (progressBarHideTimerRef.current)
        clearTimeout(progressBarHideTimerRef.current);
    };
  }, [shouldShowProgressBar, stopping]);

  useEffect(() => {
    if (
      activeAction == null &&
      !autoExecute &&
      !thinkingRunning &&
      !executeTaskRunning
    )
      return;
    const poll = () => {
      void refreshTasks(projectId).catch(() => undefined);
    };
    poll();
    const timer = window.setInterval(poll, 500);
    return () => window.clearInterval(timer);
  }, [
    activeAction,
    autoExecute,
    executeTaskRunning,
    projectId,
    refreshTasks,
    thinkingRunning,
  ]);

  useEffect(() => {
    if (prevPlanRunningRef.current && !planTaskRunning) {
      void reload();
    }
    prevPlanRunningRef.current = planTaskRunning;
  }, [planTaskRunning, reload]);

  useEffect(() => {
    if (
      !autoExecute ||
      planTaskRunning ||
      executeTaskRunning ||
      !view.planVersion?.id
    )
      return;
    setAutoExecute(false);
    setActiveAction("execute");
    void submit(
      "EXECUTE_EDIT",
      `unit:${view.unit.id}`,
      { planVersionId: view.planVersion.id },
      view.unit.targetVersion,
    ).finally(() => setActiveAction(null));
  }, [
    autoExecute,
    executeTaskRunning,
    planTaskRunning,
    submit,
    view.planVersion,
    view.unit.id,
    view.unit.targetVersion,
  ]);

  useLayoutEffect(() => {
    if (
      prevExecuteRunningRef.current &&
      !executeTaskRunning &&
      !planTaskRunning &&
      !autoExecute
    ) {
      setCompletionFlash(true);
      setReloading(true);
      void reload().finally(() => setReloading(false));
      const timer = setTimeout(() => setCompletionFlash(false), 600);
      return () => clearTimeout(timer);
    }
    prevExecuteRunningRef.current = executeTaskRunning;
  }, [autoExecute, executeTaskRunning, planTaskRunning, reload]);

  useEffect(() => {
    if (!executeTaskRunning) {
      if (prevClipIndexRef.current >= 0) {
        const clip = timeline[prevClipIndexRef.current];
        const panel =
          storyboard.find((item) => item.clip_id === clip?.clip_id) ??
          storyboard[prevClipIndexRef.current];
        if (clip) {
          setExecutionLog((current) =>
            current.some((entry) => entry.index === prevClipIndexRef.current)
              ? current
              : [
                  ...current,
                  {
                    index: prevClipIndexRef.current,
                    title:
                      panel?.title ?? `片段 ${prevClipIndexRef.current + 1}`,
                    start: clip.start,
                    end: clip.end,
                  },
                ],
          );
        }
      }
      prevClipIndexRef.current = -1;
      return;
    }
    if (processingClipIndex < 0) return;
    if (prevClipIndexRef.current === -1) {
      setExecutionLog([]);
    } else if (processingClipIndex > prevClipIndexRef.current) {
      const previousIndex = prevClipIndexRef.current;
      const clip = timeline[previousIndex];
      const panel =
        storyboard.find((item) => item.clip_id === clip?.clip_id) ??
        storyboard[previousIndex];
      if (clip) {
        setExecutionLog((current) => [
          ...current,
          {
            index: previousIndex,
            title: panel?.title ?? `片段 ${previousIndex + 1}`,
            start: clip.start,
            end: clip.end,
          },
        ]);
      }
    }
    prevClipIndexRef.current = processingClipIndex;
  }, [executeTaskRunning, processingClipIndex, storyboard, timeline]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [executionLog.length]);

  const storyboardImageUrl =
    view.storyboard_image_url || plan?.storyboard_image_url || null;
  const editDuration = timeline.length
    ? Math.round(
        timeline.reduce(
          (sum, clip) => sum + Math.max(0, clip.end - clip.start),
          0,
        ),
      )
    : view.unit.duration;

  const selectArtifact = (version: ArtifactVersionView) =>
    submit(
      "SELECT_ARTIFACT_VERSION",
      `unit:${view.unit.id}`,
      {
        slotId: version.slotId,
        artifactVersionId: version.artifactVersionId,
        artifactRef: version.sourceRef,
      },
      view.unit.targetVersion,
    );

  const acceptArtifact = async (version: ArtifactVersionView) => {
    const group = reviewGroupForArtifact(manifest, version);
    if (group?.decision === "PENDING") {
      await decideReview(group.id, {
        decisionToken: group.decisionToken,
        decision: "ACCEPT",
      });
      message.success("已接受该版本，current 已切换");
      await reload();
      return;
    }
    await selectArtifact(version);
  };

  const undoArtifact = async (version: ArtifactVersionView) => {
    const group = reviewGroupForArtifact(
      useReviewManifestStore.getState().manifest,
      version,
    );
    if (group?.decision !== "PENDING") return;
    await decideReview(group.id, {
      decisionToken: group.decisionToken,
      decision: "REJECT",
    });
    message.success("已撤销该版本");
    await reload();
  };

  const buildEditPlan = async () => {
    setActiveAction("plan");
    try {
      const result = await submit(
        "BUILD_EDIT_PLAN",
        `unit:${view.unit.id}`,
        {},
        view.unit.targetVersion,
      );
      if (result) timingDraftsRef.current = {};
    } finally {
      setActiveAction(null);
    }
  };

  const runFullPipeline = async () => {
    setAutoExecute(true);
    setActiveAction("full");
    try {
      const result = await submit(
        "BUILD_EDIT_PLAN",
        `unit:${view.unit.id}`,
        {},
        view.unit.targetVersion,
      );
      if (result) {
        timingDraftsRef.current = {};
      } else {
        setAutoExecute(false);
      }
    } finally {
      setActiveAction(null);
    }
  };

  const updateClipTiming = (
    clip: AiEditTimelineClip,
    index: number,
    field: "start" | "end",
    raw: string,
  ) => {
    const value = Number.parseFloat(raw);
    if (!Number.isFinite(value) || value < 0) return;
    const draft = timingDraftsRef.current[clip.clip_id] ?? {
      start: clip.start,
      end: clip.end,
    };
    let start = draft.start;
    let end = draft.end;
    if (field === "start") {
      const previous = timeline[index - 1];
      const previousEnd = previous
        ? timingDraftsRef.current[previous.clip_id]?.end ?? previous.end
        : view.previousUnitLastClipEnd ?? 0;
      start = Math.max(value, previousEnd);
    } else {
      const next = timeline[index + 1];
      const nextStart = next
        ? timingDraftsRef.current[next.clip_id]?.start ?? next.start
        : view.nextUnitFirstClipStart ?? undefined;
      end = nextStart == null ? value : Math.min(value, nextStart);
    }
    if (start >= end) return;
    timingDraftsRef.current[clip.clip_id] = { start, end };
  };

  const confirmTimeline = () => {
    const ranges = timeline.flatMap((clip) => {
      const draft = timingDraftsRef.current[clip.clip_id];
      if (!draft || (draft.start === clip.start && draft.end === clip.end))
        return [];
      return [{ clipId: clip.clip_id, start: draft.start, end: draft.end }];
    });
    if (ranges.length === 0) {
      message.info("时间线没有待保存修改");
      return;
    }
    setPendingRanges(ranges);
  };

  useEffect(() => {
    if (pendingRanges == null || submitting || rangeInFlightRef.current) return;
    if (pendingRanges.length === 0) {
      timingDraftsRef.current = {};
      setPendingRanges(null);
      message.success("时间线已保存");
      return;
    }
    const range = pendingRanges[0];
    rangeInFlightRef.current = true;
    void submit(
      "SET_EDIT_CLIP_RANGE",
      `unit:${view.unit.id}`,
      { clipId: range.clipId, start: range.start, end: range.end },
      view.unit.targetVersion,
    ).then((result) => {
      rangeInFlightRef.current = false;
      setPendingRanges((current) =>
        result && current ? current.slice(1) : null,
      );
    });
  }, [
    pendingRanges,
    submitting,
    submit,
    view.unit.id,
    view.unit.targetVersion,
  ]);

  const updateClipOs = (
    clip: AiEditTimelineClip,
    patch: Record<string, unknown>,
  ) =>
    submit(
      "SET_EDIT_CLIP_OS",
      `unit:${view.unit.id}`,
      {
        clipId: clip.clip_id,
        text: clip.overlay_copy?.text || "",
        vibe: clip.overlay_copy?.vibe || "chill",
        appear_at: clip.overlay_copy?.appear_at ?? 0,
        ...(clip.overlay_copy?.duration == null
          ? {}
          : { duration: clip.overlay_copy.duration }),
        ...patch,
      },
      view.unit.targetVersion,
    );

  const loadReferenceOptions = async () => {
    if (materialReferenceOptions) return;
    if (loadingRefs) return;
    setLoadingRefs(true);
    try {
      const result = await searchRefs(projectId, "", ["asset"], 100);
      setRefOptions((current) => {
        const byRef = new Map(current.map((item) => [item.ref, item]));
        (result.items || []).forEach((item) => byRef.set(item.ref, item));
        return [...byRef.values()];
      });
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoadingRefs(false);
    }
  };

  const materialOptions = useMemo(
    () =>
      refOptions
        .filter((item) => !("mediaType" in item) || item.mediaType === "video")
        .map((item) => ({ value: item.ref, label: item.name })),
    [refOptions],
  );

  const changeMaterials = (next: string[]) => {
    const current = view.unit.materialRefs;
    const added = next.find((ref) => !current.includes(ref));
    if (added) {
      void submit(
        "BIND_REFERENCE",
        `unit:${view.unit.id}`,
        {
          field: "sources",
          referenceSet: "unit",
          sourceRef: added,
        },
        view.unit.targetVersion,
      );
      return;
    }
    const removed = current.find((ref) => !next.includes(ref));
    if (removed) {
      void submit(
        "UNBIND_REFERENCE",
        `unit:${view.unit.id}`,
        {
          field: "sources",
          referenceSet: "unit",
          sourceRef: removed,
        },
        view.unit.targetVersion,
      );
    }
  };

  const jumpToMaterial = (asset: AiEditMaterialAsset) => {
    const id = String(asset.id || "");
    const target = view.resolvedRefs.find(
      (item) => item.logicalAssetId === id || item.ref.includes(id),
    );
    if (target) navigateToRefItem(projectId, target);
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[var(--color-bg-layout)]">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-5 py-3 backdrop-blur">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            className="icon-button shrink-0"
            aria-label="返回视频方案"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </button>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
              视频方案 /{" "}
              {`${String(sectionNumber).padStart(2, "0")} ${sectionTitle}`} /{" "}
              {unitDisplayName(view.unit)} / AI 剪辑工作台
            </h2>
            <p className="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]">
              基于上传视频素材做 VLM 理解、关键帧分镜、剪辑决策和成片执行。
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="small"
            icon={<ListVideo className="h-3 w-3" />}
            loading={activeAction === "plan" || planTaskRunning}
            disabled={planTaskRunning || executeTaskRunning || autoExecute}
            onClick={() => void buildEditPlan()}
            className="!text-xs"
          >
            生成方案
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<Scissors className="h-3 w-3" />}
            loading={
              activeAction === "full" ||
              activeAction === "execute" ||
              planTaskRunning ||
              executeTaskRunning ||
              autoExecute
            }
            disabled={planTaskRunning || executeTaskRunning || autoExecute}
            onClick={() => void runFullPipeline()}
            className="!text-xs"
          >
            一键AI剪辑
          </Button>
        </div>
      </div>

      {progressBarVisible &&
        (() => {
          const isDone = completionFlash || reloading || changedClips.size > 0;
          const isPlanPhase =
            planTaskRunning &&
            !executeTaskRunning &&
            !agentDockPostExecute &&
            !isDone;
          const progressLabel = executeTaskRunning
            ? executeTaskProgress != null && executeTaskProgress > 0
              ? `AI 执行剪接 ${Math.round(executeTaskProgress * 100)}%`
              : "AI 执行剪接…"
            : agentDockPostExecute
            ? "AI 确认成果中…"
            : isDone
            ? "完成"
            : "AI 生成方案中…";
          const executeFill =
            isDone || agentDockPostExecute
              ? 100
              : executeTaskRunning
              ? 40 + (executeTaskProgress ?? 0) * 60
              : 0;
          return (
            <div className="shrink-0 border-b border-[var(--color-border)] px-5 py-2.5">
              <div className="mb-1.5 flex items-center justify-between">
                <span
                  className={`flex items-center gap-1.5 text-[11px] font-semibold transition-colors ${
                    isDone
                      ? "text-[var(--color-success)]"
                      : "text-[var(--color-accent)]"
                  }`}
                >
                  {isDone ? (
                    <Check className="h-3 w-3" />
                  ) : executeTaskRunning ? (
                    <Zap className="h-3 w-3 animate-pulse" />
                  ) : (
                    <Sparkles className="h-3 w-3 animate-pulse" />
                  )}
                  {progressLabel}
                </span>
              </div>
              <div className="relative h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-primary)]">
                {isPlanPhase ? (
                  <div
                    className="absolute inset-y-0 left-0 overflow-hidden"
                    style={{ width: "40%" }}
                  >
                    <div className="absolute inset-y-0 left-0 w-full rounded-full bg-[var(--color-accent)] [animation:plan-progress_25s_ease-out_forwards]" />
                  </div>
                ) : (
                  <div
                    className="absolute inset-y-0 left-0 rounded-full bg-[var(--color-accent)] transition-[width] duration-500"
                    style={{ width: `${executeFill}%` }}
                  />
                )}
                {agentDockPostExecute &&
                  !completionFlash &&
                  !reloading &&
                  changedClips.size === 0 && (
                    <div className="absolute inset-y-0 left-0 w-2/5 bg-white/20 [animation:slide-progress_1.4s_linear_infinite]" />
                  )}
              </div>
            </div>
          );
        })()}

      {(executeTaskRunning || completionFlash) && (
        <div className="max-h-28 shrink-0 space-y-1 overflow-y-auto border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]/40 px-5 py-2">
          {executionLog.map((entry) => (
            <div
              key={entry.index}
              className="flex items-center gap-2 text-[11px]"
            >
              <Check className="h-3 w-3 shrink-0 text-[var(--color-success)]" />
              <span className="font-medium text-[var(--color-text-primary)]">
                #{entry.index + 1} {entry.title}
              </span>
              <span className="tabular-nums text-[var(--color-text-tertiary)]">
                {entry.start.toFixed(1)}s → {entry.end.toFixed(1)}s
              </span>
            </div>
          ))}
          {executeTaskRunning &&
            processingClipIndex >= 0 &&
            (() => {
              const clip = timeline[processingClipIndex];
              const panel =
                storyboard.find((item) => item.clip_id === clip?.clip_id) ??
                storyboard[processingClipIndex];
              return (
                <div className="flex items-center gap-2 text-[11px]">
                  <Zap className="h-3 w-3 shrink-0 animate-pulse text-[var(--color-accent)]" />
                  <span className="font-medium text-[var(--color-text-primary)]">
                    #{processingClipIndex + 1}{" "}
                    {panel?.title ?? `片段 ${processingClipIndex + 1}`}
                  </span>
                  <span className="text-[var(--color-text-tertiary)]">
                    处理中…
                  </span>
                </div>
              );
            })()}
          <div ref={logEndRef} />
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <Panel title="剪辑目标">
            <div
              data-creator-field={`unit:${view.unit.id}/goal`}
              data-creator-path={projectJsonPointer(
                "production",
                "units_by_id",
                view.unit.id,
                "intent",
              )}
              data-creator-field-label="剪辑目标"
            >
              <TextArea
                value={goal}
                onChange={(event) => {
                  setGoal(event.target.value);
                  scheduleUnitField("goal", event.target.value);
                }}
                autoSize={{ minRows: 3, maxRows: 8 }}
                placeholder="这支 AI 剪辑成片要表达什么、偏什么节奏、保留哪些重点…"
                className="!rounded-lg !border-[var(--color-border)] !bg-[var(--color-bg-secondary)] !text-xs"
              />
            </div>
          </Panel>

          <div className="scroll-mt-4">
            <Panel
              title="VLM 关键帧分镜"
              className={reviewFocus === "storyboard" ? "review-flash" : ""}
              badge={
                plan ? (
                  <span className="text-[11px] font-medium text-[var(--color-text-tertiary)]">
                    {storyboard.length} panels
                  </span>
                ) : null
              }
            >
              <div className="space-y-3">
                {storyboard.length ? (
                  <>
                    <div className="flex flex-wrap gap-3">
                      {storyboard.map((panel, panelIndex) => {
                        const clip = panel.clip_id
                          ? timeline.find(
                              (item) => item.clip_id === panel.clip_id,
                            )
                          : timeline[panelIndex];
                        const clipIndex = clip ? timeline.indexOf(clip) : -1;
                        const assetIndex = materialAssets.findIndex(
                          (item) =>
                            String(item.id || "") === panel.source_asset_id,
                        );
                        const asset =
                          assetIndex >= 0
                            ? materialAssets[assetIndex]
                            : undefined;
                        const videoSrc = clip?.asset_version_id
                          ? getAssetVersionMediaUrl(clip.asset_version_id)
                          : clip?.source_url
                          ? getGeneratedMediaUrl(clip.source_url)
                          : asset
                          ? materialUrl(asset)
                          : null;
                        const clipStart = clip?.start ?? 0;
                        const clipEnd = clip?.end ?? clipStart + 5;
                        const frameTimestamp = Math.max(
                          clipStart,
                          Math.min(
                            Number.isFinite(panel.timestamp)
                              ? panel.timestamp
                              : clipStart,
                            Math.max(clipStart, clipEnd - 0.1),
                          ),
                        );
                        const keyframeSrc = panel.image_url
                          ? getGeneratedMediaUrl(panel.image_url)
                          : clip?.asset_version_id
                          ? getAssetVersionFrameUrl(
                              clip.asset_version_id,
                              frameTimestamp,
                            )
                          : null;
                        const previousClip =
                          clipIndex > 0 ? timeline[clipIndex - 1] : undefined;
                        const nextClip =
                          clipIndex >= 0 && clipIndex < timeline.length - 1
                            ? timeline[clipIndex + 1]
                            : undefined;
                        const isClipChanged = Boolean(
                          clip && changedClips.has(clip.clip_id),
                        );
                        const isProcessing = clipIndex === processingClipIndex;
                        const isClipDone =
                          executeTaskRunning &&
                          processingClipIndex >= 0 &&
                          clipIndex >= 0 &&
                          clipIndex < processingClipIndex;
                        const isClipPending =
                          executeTaskRunning &&
                          processingClipIndex >= 0 &&
                          clipIndex > processingClipIndex;
                        const clipChangedInfo = clip
                          ? changedClips.get(clip.clip_id)
                          : undefined;
                        return (
                          <div
                            key={panel.panel_id}
                            data-clip-panel-id={clip?.clip_id ?? ""}
                            className={`relative w-[400px] shrink-0 overflow-hidden rounded-lg border transition-all duration-500 ${
                              isClipChanged
                                ? "border-[var(--color-accent)] shadow-[0_0_0_3px_var(--color-accent-soft)]"
                                : isClipDone
                                ? "border-[var(--color-success)]/40 bg-[var(--color-success-soft)]"
                                : isProcessing
                                ? "animate-pulse border-[var(--color-accent)]/50"
                                : isClipPending
                                ? "border-[var(--color-border)] opacity-50"
                                : "border-[var(--color-border)]"
                            }`}
                          >
                            {isClipDone && (
                              <div className="absolute right-2 top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-success)] shadow-sm">
                                <Check className="h-3 w-3 text-white" />
                              </div>
                            )}
                            {isProcessing && (
                              <div className="absolute right-2 top-2 z-10 rounded-full bg-[var(--color-accent)] px-1.5 py-0.5 text-[9px] font-semibold text-white">
                                处理中
                              </div>
                            )}
                            {videoSrc ? (
                              <StoryboardClipPreview
                                key={`${panel.panel_id}_${clipStart}_${clipEnd}`}
                                active={activePreviewPanelId === panel.panel_id}
                                videoSrc={videoSrc}
                                imageSrc={keyframeSrc}
                                start={clipStart}
                                end={clipEnd}
                                label={`#${panel.order} ${panel.title}`}
                                eager={panelIndex < 2}
                                onActivate={() =>
                                  setActivePreviewPanelId(panel.panel_id)
                                }
                                onShowKeyframe={() =>
                                  setActivePreviewPanelId(null)
                                }
                              />
                            ) : (
                              <div
                                className="flex items-center justify-center bg-[var(--color-bg-secondary)] text-xs text-[var(--color-text-tertiary)]"
                                style={{ aspectRatio: "16/9" }}
                              >
                                无预览
                              </div>
                            )}
                            <div className="p-2">
                              <p
                                data-creator-field={`unit:${view.unit.id}/editPlan/storyboard/panel:${panel.panel_id}/title`}
                                data-creator-path={projectJsonPointer(
                                  "production",
                                  "units_by_id",
                                  view.unit.id,
                                  "plan",
                                  "storyboard",
                                  "items",
                                  panel.panel_id,
                                  "title",
                                )}
                                data-creator-field-label={`VLM 分镜 ${panel.order} · 标题`}
                                className="text-[11px] font-semibold text-[var(--color-text-primary)]"
                              >
                                #{panel.order} {panel.title}
                              </p>
                              <p
                                data-creator-field={`unit:${view.unit.id}/editPlan/storyboard/panel:${panel.panel_id}/description`}
                                data-creator-path={projectJsonPointer(
                                  "production",
                                  "units_by_id",
                                  view.unit.id,
                                  "plan",
                                  "storyboard",
                                  "items",
                                  panel.panel_id,
                                  "description",
                                )}
                                data-creator-field-label={`VLM 分镜 ${panel.order} · 描述`}
                                className="mt-0.5 text-[10px] leading-4 text-[var(--color-text-secondary)]"
                              >
                                {panel.description}
                              </p>
                              <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[10px] text-[var(--color-text-tertiary)]">
                                视频第
                                <input
                                  key={`sb_s_${panel.panel_id}_${clipStart}`}
                                  type="number"
                                  step="0.5"
                                  min={
                                    previousClip?.end ??
                                    view.previousUnitLastClipEnd ??
                                    0
                                  }
                                  defaultValue={clipStart}
                                  data-creator-field={`unit:${
                                    view.unit.id
                                  }/editPlan/timeline/clip:${
                                    clip?.clip_id ?? panel.clip_id
                                  }/sourceInSeconds`}
                                  data-creator-path={
                                    clip
                                      ? projectJsonPointer(
                                          "production",
                                          "units_by_id",
                                          view.unit.id,
                                          "plan",
                                          "timeline",
                                          "items",
                                          clip.clip_id,
                                          "source_in_seconds",
                                        )
                                      : undefined
                                  }
                                  data-creator-field-label={`剪辑片段 ${
                                    clipIndex >= 0
                                      ? clipIndex + 1
                                      : panelIndex + 1
                                  } · 入点`}
                                  onBlur={(event) => {
                                    if (clip)
                                      updateClipTiming(
                                        clip,
                                        clipIndex >= 0 ? clipIndex : panelIndex,
                                        "start",
                                        event.target.value,
                                      );
                                  }}
                                  className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1 py-0.5 text-center text-[10px] font-semibold text-[var(--color-text-primary)]"
                                />
                                {(previousClip?.end ??
                                  (clipIndex <= 0
                                    ? view.previousUnitLastClipEnd ?? 0
                                    : undefined)) != null && (
                                  <span className="text-[9px] text-[var(--color-text-tertiary)] opacity-60">
                                    (最早{" "}
                                    {previousClip?.end ??
                                      view.previousUnitLastClipEnd ??
                                      0}
                                    s)
                                  </span>
                                )}
                                到
                                <input
                                  key={`sb_e_${panel.panel_id}_${clipEnd}`}
                                  type="number"
                                  step="0.5"
                                  min="0"
                                  max={
                                    nextClip?.start ??
                                    view.nextUnitFirstClipStart ??
                                    undefined
                                  }
                                  defaultValue={clipEnd}
                                  data-creator-field={`unit:${
                                    view.unit.id
                                  }/editPlan/timeline/clip:${
                                    clip?.clip_id ?? panel.clip_id
                                  }/sourceOutSeconds`}
                                  data-creator-path={
                                    clip
                                      ? projectJsonPointer(
                                          "production",
                                          "units_by_id",
                                          view.unit.id,
                                          "plan",
                                          "timeline",
                                          "items",
                                          clip.clip_id,
                                          "source_out_seconds",
                                        )
                                      : undefined
                                  }
                                  data-creator-field-label={`剪辑片段 ${
                                    clipIndex >= 0
                                      ? clipIndex + 1
                                      : panelIndex + 1
                                  } · 出点`}
                                  onBlur={(event) => {
                                    if (clip)
                                      updateClipTiming(
                                        clip,
                                        clipIndex >= 0 ? clipIndex : panelIndex,
                                        "end",
                                        event.target.value,
                                      );
                                  }}
                                  className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1 py-0.5 text-center text-[10px] font-semibold text-[var(--color-text-primary)]"
                                />
                                秒
                                {(nextClip?.start ??
                                  view.nextUnitFirstClipStart) != null && (
                                  <span className="text-[9px] text-[var(--color-text-tertiary)] opacity-60">
                                    (最長{" "}
                                    {nextClip?.start ??
                                      view.nextUnitFirstClipStart}
                                    s)
                                  </span>
                                )}
                              </div>
                              {isClipChanged && (
                                <div className="mt-1.5 inline-flex items-center gap-1 rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--color-accent)]">
                                  {clipChangedInfo ? (
                                    <>
                                      <span className="line-through opacity-60">
                                        {clipChangedInfo.oldStart}s–
                                        {clipChangedInfo.oldEnd}s
                                      </span>
                                      <span>→</span>
                                      <span>
                                        {clipStart}s–{clipEnd}s
                                      </span>
                                    </>
                                  ) : (
                                    "已更新"
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="flex justify-end pt-1">
                      <button
                        type="button"
                        disabled={
                          activeAction === "execute" ||
                          executeTaskRunning ||
                          pendingRanges != null
                        }
                        onClick={confirmTimeline}
                        className="rounded border border-transparent bg-[var(--color-accent)] px-3 py-1 text-[11px] font-medium text-white hover:opacity-80 disabled:opacity-40"
                      >
                        {pendingRanges != null ? "保存中…" : "确认时间轴"}
                      </button>
                    </div>
                  </>
                ) : storyboardImageUrl ? (
                  <img
                    src={getGeneratedMediaUrl(storyboardImageUrl)}
                    alt="AI 剪辑关键帧分镜"
                    className="w-full rounded-lg border border-[var(--color-border)]"
                  />
                ) : (
                  <div className="flex h-44 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                    尚未生成关键帧分镜
                  </div>
                )}
              </div>
            </Panel>
          </div>

          <Panel
            title={`剪辑时间线（${timeline.length}）`}
            badge={
              executeTaskRunning && processingClipIndex >= 0 ? (
                <span className="text-[11px] font-medium text-[var(--color-accent)]">
                  正在处理第 {processingClipIndex + 1} 段 / 共 {timeline.length}{" "}
                  段
                </span>
              ) : null
            }
          >
            {timeline.length ? (
              <div className="space-y-2">
                {timeline.map((clip, index) => {
                  const clipPanel =
                    storyboard.find(
                      (panel) =>
                        panel.clip_id && panel.clip_id === clip.clip_id,
                    ) || storyboard[index];
                  const rowDone =
                    executeTaskRunning &&
                    processingClipIndex >= 0 &&
                    index < processingClipIndex;
                  const rowProcessing = index === processingClipIndex;
                  const rowPending =
                    executeTaskRunning &&
                    processingClipIndex >= 0 &&
                    index > processingClipIndex;
                  return (
                    <div
                      key={clip.clip_id || index}
                      className={`grid gap-2 rounded-lg border p-3 transition-all duration-500 md:grid-cols-[80px_minmax(0,1fr)] ${
                        changedClips.has(clip.clip_id)
                          ? "border-[var(--color-accent)]/50 bg-[var(--color-accent-soft)]"
                          : rowDone
                          ? "border-[var(--color-success)]/40 bg-[var(--color-success-soft)]"
                          : rowProcessing
                          ? "animate-pulse border-[var(--color-accent)]/50 bg-[var(--color-bg-secondary)]/50"
                          : rowPending
                          ? "border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 opacity-50"
                          : "border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50"
                      }`}
                    >
                      <div
                        className={`flex items-center gap-1 text-xs font-bold ${
                          rowDone
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-accent)]"
                        }`}
                      >
                        {rowDone ? <Check className="h-3 w-3" /> : null}#
                        {index + 1}
                      </div>
                      <div className="min-w-0">
                        <p
                          data-creator-field={
                            clipPanel
                              ? `unit:${view.unit.id}/editPlan/storyboard/panel:${clipPanel.panel_id}/title`
                              : `unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/label`
                          }
                          data-creator-path={
                            clipPanel
                              ? projectJsonPointer(
                                  "production",
                                  "units_by_id",
                                  view.unit.id,
                                  "plan",
                                  "storyboard",
                                  "items",
                                  clipPanel.panel_id,
                                  "title",
                                )
                              : undefined
                          }
                          data-creator-field-label={`剪辑片段 ${
                            index + 1
                          } · 标题`}
                          className="truncate text-xs font-semibold text-[var(--color-text-primary)]"
                        >
                          {clipPanel?.title || `片段 ${index + 1}`}
                        </p>
                        <p
                          data-creator-field={`unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/reason`}
                          data-creator-path={projectJsonPointer(
                            "production",
                            "units_by_id",
                            view.unit.id,
                            "plan",
                            "timeline",
                            "items",
                            clip.clip_id,
                            "reason",
                          )}
                          data-creator-field-label={`剪辑片段 ${
                            index + 1
                          } · 选择理由`}
                          className="mt-1 text-[11px] leading-4 text-[var(--color-text-secondary)]"
                        >
                          {clip.reason || "VLM 选择该片段用于叙事推进。"}
                        </p>
                        {clip.overlay_copy?.kind === "pet_os" && (
                          <div className="mb-3 mt-2">
                            <div className="relative inline-block">
                              <div className="flex items-center gap-1 rounded-2xl border-2 border-black bg-yellow-50 px-2.5 py-1.5 shadow-[2px_2px_0_#000]">
                                <input
                                  key={`overlay_copy_${clip.clip_id}_${clip.overlay_copy.text}`}
                                  type="text"
                                  defaultValue={clip.overlay_copy.text}
                                  data-creator-field={`unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/overlay/text`}
                                  data-creator-path={projectJsonPointer(
                                    "production",
                                    "units_by_id",
                                    view.unit.id,
                                    "plan",
                                    "timeline",
                                    "items",
                                    clip.clip_id,
                                    "overlay",
                                    "text",
                                  )}
                                  data-creator-field-label={`剪辑片段 ${
                                    index + 1
                                  } · 画面文案`}
                                  ref={(element) => {
                                    if (element) {
                                      element.style.width = "0";
                                      element.style.width = `${Math.max(
                                        80,
                                        element.scrollWidth,
                                      )}px`;
                                    }
                                  }}
                                  onInput={(event) => {
                                    const element =
                                      event.target as HTMLInputElement;
                                    element.style.width = "0";
                                    element.style.width = `${Math.max(
                                      80,
                                      element.scrollWidth,
                                    )}px`;
                                  }}
                                  onBlur={(event) => {
                                    const value = event.target.value.trim();
                                    if (
                                      value !== clip.overlay_copy?.text.trim()
                                    )
                                      void updateClipOs(clip, { text: value });
                                  }}
                                  className="bg-transparent text-[11px] font-bold leading-4 text-black outline-none placeholder:font-normal placeholder:text-gray-400"
                                  placeholder="输入猫咪独白…"
                                />
                              </div>
                              <div
                                style={{
                                  position: "absolute",
                                  bottom: -9,
                                  left: 14,
                                  width: 0,
                                  height: 0,
                                  borderLeft: "7px solid transparent",
                                  borderRight: "7px solid transparent",
                                  borderTop: "9px solid black",
                                }}
                              />
                              <div
                                style={{
                                  position: "absolute",
                                  bottom: -6,
                                  left: 16,
                                  width: 0,
                                  height: 0,
                                  borderLeft: "5px solid transparent",
                                  borderRight: "5px solid transparent",
                                  borderTop: "7px solid #fefce8",
                                }}
                              />
                            </div>
                            <div className="mt-3 text-base leading-none">
                              {clip.overlay_copy.vibe === "action"
                                ? "😾"
                                : clip.overlay_copy.vibe === "surprise"
                                ? "🙀"
                                : clip.overlay_copy.vibe === "curious"
                                ? "🐱"
                                : "😺"}
                            </div>
                          </div>
                        )}
                        {clip.overlay_copy?.kind === "interview_summary" && (
                          <div
                            data-creator-field={`unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/overlay/text`}
                            data-creator-path={projectJsonPointer(
                              "production",
                              "units_by_id",
                              view.unit.id,
                              "plan",
                              "timeline",
                              "items",
                              clip.clip_id,
                              "overlay",
                              "text",
                            )}
                            data-creator-field-label={`剪辑片段 ${
                              index + 1
                            } · 画面文案`}
                            className="mt-2 rounded-md border border-[var(--color-border)] bg-black/70 px-2.5 py-1.5 text-center text-[11px] font-semibold text-white"
                          >
                            {clip.overlay_copy.text}
                          </div>
                        )}
                        {clip.overlay_copy?.kind === "pet_os" && (
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--color-text-tertiary)]">
                            <label className="flex items-center gap-1">
                              {`OS出现自第${
                                "一二三四五六七八九十".split("")[index] ??
                                index + 1
                              }分段`}
                              <input
                                key={`os_at_${clip.clip_id}_${
                                  clip.overlay_copy?.appear_at ?? 0
                                }`}
                                type="number"
                                step="0.5"
                                min="0"
                                defaultValue={clip.overlay_copy?.appear_at ?? 0}
                                data-creator-field={`unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/overlay/appearAt`}
                                data-creator-path={projectJsonPointer(
                                  "production",
                                  "units_by_id",
                                  view.unit.id,
                                  "plan",
                                  "timeline",
                                  "items",
                                  clip.clip_id,
                                  "overlay",
                                  "appear_at",
                                )}
                                data-creator-field-label={`剪辑片段 ${
                                  index + 1
                                } · 画面文案出现时间`}
                                onBlur={(event) => {
                                  const value = Number.parseFloat(
                                    event.target.value,
                                  );
                                  if (
                                    Number.isFinite(value) &&
                                    value >= 0 &&
                                    value !==
                                      (clip.overlay_copy?.appear_at ?? 0)
                                  ) {
                                    const remaining = Math.max(
                                      0.5,
                                      clip.duration - value,
                                    );
                                    void updateClipOs(clip, {
                                      appear_at: value,
                                      duration: Math.min(
                                        clip.overlay_copy?.duration ??
                                          remaining,
                                        remaining,
                                      ),
                                    });
                                  }
                                }}
                                className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1.5 py-0.5 text-center text-[11px] font-semibold text-[var(--color-text-primary)]"
                              />
                              s
                            </label>
                            <label className="flex items-center gap-1">
                              OS时长
                              <input
                                key={`os_dur_${clip.clip_id}_${
                                  clip.overlay_copy?.duration ?? ""
                                }`}
                                type="number"
                                step="0.5"
                                min="0.5"
                                defaultValue={clip.overlay_copy?.duration ?? ""}
                                placeholder="自动"
                                data-creator-field={`unit:${view.unit.id}/editPlan/timeline/clip:${clip.clip_id}/overlay/duration`}
                                data-creator-path={projectJsonPointer(
                                  "production",
                                  "units_by_id",
                                  view.unit.id,
                                  "plan",
                                  "timeline",
                                  "items",
                                  clip.clip_id,
                                  "overlay",
                                  "duration",
                                )}
                                data-creator-field-label={`剪辑片段 ${
                                  index + 1
                                } · 画面文案时长`}
                                onBlur={(event) => {
                                  const raw = event.target.value.trim();
                                  const value =
                                    raw === "" ? null : Number.parseFloat(raw);
                                  if (
                                    value === null ||
                                    (Number.isFinite(value) && value > 0)
                                  ) {
                                    if (
                                      value !==
                                      (clip.overlay_copy?.duration ?? null)
                                    )
                                      void updateClipOs(clip, {
                                        duration: value,
                                      });
                                  }
                                }}
                                className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-1.5 py-0.5 text-center text-[11px] font-semibold text-[var(--color-text-primary)] placeholder:font-normal placeholder:text-[var(--color-text-tertiary)]"
                              />
                              s
                            </label>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                <div className="flex justify-end pt-1">
                  <button
                    type="button"
                    disabled={
                      activeAction === "execute" ||
                      executeTaskRunning ||
                      pendingRanges != null
                    }
                    onClick={confirmTimeline}
                    className="rounded border border-transparent bg-[var(--color-accent)] px-3 py-1 text-[11px] font-medium text-white hover:opacity-80 disabled:opacity-40"
                  >
                    {pendingRanges != null ? "保存中…" : "确认时间线"}
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-[var(--color-text-tertiary)]">
                生成剪辑方案后会显示素材取舍、时间段和转场建议。
              </p>
            )}
          </Panel>
        </div>

        <aside className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <div className="scroll-mt-4">
            <Panel
              title="剪辑成片"
              className={reviewFocus === "video" ? "review-flash" : ""}
              badge={
                <ArtifactVersionChips
                  versions={videoVersions}
                  currentId={selectedVideo?.id}
                  viewingId={effectiveVideoId}
                  focusVersion={focusVersion}
                  onView={setViewedVideoId}
                />
              }
            >
              <div className="space-y-2">
                {viewedVideo ? (
                  <video
                    key={viewedVideo.artifactVersionId}
                    src={getArtifactVersionMediaUrl(
                      viewedVideo.artifactVersionId,
                    )}
                    controls
                    preload="metadata"
                    playsInline
                    aria-label="剪辑成片预览"
                    className="w-full rounded-lg border border-[var(--color-border)]"
                  />
                ) : (
                  <div className="flex h-36 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                    <PlayCircle className="h-6 w-6" />
                    尚未执行剪辑
                  </div>
                )}
                {viewedVideo &&
                  (reviewGroupForArtifact(manifest, viewedVideo)?.decision ===
                    "PENDING" ||
                    !viewedVideo.selected) && (
                    <div className="flex items-center justify-between rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] px-2.5 py-1.5">
                      <span className="text-[11px] text-[var(--color-warning)]">
                        {reviewGroupForArtifact(manifest, viewedVideo)
                          ?.decision === "PENDING"
                          ? "该剪辑版本待审阅"
                          : "可切换为当前剪辑版本"}
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          size="small"
                          type="primary"
                          onClick={() => void acceptArtifact(viewedVideo)}
                          className="!text-[11px]"
                        >
                          接受
                        </Button>
                        {reviewGroupForArtifact(manifest, viewedVideo)
                          ?.decision === "PENDING" && (
                          <Button
                            size="small"
                            onClick={() => void undoArtifact(viewedVideo)}
                            className="!text-[11px]"
                          >
                            撤销
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
              </div>
            </Panel>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "素材", value: `${materialAssets.length}` },
              { label: "时长", value: `${editDuration}s` },
              { label: "模型", value: "VLM" },
            ].map((cell) => (
              <div
                key={cell.label}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-center"
              >
                <p className="text-[10px] text-[var(--color-text-tertiary)]">
                  {cell.label}
                </p>
                <p className="mt-1 text-xs font-semibold text-[var(--color-text-primary)]">
                  {cell.value}
                </p>
              </div>
            ))}
          </div>

          <Panel title="剪辑素材">
            <Select
              size="small"
              mode="multiple"
              className="!w-full"
              value={view.unit.materialRefs}
              onChange={changeMaterials}
              onDropdownVisibleChange={(open) => {
                if (open) void loadReferenceOptions();
              }}
              loading={!materialReferenceOptions && loadingRefs}
              placeholder="选择要参与剪辑的视频素材"
              options={materialOptions}
            />
            <div className="mt-3 space-y-1.5">
              {materialAssets.length === 0 ? (
                <p className="text-xs text-[var(--color-text-tertiary)]">
                  暂无视频素材。请在新建项目处选择文件夹或上传视频。
                </p>
              ) : (
                materialAssets.map((asset, index) => (
                  <button
                    key={materialId(asset, index)}
                    type="button"
                    onClick={() => jumpToMaterial(asset)}
                    className="flex w-full items-center gap-2 rounded-lg bg-[var(--color-bg-secondary)]/60 px-2.5 py-1.5 text-left transition-colors hover:bg-[var(--color-bg-secondary)]"
                  >
                    <span className="shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-1.5 py-px text-[10px] text-[var(--color-text-tertiary)]">
                      VID
                    </span>
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--color-accent)]">
                      @{materialName(asset, index)}
                    </span>
                  </button>
                ))
              )}
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
