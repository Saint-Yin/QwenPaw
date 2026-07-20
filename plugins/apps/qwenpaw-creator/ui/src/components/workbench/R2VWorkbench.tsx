import { useEffect, useState } from "react";
import { Button, Input, Select, Tooltip, message } from "antd";
import {
  AlertTriangle,
  ArrowLeft,
  Clapperboard,
  Image as ImageIcon,
  Video,
  Wand2,
} from "lucide-react";
import type {
  ArtifactVersionView,
  CreatorCommandType,
  R2VWorkbenchView,
  RefSearchItem,
  ViewEnvelope,
} from "@/contracts/creator";
import { useCreatorCommand } from "@/hooks/useCreatorCommand";
import {
  getArtifactVersionMediaUrl,
  getGeneratedMediaUrl,
  searchRefs,
} from "@/api/creator";
import { navigateToRefItem } from "@/routing/locators";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import { reviewGroupForArtifact } from "@/lib/artifactReview";
import { useDebouncedUnitFieldSave } from "@/hooks/useDebouncedUnitFieldSave";
import ShotList from "./ShotList";
import ArtifactVersionChips from "./ArtifactVersionChips";
import { projectJsonPointer } from "@/lib/projectJsonPointer";

const { TextArea } = Input;

type ReferenceField = "scene" | "characters" | "props" | "sources";
type ReferenceSet = "storyboard" | "video" | "storyboard_and_video";

const FIELD_LABEL: Record<ReferenceField, string> = {
  scene: "场景",
  characters: "角色",
  props: "道具",
  sources: "素材",
};

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

function unitDisplayName(unit: R2VWorkbenchView["unit"]): string {
  return unit.title
    ? `${String(unit.number).padStart(2, "0")} ${unit.title}`
    : `生成单元 ${String(unit.number).padStart(2, "0")}`;
}

function currentVersion(
  versions: ArtifactVersionView[],
  selectedId?: string | null,
): ArtifactVersionView | null {
  return (
    versions.find((version) => version.id === selectedId || version.selected) ??
    null
  );
}

function referenceSetOf(
  view: R2VWorkbenchView,
  sourceRef: string,
): ReferenceSet {
  const sets =
    view.inputReferenceBindings.find((item) => item.sourceRef === sourceRef)
      ?.referenceSets ?? [];
  if (sets.includes("storyboard") && sets.includes("video"))
    return "storyboard_and_video";
  return sets[0] ?? "storyboard_and_video";
}

