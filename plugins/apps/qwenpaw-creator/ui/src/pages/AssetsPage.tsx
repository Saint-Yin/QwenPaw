import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Dropdown, Input, message, Modal, Tabs } from "antd";
import {
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Boxes, Paperclip, Sparkles } from "lucide-react";
import type {
  AssetDetailView,
  AssetLibraryView,
  IngestItemView,
  PresentationAssetView,
} from "@/contracts/creator";
import {
  getArtifactVersionMediaUrl,
  getAssetContentUrl,
  ingestAssetFile,
  ingestAssetValue,
} from "@/api/creator";
import { navigate, useParams, useSearchParams } from "@/routing/navigation";
import {
  presentationOf,
  useWorkspaceViewStore,
} from "@/store/workspaceViewStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import { useNavigationStore } from "@/store/navigationStore";
import { useCreatorCommand } from "@/hooks/useCreatorCommand";
import { taskErrorMessage, taskProgressPercent } from "@/lib/taskPresentation";
import PageSkeleton from "@/components/PageSkeleton";
import EmptyState from "@/components/EmptyState";
import AssetCard, {
  type AssetDisplayItem,
} from "@/components/assets/AssetCard";
import AssetInspector from "@/components/assets/AssetInspector";
import AssetDetailPanel, {
  type ReferenceImageOption,
} from "@/components/AssetDetailPanel";
import PageLoadError from "@/components/PageLoadError";

type AssetFilterKey =
  | "all"
  | "upload"
  | "subject_ref"
  | "env_ref"
  | "brand_constraint"
  | "understanding"
  | "generated"
  | "storyboard_image"
  | "generated_video"
  | "planned";

const FILTERS: Array<{
  key: AssetFilterKey;
  label: string;
  divider?: boolean;
}> = [
  { key: "all", label: "全部资产" },
  { key: "upload", label: "用户上传" },
  { key: "subject_ref", label: "主体参考" },
  { key: "env_ref", label: "环境参考" },
  { key: "brand_constraint", label: "品牌约束" },
  { key: "understanding", label: "理解资产" },
  { key: "generated", label: "生成资产" },
  { key: "storyboard_image", label: "分镜图", divider: true },
  { key: "generated_video", label: "影片片段" },
  { key: "planned", label: "待完善资产", divider: true },
];

type DetailKind = AssetDetailView["kind"];
type DetailAssetItem = AssetDetailView;

const DETAIL_TAB: Record<
  DetailKind,
  "characters" | "scenes" | "props" | "materials"
> = {
  character: "characters",
  scene: "scenes",
  prop: "props",
  material: "materials",
};

function scenarioCategoryLabel(key: AssetFilterKey, scenario?: string): string {
  if (key === "subject_ref")
    return scenario === "short_drama"
      ? "角色"
      : scenario === "video_edit"
      ? "主体素材"
      : "主体参考";
  if (key === "env_ref")
    return scenario === "short_drama"
      ? "场景"
      : scenario === "video_edit"
      ? "场景素材"
      : "环境参考";
  return FILTERS.find((item) => item.key === key)?.label || key;
}

function detailKindOf(asset: AssetDisplayItem): DetailKind | null {
  return asset.detail?.kind ?? null;
}

function replacePromptConfig(
  asset: DetailAssetItem,
  promptIndex: number,
  prompt: string,
  referenceImageUrls: string[],
): DetailAssetItem {
  const prompts = [...(asset.prompts || [])];
  const references = [...asset.referenceImageRefs];
  prompts[promptIndex] = prompt;
  references[promptIndex] = referenceImageUrls;
  return { ...asset, prompts, referenceImageRefs: references };
}

function useDebouncedValue(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debounced;
}

function refIdentity(
  sourceRef: string | null | undefined,
  scheme: "asset" | "artifact",
): { id: string; versionId: string } | null {
  const prefix = `${scheme}://`;
  if (!sourceRef?.startsWith(prefix)) return null;
  const [id, versionId] = sourceRef.slice(prefix.length).split("@", 2);
  return id && versionId ? { id, versionId } : null;
}

