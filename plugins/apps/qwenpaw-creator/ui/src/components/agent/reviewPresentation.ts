import type {
  AssetLibraryView,
  MediaComparison,
  PlanView,
  ReviewDecisionGroup,
  ReviewManifest,
  ReviewMediaVersion,
  ReviewOperation,
} from "@/contracts/creator";
import { reviewFieldForOperation } from "./ReviewFieldText";

export type ReviewPresentationCategory =
  | "change"
  | "storyboard"
  | "video"
  | "asset";

export interface ReviewGroupPresentation {
  group: ReviewDecisionGroup;
  category: ReviewPresentationCategory;
  categoryLabel: string;
  title: string;
  locationSegments: string[];
  detail: string;
  mediaVersion?: ReviewMediaVersion;
  showPreview: boolean;
}

const CATEGORY_LABELS: Record<ReviewPresentationCategory, string> = {
  change: "Agent 改动",
  storyboard: "分镜",
  video: "视频",
  asset: "素材",
};

const FIELD_LABELS: Record<string, string> = {
  title: "标题",
  summary: "摘要",
  pacing: "节奏",
  narrative: "正文",
  storyText: "正文",
  script: "剧本",
  constraints: "创作约束",
  transition: "过渡",
  transitionNote: "过渡",
  duration: "时长",
  durationBudget: "时长预算",
  dialogue: "对白",
  goal: "剪辑目标",
  storyboardPrompt: "分镜提示词",
  videoPrompt: "视频提示词",
  sceneRef: "场景引用",
  description: "镜头描述",
  cameraDescription: "运镜",
};

const PATH_LABELS: Array<[RegExp, string]> = [
  [/\/production\/edit\/timeline-summary\.md$/i, "剪辑方案"],
  [/\/production\/edit\/intent\.md$/i, "剪辑目标"],
  [/\/understanding\/current\.ref$/i, "素材理解结果"],
  [/\/understanding\/versions\/[^/]+\/summary\.md$/i, "素材理解摘要"],
  [/\/understanding\/versions\/[^/]+\/index\.txt$/i, "素材理解索引"],
  [/\/target-duration\.txt$/i, "目标时长"],
  [/\/duration-budget\.txt$/i, "时长预算"],
  [/\/constraints\.md$/i, "创作约束"],
  [/\/transition\.md$/i, "过渡"],
  [/\/pacing\.md$/i, "节奏"],
  [/\/narrative\.md$/i, "正文"],
  [/\/summary\.md$/i, "摘要"],
  [/\/title\.txt$/i, "标题"],
  [/\/duration\.txt$/i, "时长"],
  [/\/route\.txt$/i, "剪辑路线"],
  [/\/continuity\.md$/i, "连续性说明"],
];

function operationSet(group: ReviewDecisionGroup): Set<string> {
  return new Set(group.operationIds);
}

function groupOperations(
  group: ReviewDecisionGroup,
  operations: ReviewOperation[],
): ReviewOperation[] {
  const ids = operationSet(group);
  return operations.filter((operation) => ids.has(operation.id));
}

function groupComparison(
  group: ReviewDecisionGroup,
  comparisons: MediaComparison[],
): MediaComparison | undefined {
  const ids = operationSet(group);
  return comparisons.find((comparison) =>
    comparison.operationIds.some((id) => ids.has(id)),
  );
}

function entityIdFromPath(
  path: string,
  collection: "sections" | "units" | "shots",
): string | null {
  const parts = path.split("/").filter(Boolean);
  const index = parts.lastIndexOf(collection);
  if (index < 0 || !parts[index + 1]) return null;
  let segment = parts[index + 1];
  try {
    segment = decodeURIComponent(segment);
  } catch {
    return null;
  }
  const sparse = segment.split("--");
  return sparse.length > 1 ? sparse[1] || null : segment;
}

function refId(ref: string | null | undefined, prefix: string): string | null {
  if (!ref?.startsWith(`${prefix}:`)) return null;
  return ref.slice(prefix.length + 1).split("/", 1)[0] || null;
}