export default function R2VWorkbench({
  projectId,
  envelope,
  view,
  reload,
  focusVersion,
  reviewFocus,
  sectionNumber = 1,
  sectionTitle = "",
  sectionId,
  aspectRatio = "16:9",
  unitTerm = "生成单元",
  referenceOptions,
  onBack = () => undefined,
}: {
  projectId: string;
  envelope: ViewEnvelope<R2VWorkbenchView>;
  view: R2VWorkbenchView;
  reload: () => Promise<void>;
  focusVersion?: string | null;
  reviewFocus?: "storyboard" | "video" | null;
  sectionNumber?: number;
  sectionTitle?: string;
  sectionId?: string;
  aspectRatio?: string;
  unitTerm?: string;
  referenceOptions?: Partial<Record<ReferenceField, RefSearchItem[]>>;
  onBack?: () => void;
}) {
  const { submit } = useCreatorCommand(projectId, envelope, reload);
  const tasks = useCreatorTaskViewStore((state) => state.tasks);
  const refreshTasks = useCreatorTaskViewStore((state) => state.refresh);
  const manifest = useReviewManifestStore((state) => state.manifest);
  const decideReview = useReviewManifestStore((state) => state.decide);
  const [activeAction, setActiveAction] = useState<CreatorCommandType | null>(
    null,
  );
  const [storyboardPrompt, setStoryboardPrompt] = useState(
    view.storyboardPrompt || "",
  );
  const [videoPrompt, setVideoPrompt] = useState(view.videoPrompt || "");
  const selectedStoryboard = currentVersion(
    view.storyboardVersions,
    view.selectedStoryboardVersionId,
  );
  const selectedVideo = currentVersion(
    view.videoVersions,
    view.selectedVideoVersionId,
  );
  const [viewedSbId, setViewedSbId] = useState<string | null>(null);
  const [viewedVideoId, setViewedVideoId] = useState<string | null>(null);
  const [refOptions, setRefOptions] = useState<RefSearchItem[]>(
    view.resolvedRefs,
  );
  const [loadingRefs, setLoadingRefs] = useState(false);
  const { schedule: scheduleUnitField } = useDebouncedUnitFieldSave<string>(
    (field, value) =>
      submit(
        "SET_UNIT_TEXT",
        `unit:${view.unit.id}`,
        { field, value },
        view.unit.targetVersion,
      ),
  );

  useEffect(
    () => setStoryboardPrompt(view.storyboardPrompt || ""),
    [view.storyboardPrompt],
  );
  useEffect(() => setVideoPrompt(view.videoPrompt || ""), [view.videoPrompt]);
  useEffect(() => {
    setViewedSbId(null);
    setViewedVideoId(null);
    // Reset the local history-viewing state only when the workbench unit changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.unit.id]);
  useEffect(() => {
    if (!focusVersion) return;
    if (view.storyboardVersions.some((version) => version.id === focusVersion))
      setViewedSbId(focusVersion);
    if (view.videoVersions.some((version) => version.id === focusVersion))
      setViewedVideoId(focusVersion);
  }, [focusVersion, view.storyboardVersions, view.videoVersions]);
  useEffect(() => {
    setRefOptions((current) => {
      const byRef = new Map(current.map((item) => [item.ref, item]));
      view.resolvedRefs.forEach((item) => byRef.set(item.ref, item));
      return [...byRef.values()];
    });
  }, [view.resolvedRefs]);

  const effectiveSbId =
    viewedSbId ??
    selectedStoryboard?.id ??
    view.storyboardVersions.at(-1)?.id ??
    null;
  const effectiveVideoId =
    viewedVideoId ?? selectedVideo?.id ?? view.videoVersions.at(-1)?.id ?? null;
  const viewedStoryboard =
    view.storyboardVersions.find((version) => version.id === effectiveSbId) ??
    null;
  const viewedVideo =
    view.videoVersions.find((version) => version.id === effectiveVideoId) ??
    null;
  const videoTask = [...tasks]
    .filter(
      (task) =>
        task.kind === "r2v_generation" &&
        task.targetRef === `unit:${view.unit.id}`,
    )
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt || right.createdAt || "") -
        Date.parse(left.updatedAt || left.createdAt || ""),
    )[0];
  const videoGenerating =
    videoTask?.status === "RUNNING" || videoTask?.status === "QUEUED";
  const videoFailed =
    videoTask &&
    ["FAILED", "CANCELLED", "QUARANTINED"].includes(videoTask.status);
  const videoTaskMessage = (() => {
    if (!videoTask) return "";
    if (videoGenerating) return "任务已提交，等待最新状态";
    const detail =
      videoTask.error?.message ||
      videoTask.error?.detail ||
      videoTask.error?.code;
    return typeof detail === "string" && detail ? detail : "视频生成失败";
  })();
  const displayedStoryboardUrl = viewedStoryboard
    ? getArtifactVersionMediaUrl(viewedStoryboard.artifactVersionId)
    : view.unit.storyboardImageUrl
    ? getGeneratedMediaUrl(view.unit.storyboardImageUrl)
    : null;
  const totalDuration = view.unit.shots.length
    ? view.unit.shots.reduce((total, shot) => total + shot.duration, 0)
    : view.unit.duration;
  const overLimit = totalDuration > view.providerConstraints.maxDuration;
  const inputRefs = view.resolvedRefs;
  const refCount = view.videoInputRefs?.length ?? inputRefs.length;

  const bindingFor = (sourceRef: string) =>
    view.inputReferenceBindings.find((item) => item.sourceRef === sourceRef);
  const refsForField = (field: ReferenceField) => [
    ...new Set(
      view.inputReferenceBindings
        .filter((item) => item.field === field)
        .map((item) => item.sourceRef),
    ),
  ];
  const selectOptionsFor = (field: ReferenceField) => {
    const candidates = referenceOptions?.[field] ?? refOptions;
    const byRef = new Map(candidates.map((item) => [item.ref, item]));
    view.resolvedRefs
      .filter((item) => bindingFor(item.ref)?.field === field)
      .forEach((item) => byRef.set(item.ref, item));
    return [...byRef.values()].map((item) => ({
      value: item.ref,
      label: item.name,
    }));
  };

  const runAction = async (
    type: CreatorCommandType,
    args: Record<string, unknown> = {},
  ) => {
    setActiveAction(type);
    try {
      await submit(type, `unit:${view.unit.id}`, args, view.unit.targetVersion);
    } finally {
      setActiveAction(null);
    }
  };

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

  const loadReferenceOptions = async () => {
    if (referenceOptions) return;
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

  const bindReference = (field: ReferenceField, sourceRef: string) =>
    submit(
      "BIND_REFERENCE",
      `unit:${view.unit.id}`,
      { field, referenceSet: "storyboard_and_video", sourceRef },
      view.unit.targetVersion,
    );

  const unbindReference = (field: ReferenceField, sourceRef: string) =>
    submit(
      "UNBIND_REFERENCE",
      `unit:${view.unit.id}`,
      { field, referenceSet: referenceSetOf(view, sourceRef), sourceRef },
      view.unit.targetVersion,
    );

  const changeSingleReference = (field: ReferenceField, next?: string) => {
    const current = refsForField(field)[0];
    if (next) {
      if (next !== current) void bindReference(field, next);
    } else if (current) {
      void unbindReference(field, current);
    }
  };

  const changeMultipleReferences = (field: ReferenceField, next: string[]) => {
    const current = refsForField(field);
    const added = next.find((ref) => !current.includes(ref));
    if (added) {
      void bindReference(field, added);
      return;
    }
    const removed = current.find((ref) => !next.includes(ref));
    if (removed) void unbindReference(field, removed);
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
              {unitDisplayName(view.unit)} / 制作工作台
            </h2>
            <p className="mt-0.5 truncate text-xs text-[var(--color-text-secondary)]">
              {unitTerm}子界面，继承分镜、引用资产、模型输入包和审阅状态。
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="small"
            icon={<Wand2 className="h-3 w-3" />}
            loading={activeAction === "GENERATE_STORYBOARD_PROMPT"}
            onClick={() => void runAction("GENERATE_STORYBOARD_PROMPT")}
            className="!text-xs"
          >
            生成分镜 Prompt
          </Button>
          <Button
            size="small"
            icon={<ImageIcon className="h-3 w-3" />}
            loading={activeAction === "GENERATE_STORYBOARD_IMAGE"}
            onClick={() => void runAction("GENERATE_STORYBOARD_IMAGE")}
            className="!text-xs"
          >
            生成分镜图
          </Button>
          <Button
            size="small"
            icon={<Clapperboard className="h-3 w-3" />}
            loading={activeAction === "GENERATE_VIDEO_PROMPT"}
            onClick={() => void runAction("GENERATE_VIDEO_PROMPT")}
            className="!text-xs"
          >
            生成视频 Prompt
          </Button>
          <Tooltip
            title={
              view.blockers.length > 0
                ? `Agent 将在计划阶段校验：${view.blockers.join("；")}`
                : undefined
            }
          >
            <Button
              size="small"
              type="primary"
              icon={<Video className="h-3 w-3" />}
              loading={activeAction === "GENERATE_R2V_VIDEO" || videoGenerating}
              disabled={videoGenerating}
              onClick={() =>
                void runAction("GENERATE_R2V_VIDEO", {
                  storyboardArtifactVersionId:
                    selectedStoryboard?.artifactVersionId,
                })
              }
              className="!text-xs"
            >
              {videoGenerating ? "视频生成中" : "生成视频"}
            </Button>
          </Tooltip>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <Panel
            title={`Shot 列表（${view.unit.shots.length}）`}
            badge={
              <span
                className={`flex items-center gap-1 text-[11px] font-medium ${
                  overLimit
                    ? "text-[var(--color-danger)]"
                    : "text-[var(--color-text-tertiary)]"
                }`}
              >
                {overLimit && <AlertTriangle className="h-3 w-3" />}
                合计 {totalDuration}s / 上限{" "}
                {view.providerConstraints.maxDuration}s
              </span>
            }
          >
            <ShotList
              shots={view.unit.shots}
              unitId={view.unit.id}
              sectionId={sectionId}
              onUpsert={(shot) =>
                submit(
                  "UPSERT_SHOT",
                  `unit:${view.unit.id}`,
                  {
                    shot: {
                      id: shot.id,
                      description: shot.description,
                      camera: shot.camera,
                      framing: shot.framing,
                      cameraDescription: shot.cameraDescription,
                      dialogue: shot.dialogue,
                      duration: shot.duration,
                    },
                  },
                  view.unit.targetVersion,
                )
              }
              onDelete={(shot) =>
                submit("DELETE_SHOT", `shot:${shot.id}`, {}, shot.targetVersion)
              }
            />
          </Panel>

          <div className="scroll-mt-4">
            <Panel
              title="分镜Prompt与分镜图"
              className={reviewFocus === "storyboard" ? "review-flash" : ""}
              badge={
                <ArtifactVersionChips
                  versions={view.storyboardVersions}
                  currentId={selectedStoryboard?.id}
                  viewingId={effectiveSbId}
                  focusVersion={focusVersion}
                  onView={setViewedSbId}
                />
              }
            >
              <div className="space-y-3">
                {viewedStoryboard &&
                  (reviewGroupForArtifact(manifest, viewedStoryboard)
                    ?.decision === "PENDING" ||
                    !viewedStoryboard.selected) && (
                    <div className="flex items-center justify-between rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] px-2.5 py-1.5">
                      <span className="text-[11px] text-[var(--color-warning)]">
                        {reviewGroupForArtifact(manifest, viewedStoryboard)
                          ?.decision === "PENDING"
                          ? "该版本待审阅（待接受）"
                          : "可切换为当前分镜版本"}
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          size="small"
                          type="primary"
                          onClick={() => void acceptArtifact(viewedStoryboard)}
                          className="!text-[11px]"
                        >
                          接受
                        </Button>
                        {reviewGroupForArtifact(manifest, viewedStoryboard)
                          ?.decision === "PENDING" && (
                          <Button
                            size="small"
                            onClick={() => void undoArtifact(viewedStoryboard)}
                            className="!text-[11px]"
                          >
                            撤销
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                <div
                  data-creator-field={`unit:${view.unit.id}/storyboardPrompt`}
                  data-creator-path={projectJsonPointer(
                    "production",
                    "units_by_id",
                    view.unit.id,
                    "storyboard_prompt",
                  )}
                  data-creator-field-label={`${unitDisplayName(
                    view.unit,
                  )} · 分镜图 Prompt`}
                >
                  <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                    分镜图 Prompt
                  </p>
                  <TextArea
                    value={storyboardPrompt}
                    onChange={(event) => {
                      setStoryboardPrompt(event.target.value);
                      scheduleUnitField("storyboardPrompt", event.target.value);
                    }}
                    autoSize={{ minRows: 2, maxRows: 10 }}
                    placeholder="生成分镜 Prompt 后可在此编辑…"
                    className="!rounded-lg !border-[var(--color-border)] !bg-[var(--color-bg-secondary)] !text-xs"
                  />
                </div>
                {displayedStoryboardUrl ? (
                  <img
                    src={displayedStoryboardUrl}
                    alt="分镜图"
                    className="w-full rounded-lg border border-[var(--color-border)]"
                  />
                ) : (
                  <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                    尚无分镜图
                  </div>
                )}
                <div
                  data-creator-field={`unit:${view.unit.id}/videoPrompt`}
                  data-creator-path={projectJsonPointer(
                    "production",
                    "units_by_id",
                    view.unit.id,
                    "video_prompt",
                  )}
                  data-creator-field-label={`${unitDisplayName(
                    view.unit,
                  )} · 视频 Prompt`}
                >
                  <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                    视频 Prompt
                  </p>
                  <TextArea
                    value={videoPrompt}
                    onChange={(event) => {
                      setVideoPrompt(event.target.value);
                      scheduleUnitField("videoPrompt", event.target.value);
                    }}
                    autoSize={{ minRows: 2, maxRows: 10 }}
                    placeholder="生成视频 Prompt 后可在此编辑…"
                    className="!rounded-lg !border-[var(--color-border)] !bg-[var(--color-bg-secondary)] !text-xs"
                  />
                </div>
              </div>
            </Panel>
          </div>
        </div>

        <aside className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <div className="scroll-mt-4">
            <Panel
              title="视频结果"
              className={reviewFocus === "video" ? "review-flash" : ""}
              badge={
                <ArtifactVersionChips
                  versions={view.videoVersions}
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
                    className="w-full rounded-lg border border-[var(--color-border)]"
                  />
                ) : (
                  <div className="flex h-32 flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)]">
                    {videoGenerating ? (
                      <>
                        <span className="font-medium text-[var(--color-warning)]">
                          R2V 任务生成中…
                        </span>
                        <span>{videoTaskMessage}</span>
                        <Button
                          size="small"
                          onClick={() =>
                            void Promise.all([
                              refreshTasks(projectId),
                              reload(),
                            ])
                          }
                          className="!text-[11px]"
                        >
                          手动刷新
                        </Button>
                      </>
                    ) : videoFailed ? (
                      <span className="px-3 text-center text-[var(--color-danger)]">
                        {videoTaskMessage}
                      </span>
                    ) : (
                      "尚未生成视频"
                    )}
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
                          ? "该版本待审阅（待接受）"
                          : "可切换为当前视频版本"}
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
              { label: "时长", value: `${totalDuration}s` },
              { label: "画幅", value: aspectRatio },
              { label: "模型", value: "R2V" },
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

          <Panel title={`输入引用（${refCount}）`}>
            {inputRefs.length === 0 ? (
              <p className="text-xs text-[var(--color-text-tertiary)]">
                暂无引用资产。
              </p>
            ) : (
              <div className="space-y-1.5">
                {inputRefs.map((ref) => {
                  const field = bindingFor(ref.ref)?.field ?? "sources";
                  return (
                    <button
                      key={ref.ref}
                      type="button"
                      onClick={() => navigateToRefItem(projectId, ref)}
                      className="flex w-full items-center gap-2 rounded-lg bg-[var(--color-bg-secondary)]/60 px-2.5 py-1.5 text-left transition-colors hover:bg-[var(--color-bg-secondary)]"
                    >
                      <span className="shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-1.5 py-px text-[10px] text-[var(--color-text-tertiary)]">
                        {FIELD_LABEL[field]}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--color-accent)]">
                        @{ref.name}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </Panel>

          <Panel title="资产绑定">
            <div className="space-y-3">
              <div>
                <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  场景
                </p>
                <Select
                  size="small"
                  className="!w-full"
                  value={refsForField("scene")[0] || undefined}
                  onChange={(value) => changeSingleReference("scene", value)}
                  onDropdownVisibleChange={(open) => {
                    if (open) void loadReferenceOptions();
                  }}
                  loading={!referenceOptions && loadingRefs}
                  allowClear
                  placeholder="选择场景"
                  options={selectOptionsFor("scene")}
                />
              </div>
              <div>
                <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  角色
                </p>
                <Select
                  size="small"
                  mode="multiple"
                  className="!w-full"
                  value={refsForField("characters")}
                  onChange={(value) =>
                    changeMultipleReferences("characters", value)
                  }
                  onDropdownVisibleChange={(open) => {
                    if (open) void loadReferenceOptions();
                  }}
                  loading={!referenceOptions && loadingRefs}
                  placeholder="选择角色"
                  options={selectOptionsFor("characters")}
                />
              </div>
              <div>
                <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  道具
                </p>
                <Select
                  size="small"
                  mode="multiple"
                  className="!w-full"
                  value={refsForField("props")}
                  onChange={(value) => changeMultipleReferences("props", value)}
                  onDropdownVisibleChange={(open) => {
                    if (open) void loadReferenceOptions();
                  }}
                  loading={!referenceOptions && loadingRefs}
                  placeholder="选择道具"
                  options={selectOptionsFor("props")}
                />
              </div>
              <div>
                <p className="mb-1 text-[11px] font-medium text-[var(--color-text-tertiary)]">
                  素材
                </p>
                <Select
                  size="small"
                  mode="multiple"
                  className="!w-full"
                  value={refsForField("sources")}
                  onChange={(value) =>
                    changeMultipleReferences("sources", value)
                  }
                  onDropdownVisibleChange={(open) => {
                    if (open) void loadReferenceOptions();
                  }}
                  loading={!referenceOptions && loadingRefs}
                  placeholder="选择素材"
                  options={selectOptionsFor("sources")}
                />
              </div>
              {view.blockers.length > 0 && (
                <div className="rounded-lg border border-[var(--color-warning)]/25 bg-[var(--color-warning-soft)] px-2.5 py-2">
                  {view.blockers.slice(0, 4).map((blocker) => (
                    <p
                      key={blocker}
                      className="text-[11px] text-[var(--color-warning)]"
                    >
                      · {blocker}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