function normalizedMediaType(item: PresentationAssetView): string {
  const raw = String(
    item.mediaType || item.generatedKind || "",
  ).toLocaleLowerCase();
  if (
    item.generatedKind === "storyboard_image" ||
    raw.startsWith("image/") ||
    raw.includes("image") ||
    raw.includes("storyboard")
  )
    return "image";
  if (
    item.generatedKind === "unit_video" ||
    item.generatedKind === "section_video" ||
    raw.startsWith("video/") ||
    raw.includes("video")
  )
    return "video";
  if (raw.startsWith("audio/") || raw.includes("audio")) return "audio";
  if (raw.startsWith("text/")) return "text";
  if (raw === "url") return "url";
  if (raw.includes("document") || raw.includes("pdf")) return "doc";
  return raw || "other";
}

function toDisplay(
  projectId: string,
  item: PresentationAssetView,
  ingestItems: IngestItemView[],
): AssetDisplayItem {
  const selectedDetailVersionId = item.detail?.images[0]?.id;
  const sourceIdentity = refIdentity(item.sourceRef, "asset");
  const artifactIdentity = refIdentity(item.sourceRef, "artifact");
  const artifactVersionId =
    item.artifactVersionId ||
    artifactIdentity?.versionId ||
    (item.sourceRef?.startsWith("artifact://")
      ? selectedDetailVersionId
      : undefined);
  const assetVersionId =
    item.assetVersionId ||
    sourceIdentity?.versionId ||
    (item.sourceRef?.startsWith("asset://")
      ? selectedDetailVersionId
      : undefined);
  const versionId =
    assetVersionId || artifactVersionId || item.uiLocator.versionId;
  const isUpload = item.category === "upload";
  const mediaType = normalizedMediaType(item);
  const previewable = mediaType === "image" || mediaType === "video";
  const ingestItem = isUpload
    ? ingestItems.find(
        (entry) =>
          (assetVersionId && entry.assetVersionId === assetVersionId) ||
          (!assetVersionId &&
            entry.assetId === (sourceIdentity?.id || item.id)),
      )
    : undefined;
  const previewCandidate = !previewable
    ? undefined
    : artifactVersionId
    ? getArtifactVersionMediaUrl(artifactVersionId)
    : assetVersionId
    ? getAssetContentUrl(
        projectId,
        sourceIdentity?.id || item.id,
        assetVersionId,
      )
    : item.thumbnailUrl || item.url || undefined;
  const previewState =
    item.existence === "planned"
      ? "planned"
      : ingestItem && ingestItem.status !== "SUCCEEDED"
      ? ingestItem.status === "QUEUED" || ingestItem.status === "RUNNING"
        ? "processing"
        : "failed"
      : previewCandidate
      ? "ready"
      : "unavailable";
  const previewUrl = previewState === "ready" ? previewCandidate : undefined;
  const detail = item.detail
    ? {
        ...item.detail,
        primaryUrl: previewUrl || item.detail.primaryUrl,
        images: item.detail.images.map((image) => ({
          ...image,
          url:
            image.id === artifactVersionId
              ? getArtifactVersionMediaUrl(image.id)
              : image.id === assetVersionId
              ? getAssetContentUrl(
                  projectId,
                  sourceIdentity?.id || item.id,
                  image.id,
                )
              : image.url,
        })),
      }
    : undefined;
  return {
    id: item.id,
    versionId,
    name: item.name,
    category: item.category,
    mediaType,
    previewUrl,
    previewState,
    sourceUrl: item.url || undefined,
    sourceRef: item.sourceRef || `asset:${item.id}`,
    sourceLine: item.sourceDescription || item.description || "",
    status: item.presentationStatus,
    planned: item.existence === "planned",
    referenceCount: item.referenceCount,
    checksum: item.checksum,
    durationSeconds: item.durationSeconds,
    content: item.description,
    userNotes: item.userNotes,
    targetVersion: item.targetVersion || undefined,
    generatedKind: item.generatedKind,
    ownerRef: item.ownerRef,
    kind: item.category === "upload" ? "source" : "visual",
    visualKind:
      item.detail?.kind === "material" ? undefined : item.detail?.kind,
    detail,
  };
}