function pathFieldLabel(path: string | undefined): string | null {
  if (!path) return null;
  const semantic = path.match(
    /^(?:section|unit):[^/]+(?:\/shot:[^/]+)?\/([^/]+)$/,
  );
  if (semantic) return FIELD_LABELS[semantic[1]] ?? null;
  return PATH_LABELS.find(([pattern]) => pattern.test(path))?.[1] ?? null;
}

function safeGroupTitle(title: string): string | null {
  if (
    !title ||
    /(?:^|\s)(?:asset|unit|section|project|post):[^\s·]+/.test(title)
  )
    return null;
  if (title.includes("/") || title.includes("\\")) return null;
  return title;
}

function assetName(
  assetId: string | null,
  assets: AssetLibraryView | null,
): string | null {
  if (!assetId || !assets) return null;
  return (
    assets.attachedSources.find((item) => item.assetId === assetId)?.name ??
    assets.availableAssets.find((item) => item.assetId === assetId)?.name ??
    assets.visualAssets.find((item) => item.id === assetId)?.name ??
    assets.presentationAssets.find((item) => item.id === assetId)?.name ??
    null
  );
}

function assetNameFromPath(path: string): string | null {
  const segment = path
    .split("/")
    .find((part, index, values) => values[index - 1] === "sources");
  if (!segment) return null;
  let decoded = segment;
  try {
    decoded = decodeURIComponent(segment);
  } catch {
    return null;
  }
  const sparse = decoded.split("--");
  const slug = sparse.length > 1 ? sparse.slice(1).join("--") : "";
  if (!slug) return null;
  return slug.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim() || null;
}

function paddedNumber(value: number): string {
  return String(value).padStart(2, "0");
}

function reviewLocation(
  group: ReviewDecisionGroup,
  operations: ReviewOperation[],
  category: ReviewPresentationCategory,
  plan: PlanView | null,
  assets: AssetLibraryView | null,
  comparison?: MediaComparison,
): string[] {
  const semantic =
    operations.map(reviewFieldForOperation).find(Boolean) ?? null;
  const semanticSectionId = semantic ? refId(semantic, "section") : null;
  const semanticUnitId = semantic ? refId(semantic, "unit") : null;
  const semanticShotId = semantic?.match(/\/shot:([^/]+)/)?.[1] ?? null;
  const path = operations.map((item) => item.path).find(Boolean) ?? "";
  const unitId =
    semanticUnitId ??
    entityIdFromPath(path, "units") ??
    refId(comparison?.targetRef, "unit") ??
    operations.map((item) => refId(item.targetRef, "unit")).find(Boolean) ??
    null;
  const sectionId =
    semanticSectionId ??
    entityIdFromPath(path, "sections") ??
    refId(comparison?.targetRef, "section") ??
    refId(comparison?.targetRef, "post") ??
    operations.map((item) => refId(item.targetRef, "section")).find(Boolean) ??
    null;
  const shotId = semanticShotId ?? entityIdFromPath(path, "shots");
  const assetId =
    operations.map((item) => refId(item.targetRef, "asset")).find(Boolean) ??
    null;
  const field =
    pathFieldLabel(semantic ?? undefined) ??
    operations.map((item) => pathFieldLabel(item.path)).find(Boolean) ??
    (category === "storyboard"
      ? "分镜图"
      : category === "video"
      ? "视频"
      : category === "asset"
      ? "素材信息"
      : null);

  // Some legacy manifests carried an asset targetRef for Plan text paths.
  // The semantic workspace path/category is authoritative for presentation;
  // only genuine asset-category items belong under the asset library.
  if (category === "asset") {
    const name = assetName(assetId, assets) ?? assetNameFromPath(path);
    return ["资产库", ...(name ? [name] : []), ...(field ? [field] : [])];
  }

  if (
    comparison?.targetRef === "post:final" ||
    operations.some((item) => item.targetRef === "post:final")
  ) {
    return ["视频方案", "最终合成", ...(field ? [field] : [])];
  }

  const unitMatch = unitId
    ? plan?.sections
        .flatMap((section) => section.units.map((unit) => ({ section, unit })))
        .find((item) => item.unit.id === unitId)
    : undefined;
  const section =
    unitMatch?.section ??
    (sectionId && sectionId !== "final"
      ? plan?.sections.find((item) => item.id === sectionId)
      : undefined);
  const unit = unitMatch?.unit;
  const shot = shotId
    ? unit?.shots.find((item) => item.id === shotId)
    : undefined;
  const segments = ["视频方案"];
  if (section)
    segments.push(`${paddedNumber(section.number)} ${section.title || "段落"}`);
  if (unit)
    segments.push(`${paddedNumber(unit.number)} ${unit.title || "剪辑片段"}`);
  if (shotId)
    segments.push(shot ? `镜头 ${paddedNumber(shot.number)}` : "镜头");
  if (!section && !unit) {
    const fallback = safeGroupTitle(group.title);
    if (fallback) segments.push(fallback);
    else if (operations.some((item) => item.targetRef.startsWith("project:")))
      segments.push("项目设置");
  }
  if (field && segments.at(-1) !== field) segments.push(field);
  return segments;
}

