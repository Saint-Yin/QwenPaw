import { Button } from "antd";
import { Link2, Sparkles } from "lucide-react";
import type { AssetDetailView } from "@/contracts/creator";
import AssetMediaPreview, { type AssetPreviewState } from "./AssetMediaPreview";

export type AssetDisplayStatus = "draft" | "pending" | "accepted" | "stale";

export interface AssetDisplayItem {
  id: string;
  versionId?: string;
  name: string;
  category: string;
  mediaType: string;
  previewUrl?: string;
  previewState: AssetPreviewState;
  sourceUrl?: string;
  sourceRef: string;
  sourceLine: string;
  status: AssetDisplayStatus;
  planned: boolean;
  referenceCount: number;
  checksum?: string;
  durationSeconds?: number;
  content?: string;
  userNotes?: string;
  targetVersion?: string;
  generatedKind?: string;
  ownerRef?: string;
  kind: "source" | "visual";
  visualKind?: "character" | "scene" | "prop";
  detail?: AssetDetailView;
}

const STATUS_LABELS: Record<AssetDisplayStatus, string> = {
  draft: "草稿",
  pending: "待统一审阅",
  accepted: "已接受",
  stale: "已过期",
};

const STATUS_TONES: Record<AssetDisplayStatus, string> = {
  draft:
    "border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-tertiary)]",
  pending:
    "border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] text-[var(--color-accent)]",
  accepted:
    "border-[var(--color-success)]/25 bg-[var(--color-success-soft)] text-[var(--color-success)]",
  stale:
    "border-[var(--color-danger)]/25 bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
};

export function assetTypeTag(asset: AssetDisplayItem): string {
  if (asset.generatedKind === "storyboard_image") return "SB";
  if (
    asset.generatedKind === "unit_video" ||
    asset.generatedKind === "section_video"
  )
    return "MP4";
  switch (asset.mediaType) {
    case "image":
      return "IMG";
    case "video":
      return "VID";
    case "audio":
      return "AUD";
    case "url":
      return "URL";
    case "doc":
      return "DOC";
    case "text":
      return "TXT";
    default:
      return asset.visualKind === "character" ? "CHR" : "IMG";
  }
}

export default function AssetCard({
  asset,
  selected,
  onSelect,
  onGenerate,
  generating,
  flashing,
}: {
  asset: AssetDisplayItem;
  selected: boolean;
  onSelect: (asset: AssetDisplayItem) => void;
  onGenerate?: (asset: AssetDisplayItem) => void;
  generating?: boolean;
  flashing?: boolean;
}) {
  const tone =
    asset.previewState === "failed"
      ? STATUS_TONES.stale
      : asset.previewState === "processing"
      ? STATUS_TONES.pending
      : STATUS_TONES[asset.status];
  const statusLabel =
    asset.previewState === "failed"
      ? "入库失败"
      : asset.previewState === "processing"
      ? "入库中"
      : asset.planned
      ? "待生成"
      : STATUS_LABELS[asset.status];
  return (
    <article
      data-creator-module="asset-card"
      data-creator-module-id={asset.id}
      data-creator-module-ref={`asset:${asset.id}`}
      data-asset-id={asset.id}
      data-asset-version={asset.versionId}
      onClick={() => onSelect(asset)}
      className={`group cursor-pointer overflow-hidden rounded-xl border bg-[var(--color-bg-card)] transition-all ${
        flashing ? "review-flash " : ""
      }${
        selected
          ? "border-[var(--color-accent)] shadow-[0_0_0_1px_var(--color-accent)]"
          : asset.planned
          ? "border-dashed border-[var(--color-border-strong)] hover:border-[var(--color-accent)]/50"
          : "border-[var(--color-border)] hover:border-[var(--color-border-strong)] hover:shadow-sm"
      }`}
    >
      <div className="relative flex h-32 items-center justify-center overflow-hidden bg-[var(--color-bg-secondary)]">
        <AssetMediaPreview
          name={asset.name}
          mediaType={asset.mediaType}
          previewUrl={asset.previewUrl}
          state={asset.previewState}
          mediaClassName={
            asset.mediaType === "image"
              ? "h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
              : "h-full w-full object-cover"
          }
          placeholderClassName="rounded-md border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-primary)]/70 px-3 py-1.5 text-xs font-semibold text-[var(--color-text-tertiary)]"
        />
        <span className="absolute left-2 top-2 rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-bold text-white">
          {assetTypeTag(asset)}
        </span>
        {asset.referenceCount > 0 && (
          <span className="absolute right-2 top-2 flex items-center gap-1 rounded bg-black/65 px-1.5 py-0.5 text-[10px] font-medium text-white">
            <Link2 className="h-2.5 w-2.5" />
            {asset.referenceCount}
          </span>
        )}
        {asset.planned && onGenerate && (
          <Button
            size="small"
            type="primary"
            icon={<Sparkles className="h-3 w-3" />}
            loading={generating}
            onClick={(event) => {
              event.stopPropagation();
              onGenerate(asset);
            }}
            className="!absolute !bottom-2 !right-2 !flex !items-center !gap-1 !text-[11px]"
          >
            生成
          </Button>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="min-w-0 truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {asset.name}
          </h3>
          <span
            className={`shrink-0 rounded border px-1.5 py-px text-[10px] ${tone}`}
          >
            {statusLabel}
          </span>
        </div>
        <p className="mt-1 line-clamp-2 min-h-[2rem] text-[11px] leading-4 text-[var(--color-text-secondary)]">
          {asset.sourceLine}
        </p>
      </div>
    </article>
  );
}