function matchesFilter(
  asset: AssetDisplayItem,
  filter: AssetFilterKey,
): boolean {
  if (filter === "all") return true;
  if (filter === "planned") return asset.planned;
  if (filter === "storyboard_image")
    return asset.generatedKind === "storyboard_image";
  if (filter === "generated_video")
    return (
      asset.generatedKind === "unit_video" ||
      asset.generatedKind === "section_video"
    );
  return asset.category === filter;
}

export default function AssetsPage() {
  const { id = "" } = useParams();
  const query = useSearchParams();
  const locatorAssetId = query.get("select") || query.get("asset");
  const locatorVersionId = query.get("version");
  const reviewMode = query.get("review") === "1";
  const reviewPulse = query.get("reviewPulse");
  const reviewFocusRequest = useNavigationStore((state) => state.reviewFocus);
  const envelope = useWorkspaceViewStore((state) => state.assets);
  const headerEnvelope = useWorkspaceViewStore((state) => state.header);
  const load = useWorkspaceViewStore((state) => state.loadAssets);
  const view = presentationOf(envelope);
  const header = presentationOf(headerEnvelope);
  const error = useWorkspaceViewStore((state) => state.errors.assets);
  const events = useCreatorSessionStore((state) => state.events);
  const tasks = useCreatorTaskViewStore((state) => state.tasks);
  const [filter, setFilter] = useState<AssetFilterKey>("all");
  const [searchText, setSearchText] = useState("");
  const debouncedSearch = useDebouncedValue(searchText, 300);
  const [selectedId, setSelectedId] = useState<string | null>(locatorAssetId);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(
    locatorVersionId,
  );
  const [supplementOpen, setSupplementOpen] = useState(false);
  const [detail, setDetail] = useState<{
    assetId: string;
    kind: DetailKind;
  } | null>(null);
  const [detailOverrides, setDetailOverrides] = useState<
    Record<string, DetailAssetItem>
  >({});
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [flashId, setFlashId] = useState<string | null>(null);
  const reviewTimersRef = useRef<number[]>([]);
  const lastAssetEvent = [...events]
    .reverse()
    .find(
      (event) =>
        event.type.startsWith("task.") ||
        event.type.startsWith("task_") ||
        event.type === "workspace.head_changed",
    )?.seq;
  const reload = useCallback(() => load(id), [id, load]);
  const { submit, submitting } = useCreatorCommand(id, envelope, reload);

  useEffect(() => {
    void load(id).catch(() => undefined);
  }, [id, lastAssetEvent, load]);
  useEffect(() => {
    if (!locatorAssetId) return;
    setSelectedId(locatorAssetId);
    setSelectedVersionId(locatorVersionId);
  }, [locatorAssetId, locatorVersionId]);
  useEffect(
    () =>
      useCreatorInteractionStore
        .getState()
        .select(selectedId ? `asset:${selectedId}` : null),
    [selectedId],
  );

  const triggerAssetReviewFlash = useCallback((assetId: string) => {
    reviewTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    // Mark the business target immediately. Cross-page navigation can mount
    // this page before its asset grid has loaded, and a delayed state write
    // would otherwise be cancelled by the first route/query reconciliation.
    setFlashId(assetId);
    const scrollTimer = window.setTimeout(() => {
      document
        .querySelector(
          `[data-creator-module="asset-card"][data-creator-module-id="${CSS.escape(
            assetId,
          )}"]`,
        )
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 200);
    const clearTimer = window.setTimeout(() => setFlashId(null), 2600);
    reviewTimersRef.current = [scrollTimer, clearTimer];
  }, []);
  useEffect(() => {
    const requestedAssetId =
      reviewFocusRequest?.path === `/project/${id}/assets` &&
      reviewFocusRequest.query.review === "1"
        ? reviewFocusRequest.query.asset
        : null;
    const assetId = requestedAssetId || (reviewMode ? locatorAssetId : null);
    if (!assetId) {
      setFlashId(null);
      return;
    }
    triggerAssetReviewFlash(assetId);
    return () => {
      reviewTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      reviewTimersRef.current = [];
    };
  }, [
    id,
    locatorAssetId,
    reviewFocusRequest,
    reviewMode,
    reviewPulse,
    triggerAssetReviewFlash,
  ]);

  if (error && !view)
    return <PageLoadError message={error} retry={() => void load(id)} />;
  if (!view || !envelope) return <PageSkeleton type="grid" />;

  const assets = view.presentationAssets.map((item) =>
    toDisplay(id, item, view.ingestItems),
  );
  const selectedAsset =
    assets.find(
      (asset) =>
        asset.id === selectedId &&
        (!selectedVersionId || asset.versionId === selectedVersionId),
    ) ||
    assets.find((asset) => asset.id === selectedId) ||
    null;
  const normalizedSearch = debouncedSearch.trim().toLocaleLowerCase();
  const visibleAssets = assets.filter(
    (asset) =>
      matchesFilter(asset, filter) &&
      (!normalizedSearch ||
        `${asset.name} ${asset.content || ""}`
          .toLocaleLowerCase()
          .includes(normalizedSearch)),
  );
  const filterItems = FILTERS.map((item) => ({
    ...item,
    label: scenarioCategoryLabel(item.key, header?.scenario),
    count: assets.filter((asset) => matchesFilter(asset, item.key)).length,
  }));
  const activeIngest = view.ingestItems.find(
    (item) => item.status === "RUNNING" || item.status === "QUEUED",
  );
  const latestFailedIngestTask = [...tasks]
    .filter(
      (task) =>
        (task.kind === "asset_ingest" || task.kind === "asset_import") &&
        task.status === "FAILED",
    )
    .sort(
      (left, right) =>
        Date.parse(right.updatedAt || right.createdAt || "") -
        Date.parse(left.updatedAt || left.createdAt || ""),
    )[0];
  const latestFailedIngest =
    (latestFailedIngestTask
      ? view.ingestItems.find(
          (item) =>
            item.taskId === latestFailedIngestTask.id &&
            item.status === "FAILED",
        )
      : undefined) ||
    [...view.ingestItems].reverse().find((item) => item.status === "FAILED");
  const latestCacheFailedIngest = [...view.ingestItems]
    .reverse()
    .find((item) => item.status === "CACHE_FAILED");
  const ingestNotice =
    activeIngest || latestCacheFailedIngest || latestFailedIngest;
  const activeIngestPercent = taskProgressPercent(activeIngest?.progress);
  const detailDisplayAsset = detail
    ? assets.find((asset) => asset.id === detail.assetId) || null
    : null;
  const detailAsset =
    detail && detailDisplayAsset?.detail
      ? detailOverrides[detail.assetId] || detailDisplayAsset.detail
      : null;
  const referenceImageOptions: ReferenceImageOption[] = assets
    .filter((asset) => asset.mediaType === "image" || asset.visualKind)
    .map((asset) => ({
      value: asset.sourceRef,
      url: asset.previewUrl,
      label: asset.name,
      available: Boolean(asset.previewUrl),
    }));

  const updateDetailOverride = (next: DetailAssetItem) => {
    setDetailOverrides((current) => ({ ...current, [next.id]: next }));
  };

  const generateAsset = async (asset: AssetDisplayItem) => {
    setGeneratingId(asset.id);
    try {
      await submit(
        "GENERATE_ASSET",
        `asset:${asset.id}`,
        {},
        asset.targetVersion,
      );
    } finally {
      setGeneratingId(null);
    }
  };
  const deleteAsset = async (asset: AssetDisplayItem) => {
    if (asset.kind === "source") {
      const attached = view.attachedSources.find(
        (item) => item.sourceRef === asset.sourceRef,
      );
      if (attached)
        await submit(
          "DETACH_SOURCE_ASSETS",
          "project:assets",
          { assetVersionRefs: [asset.sourceRef] },
          view.targetVersion,
        );
      else
        await submit(
          "SUPPLEMENT_ASSET",
          `asset:${asset.id}`,
          { operation: "delete", assetVersionRef: asset.sourceRef },
          asset.targetVersion,
        );
    } else {
      await submit(
        "SUPPLEMENT_ASSET",
        `asset:${asset.id}`,
        { operation: "delete" },
        asset.targetVersion,
      );
    }
    setSelectedId(null);
  };
  const createManualAsset = (
    assetKind: "character" | "scene" | "prop" | "material",
  ) => {
    const name =
      assetKind === "character"
        ? "新角色"
        : assetKind === "scene"
        ? "新场景"
        : assetKind === "prop"
        ? "新道具"
        : "新素材";
    void submit(
      "SUPPLEMENT_ASSET",
      "project:assets",
      { operation: "create", assetKind, name },
      view.targetVersion,
    );
  };

  return (
    <div className="flex h-full min-h-0">
      <aside
        aria-label="资产分类"
        className="flex w-52 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-card)]/40"
      >
        <div className="border-b border-[var(--color-border)] p-3">
          <Input
            prefix={
              <SearchOutlined className="text-[var(--color-text-tertiary)]" />
            }
            placeholder="搜索资产..."
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            allowClear
            size="small"
            className="!rounded-lg"
          />
        </div>
        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
          {filterItems.map((item) => (
            <div key={item.key}>
              {item.divider && (
                <div className="mx-1 my-2 border-t border-[var(--color-border)]" />
              )}
              <button
                aria-label={`${item.label} ${item.count}`}
                onClick={() => setFilter(item.key)}
                className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  filter === item.key
                    ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-text-primary)]"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {item.key === "planned" && <Sparkles className="h-3 w-3" />}
                  {item.label}
                </span>
                <span
                  className={`rounded px-1.5 py-px text-[10px] ${
                    filter === item.key
                      ? "bg-[var(--color-accent)]/12 text-[var(--color-accent)]"
                      : "bg-[var(--color-bg-secondary)] text-[var(--color-text-tertiary)]"
                  }`}
                >
                  {item.count}
                </span>
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <main
        data-testid="asset-grid-column"
        className="flex min-w-0 flex-1 flex-col"
      >
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-2.5">
          <h1 className="text-sm font-semibold text-[var(--color-text-primary)]">
            资产库
            <span className="ml-2 text-xs font-normal text-[var(--color-text-tertiary)]">
              {visibleAssets.length} / {assets.length}
            </span>
          </h1>
          <div className="flex items-center gap-2">
            <Button
              size="small"
              icon={<Paperclip className="h-3 w-3" />}
              onClick={() => setSupplementOpen(true)}
              className="!flex !items-center !gap-1 !text-xs"
            >
              补充资料
            </Button>
            <Dropdown
              menu={{
                items: [
                  { key: "character", label: "新建角色（主体参考）" },
                  { key: "scene", label: "新建场景（环境参考）" },
                  { key: "prop", label: "新建道具（主体参考）" },
                  { key: "material", label: "新建素材" },
                ],
                onClick: ({ key }) =>
                  createManualAsset(
                    key as "character" | "scene" | "prop" | "material",
                  ),
              }}
            >
              <Button size="small" icon={<PlusOutlined />} className="!text-xs">
                新建
              </Button>
            </Dropdown>
            <Button
              size="small"
              loading={submitting}
              onClick={() =>
                void submit(
                  "GENERATE_ASSET",
                  "project:assets",
                  { scope: "all" },
                  view.targetVersion,
                )
              }
              className="!text-xs"
            >
              AI 生成所有资产描述
            </Button>
          </div>
        </div>

        {ingestNotice && (
          <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)]/60 px-4 py-2 text-xs text-[var(--color-text-secondary)]">
            {activeIngest
              ? `正在入库「${activeIngest.name}」${
                  activeIngestPercent != null
                    ? ` · ${activeIngestPercent}%`
                    : ""
                }`
              : latestCacheFailedIngest
              ? `本地缓存失败，公网素材仍可用于模型 · 「${
                  latestCacheFailedIngest.name
                }」${
                  latestCacheFailedIngest.error
                    ? `：${latestCacheFailedIngest.error}`
                    : ""
                }`
              : `入库失败「${latestFailedIngest!.name}」 · ${taskErrorMessage(
                  latestFailedIngestTask?.error ?? latestFailedIngest!.error,
                  "素材入库失败",
                )}`}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {visibleAssets.length === 0 ? (
            debouncedSearch || filter !== "all" ? (
              <EmptyState
                icon={Boxes}
                title="没有匹配的资产"
                description={
                  debouncedSearch
                    ? `未找到包含"${debouncedSearch}"的资产`
                    : "当前分类下暂无资产"
                }
              />
            ) : (
              <EmptyState
                icon={Boxes}
                title="资产库还是空的"
                description="通过补充资料上传素材，或让 AI 根据视频方案规划资产"
                actionText="补充资料"
                onAction={() => setSupplementOpen(true)}
              />
            )
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
              {visibleAssets.map((asset) => (
                <AssetCard
                  key={`${asset.id}:${asset.versionId || asset.sourceRef}:${
                    reviewMode && locatorAssetId === asset.id
                      ? reviewPulse || "review"
                      : ""
                  }`}
                  asset={asset}
                  selected={
                    selectedAsset?.id === asset.id &&
                    (!selectedVersionId ||
                      selectedAsset.versionId === asset.versionId)
                  }
                  onSelect={(item) => {
                    setSelectedId(item.id);
                    setSelectedVersionId(item.versionId || null);
                    setDetail(null);
                    if (
                      (query.get("select") || query.get("asset")) &&
                      (query.get("select") || query.get("asset")) !== item.id
                    )
                      navigate(`/project/${id}/assets`, true);
                  }}
                  onGenerate={asset.planned ? generateAsset : undefined}
                  generating={generatingId === asset.id}
                  flashing={
                    flashId === asset.id ||
                    (reviewMode && locatorAssetId === asset.id)
                  }
                />
              ))}
            </div>
          )}
        </div>
      </main>

      {selectedAsset && (
        <aside className="w-80 shrink-0 border-l border-[var(--color-border)] bg-[var(--color-bg-card)]/40">
          <AssetInspector
            projectId={id}
            asset={selectedAsset}
            view={view}
            onEditDetail={
              detailKindOf(selectedAsset)
                ? (asset) => {
                    const kind = detailKindOf(asset);
                    if (kind) setDetail({ assetId: asset.id, kind });
                  }
                : undefined
            }
            onDelete={deleteAsset}
          />
        </aside>
      )}

      <AssetDetailPanel
        open={Boolean(detail && detailAsset)}
        onClose={() => setDetail(null)}
        asset={detailAsset}
        assetType={detail ? DETAIL_TAB[detail.kind] : "characters"}
        projectId={id}
        referenceImageOptions={referenceImageOptions}
        onNameChange={(asset, name) => {
          updateDetailOverride({ ...asset, name } as DetailAssetItem);
          const display = assets.find((item) => item.id === asset.id);
          void submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            { field: "name", value: name },
            display?.targetVersion,
          );
        }}
        onPromptConfigChange={(
          asset,
          promptIndex,
          prompt,
          referenceImageUrls,
        ) => {
          updateDetailOverride(
            replacePromptConfig(asset, promptIndex, prompt, referenceImageUrls),
          );
          const display = assets.find((item) => item.id === asset.id);
          void submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            { field: "promptConfig", promptIndex, prompt, referenceImageUrls },
            display?.targetVersion,
          );
        }}
        onGeneratePrompt={async (
          asset,
          promptIndex,
          prompt,
          referenceImageUrls,
        ) => {
          updateDetailOverride(
            replacePromptConfig(asset, promptIndex, prompt, referenceImageUrls),
          );
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "GENERATE_ASSET",
            `asset:${asset.id}`,
            { promptIndex, prompt, referenceImageUrls },
            display?.targetVersion,
          );
        }}
        onUploadImage={async (asset, index, file) => {
          const localUrl = URL.createObjectURL(file);
          const images = [...asset.images];
          const current = images[index];
          images[index] = current
            ? { ...current, url: localUrl }
            : {
                id: `${asset.id}-image-${index}`,
                name: file.name.replace(/\.[^.]+$/, ""),
                url: localUrl,
                description: file.name,
                facetKind:
                  asset.kind === "character" ? "front_anchor" : "unknown",
              };
          const next: DetailAssetItem = {
            ...asset,
            mediaType: "image",
            primaryUrl: index === 0 ? localUrl : asset.primaryUrl,
            images,
          };
          updateDetailOverride(next);
          const accepted = await ingestAssetFile(id, file, "NONE");
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            {
              field: "image",
              promptIndex: index,
              assetId: accepted.assetId,
              assetVersionId: accepted.assetVersionId,
            },
            display?.targetVersion,
          );
        }}
        onUploadReference={async (_asset, file) => {
          await ingestAssetFile(id, file, "ATTACH_SOURCE");
          await load(id);
          message.success("参考图已上传为用户上传资产");
        }}
        onAddAppearance={async (asset, refDescription, prompt, imageUrl) => {
          const next: DetailAssetItem = {
            ...asset,
            images: [
              ...asset.images,
              {
                id: `facet-${Date.now()}`,
                name: refDescription,
                url: imageUrl,
                description: prompt,
                facetKind:
                  asset.kind === "character" ? "front_anchor" : "unknown",
              },
            ],
            refsNeeded: [...asset.refsNeeded, refDescription],
            prompts: [...asset.prompts, prompt],
            referenceImageRefs: [...asset.referenceImageRefs, []],
          };
          updateDetailOverride(next);
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            { field: "appearance", refDescription, prompt, imageUrl },
            display?.targetVersion,
          );
        }}
        onGenerateAppearancePrompt={async (asset, refDescription) => {
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            { field: "appearancePrompt", refDescription },
            display?.targetVersion,
          );
          return `${asset.name}，${refDescription}`;
        }}
        onGenerateAppearanceImage={async (asset, prompt) => {
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "GENERATE_ASSET",
            `asset:${asset.id}`,
            { prompt, purpose: "appearance" },
            display?.targetVersion,
          );
          const latest = presentationOf(
            useWorkspaceViewStore.getState().assets,
          );
          return (
            latest?.visualAssets.find((item) => item.id === asset.id)?.url ||
            latest?.visualAssets.find((item) => item.id === asset.id)
              ?.thumbnailUrl ||
            display?.previewUrl ||
            ""
          );
        }}
        onDeleteAppearance={async (asset, index) => {
          const next: DetailAssetItem = {
            ...asset,
            images: asset.images.filter((_, itemIndex) => itemIndex !== index),
            refsNeeded: asset.refsNeeded.filter(
              (_, itemIndex) => itemIndex !== index,
            ),
            prompts: asset.prompts.filter(
              (_, itemIndex) => itemIndex !== index,
            ),
            referenceImageRefs: asset.referenceImageRefs.filter(
              (_, itemIndex) => itemIndex !== index,
            ),
          };
          updateDetailOverride(next);
          const display = assets.find((item) => item.id === asset.id);
          await submit(
            "SUPPLEMENT_ASSET",
            `asset:${asset.id}`,
            { field: "appearance", action: "removeFacet", promptIndex: index },
            display?.targetVersion,
          );
        }}
      />
      <SupplementDialog
        open={supplementOpen}
        projectId={id}
        onClose={() => setSupplementOpen(false)}
        onAdded={() => void load(id)}
      />
    </div>
  );
}