function presentationCategory(
  operations: ReviewOperation[],
  comparison?: MediaComparison,
): ReviewPresentationCategory {
  const version =
    comparison?.after ?? comparison?.before ?? comparison?.candidates[0];
  if (
    version?.versionKind === "asset" &&
    operations.some(
      (operation) =>
        operation.targetRef.startsWith("asset:") ||
        operation.path?.includes("/refs/sources/"),
    )
  )
    return "asset";
  if (version?.mediaType === "image") return "storyboard";
  if (version?.mediaType === "video") return "video";
  const paths = operations.map((item) => item.path ?? "");
  if (paths.some((path) => path.includes("/storyboard/"))) return "storyboard";
  if (paths.some((path) => /(?:rendered-video|video)\.ref$/i.test(path)))
    return "video";
  if (
    paths.some(
      (path) => path.startsWith("sources/") || path.includes("/understanding/"),
    )
  )
    return "asset";
  return "change";
}

function presentationDetail(
  category: ReviewPresentationCategory,
  operations: ReviewOperation[],
): string {
  if (category === "storyboard")
    return "生成的分镜图待确认，请前往对应位置查看。";
  if (category === "video") return "生成的视频待确认，请前往对应位置查看。";
  if (category === "asset") return "素材相关内容有更新，请前往素材位置查看。";
  return "";
}

export function presentReviewGroup(
  group: ReviewDecisionGroup,
  manifest: ReviewManifest,
  plan: PlanView | null,
  assets: AssetLibraryView | null,
): ReviewGroupPresentation {
  const operations = groupOperations(group, manifest.operations);
  const comparison = groupComparison(group, manifest.mediaComparisons);
  const category = presentationCategory(operations, comparison);
  const locationSegments = reviewLocation(
    group,
    operations,
    category,
    plan,
    assets,
    comparison,
  );
  const mediaVersion =
    comparison?.after ?? comparison?.before ?? comparison?.candidates[0];
  return {
    group,
    category,
    categoryLabel: CATEGORY_LABELS[category],
    title: locationSegments.join(" / "),
    locationSegments,
    detail: presentationDetail(category, operations),
    mediaVersion,
    showPreview:
      mediaVersion?.mediaType === "image" ||
      mediaVersion?.mediaType === "video",
  };
}

export function presentPendingReviewGroups(
  manifest: ReviewManifest | null,
  plan: PlanView | null,
  assets: AssetLibraryView | null,
): ReviewGroupPresentation[] {
  if (!manifest) return [];
  return manifest.decisionGroups
    .filter((group) => group.decision === "PENDING")
    .map((group) => presentReviewGroup(group, manifest, plan, assets));
}

export function groupReviewPresentations(
  items: ReviewGroupPresentation[],
): Array<{
  id: ReviewPresentationCategory;
  label: string;
  items: ReviewGroupPresentation[];
}> {
  const order: ReviewPresentationCategory[] = [
    "change",
    "storyboard",
    "video",
    "asset",
  ];
  return order
    .map((id) => ({
      id,
      label: CATEGORY_LABELS[id],
      items: items.filter((item) => item.category === id),
    }))
    .filter((group) => group.items.length > 0);
}