function SupplementDialog({
  open,
  projectId,
  onClose,
  onAdded,
}: {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const [urlName, setUrlName] = useState("");
  const [textName, setTextName] = useState("");
  const [textContent, setTextContent] = useState("");
  const submitFiles = async (files: FileList) => {
    setSubmitting(true);
    let succeeded = 0;
    for (const file of Array.from(files)) {
      try {
        await ingestAssetFile(projectId, file, "ATTACH_SOURCE");
        succeeded += 1;
      } catch (error) {
        message.error(`「${file.name}」上传失败：${(error as Error).message}`);
      }
    }
    setSubmitting(false);
    if (succeeded > 0) {
      message.success(`已入库 ${succeeded} 个文件`);
      onAdded();
      onClose();
    }
  };
  const submitValue = async (kind: "url" | "text") => {
    const value = kind === "url" ? urlValue.trim() : textContent.trim();
    if (!value) return;
    setSubmitting(true);
    try {
      const accepted = await ingestAssetValue(projectId, {
        kind,
        name:
          (kind === "url" ? urlName : textName).trim() ||
          (kind === "url" ? value : "文本资料"),
        value,
        postIngestAction: "ATTACH_SOURCE",
      });
      if (accepted.status === "SUCCEEDED") {
        message.success(kind === "url" ? "链接已入库" : "文本资料已入库");
      } else if (
        accepted.status === "FAILED" ||
        accepted.status === "CANCELLED" ||
        accepted.status === "QUARANTINED"
      ) {
        message.error(
          taskErrorMessage(
            accepted.error,
            kind === "url" ? "链接入库失败" : "文本资料入库失败",
          ),
        );
      } else {
        message.info(
          kind === "url" ? "链接已接收，正在入库" : "文本资料已接收，正在入库",
        );
      }
      if (kind === "url") {
        setUrlValue("");
        setUrlName("");
      } else {
        setTextName("");
        setTextContent("");
      }
      onAdded();
      onClose();
    } catch (error) {
      message.error((error as Error).message || "入库失败");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title="补充资料"
      width={480}
      destroyOnHidden
    >
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        追加的资料会进入资产库「用户上传」分类，与新建项目时的入库路径一致。
      </p>
      <Tabs
        size="small"
        items={[
          {
            key: "file",
            label: "文件",
            children: (
              <label className="flex h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)]">
                <UploadOutlined className="text-lg text-[var(--color-text-tertiary)]" />
                点击选择文件（支持多选：图片 / 视频 / 音频 / 文档）
                <input
                  type="file"
                  multiple
                  hidden
                  disabled={submitting}
                  onChange={(event) => {
                    if (event.target.files?.length)
                      void submitFiles(event.target.files);
                    event.target.value = "";
                  }}
                />
              </label>
            ),
          },
          {
            key: "url",
            label: "链接",
            children: (
              <div className="space-y-2">
                <Input
                  value={urlName}
                  onChange={(event) => setUrlName(event.target.value)}
                  placeholder="名称（可选）"
                />
                <Input
                  value={urlValue}
                  onChange={(event) => setUrlValue(event.target.value)}
                  placeholder="https://…"
                  onPressEnter={() => void submitValue("url")}
                />
                <Button
                  type="primary"
                  block
                  loading={submitting}
                  disabled={!urlValue.trim()}
                  onClick={() => void submitValue("url")}
                >
                  入库
                </Button>
              </div>
            ),
          },
          {
            key: "text",
            label: "文本",
            children: (
              <div className="space-y-2">
                <Input
                  value={textName}
                  onChange={(event) => setTextName(event.target.value)}
                  placeholder="名称（如：品牌约束）"
                />
                <Input.TextArea
                  value={textContent}
                  onChange={(event) => setTextContent(event.target.value)}
                  autoSize={{ minRows: 4, maxRows: 12 }}
                  placeholder="粘贴文本资料…"
                />
                <Button
                  type="primary"
                  block
                  loading={submitting}
                  disabled={!textContent.trim()}
                  onClick={() => void submitValue("text")}
                >
                  入库
                </Button>
              </div>
            ),
          },
        ]}
      />
    </Modal>
  );
}
