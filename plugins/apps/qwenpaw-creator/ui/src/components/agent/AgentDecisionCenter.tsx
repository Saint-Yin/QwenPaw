import { useState } from "react";
import { message } from "antd";
import {
  CheckCircle2,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  FileImage,
  FileVideo,
  Undo2,
} from "lucide-react";
import {
  getArtifactVersionMediaUrl,
  getAssetVersionMediaUrl,
} from "@/api/creator";
import type { ReviewGroupPresentation } from "./reviewPresentation";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import {
  presentationOf,
  useWorkspaceViewStore,
} from "@/store/workspaceViewStore";
import ExecutionAuthorizationCard from "./ExecutionAuthorizationCard";
import {
  groupReviewPresentations,
  presentPendingReviewGroups,
} from "./reviewPresentation";

const BUTTON_GHOST =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]";
const BUTTON_PRIMARY =
  "rounded-md bg-[var(--color-accent)] px-2 py-1 text-[11px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50";

function mediaUrl(item: ReviewGroupPresentation): string | null {
  const version = item.mediaVersion;
  if (!version) return null;
  return version.versionKind === "artifact"
    ? getArtifactVersionMediaUrl(version.versionId)
    : getAssetVersionMediaUrl(version.versionId);
}

function DecisionThumb({ item }: { item: ReviewGroupPresentation }) {
  if (!item.showPreview) return null;
  const url = mediaUrl(item);
  if (url && item.mediaVersion?.mediaType === "image") {
    return (
      <img
        data-review-thumbnail
        src={url}
        alt={item.title}
        className="h-10 w-14 shrink-0 rounded-md border border-[var(--color-border)] object-cover"
      />
    );
  }
  const Icon = item.category === "video" ? FileVideo : FileImage;
  return (
    <div
      data-review-thumbnail
      className="flex h-10 w-14 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
    >
      <Icon className="h-4 w-4 text-[var(--color-text-tertiary)]" />
    </div>
  );
}

function ReviewLocationTitle({ item }: { item: ReviewGroupPresentation }) {
  return (
    <div
      aria-label={item.title}
      className="flex min-w-0 flex-wrap items-center gap-x-0.5 gap-y-0.5 text-[11px] leading-4"
      title={item.title}
    >
      {item.locationSegments.map((segment, index) => (
        <span key={`${segment}-${index}`} className="contents">
          {index > 0 && (
            <ChevronRight className="h-3 w-3 shrink-0 text-[var(--color-text-tertiary)]" />
          )}
          <span
            className={
              index === item.locationSegments.length - 1
                ? "font-semibold text-[var(--color-text-primary)]"
                : "text-[var(--color-text-tertiary)]"
            }
          >
            {segment}
          </span>
        </span>
      ))}
    </div>
  );
}

function ReviewSummaryCard({
  item,
  onView,
}: {
  item: ReviewGroupPresentation;
  onView: () => void;
}) {
  const decide = useReviewManifestStore((state) => state.decide);
  const [busy, setBusy] = useState<"ACCEPT" | "REJECT" | null>(null);
  const makeDecision = async (decision: "ACCEPT" | "REJECT") => {
    const current = useReviewManifestStore
      .getState()
      .manifest?.decisionGroups.find(
        (group) => group.id === item.group.id && group.decision === "PENDING",
      );
    if (!current) return;
    setBusy(decision);
    try {
      await decide(current.id, {
        decisionToken: current.decisionToken,
        decision,
      });
      message.success(
        decision === "ACCEPT" ? "已接受这处修改" : "已撤销这处修改",
      );
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <article
      data-review-summary-card={item.group.id}
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-2.5"
    >
      <div className="flex items-start gap-2.5">
        <DecisionThumb item={item} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--color-accent)]">
              <ClipboardCheck className="h-3 w-3" />
              待审
            </span>
            <div className="min-w-0 flex-1">
              <ReviewLocationTitle item={item} />
            </div>
          </div>
          {item.detail && (
            <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-[var(--color-text-tertiary)]">
              {item.detail}
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void makeDecision("ACCEPT")}
          className={`flex flex-1 items-center justify-center gap-1 ${BUTTON_PRIMARY}`}
        >
          <CircleCheck className="h-3 w-3" />
          接受
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void makeDecision("REJECT")}
          className={`flex flex-1 items-center justify-center gap-1 ${BUTTON_GHOST}`}
        >
          <Undo2 className="h-3 w-3" />
          撤销
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={onView}
          className={BUTTON_GHOST}
        >
          查看
        </button>
      </div>
    </article>
  );
}

export default function AgentDecisionCenter({
  projectId: _projectId,
  onViewReview,
}: {
  projectId: string;
  onViewReview?: (groupId: string) => void;
}) {
  const manifest = useReviewManifestStore((state) => state.manifest);
  const authorizations = useReviewManifestStore(
    (state) => state.authorizations,
  );
  const loading = useReviewManifestStore((state) => state.loading);
  const error = useReviewManifestStore((state) => state.error);
  const plan = presentationOf(useWorkspaceViewStore((state) => state.plan));
  const assets = presentationOf(useWorkspaceViewStore((state) => state.assets));
  const pendingAuthorizations = authorizations.filter(
    (item) => item.status === "PENDING",
  );
  const pendingItems = presentPendingReviewGroups(manifest, plan, assets);
  const reviewGroups = groupReviewPresentations(pendingItems);
  const decide = useReviewManifestStore((state) => state.decide);
  const [bulkBusy, setBulkBusy] = useState(false);

  const acceptAll = async (items: ReviewGroupPresentation[]) => {
    setBulkBusy(true);
    try {
      for (const item of items) {
        const current = useReviewManifestStore
          .getState()
          .manifest?.decisionGroups.find(
            (group) =>
              group.id === item.group.id && group.decision === "PENDING",
          );
        if (current)
          await decide(current.id, {
            decisionToken: current.decisionToken,
            decision: "ACCEPT",
          });
      }
      message.success(`已接受 ${items.length} 个待审项`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  if (loading && !manifest && pendingAuthorizations.length === 0) {
    return (
      <p className="px-1 py-2 text-[11px] text-[var(--color-text-tertiary)]">
        加载审阅清单…
      </p>
    );
  }
  if (error && !manifest && pendingAuthorizations.length === 0) {
    return (
      <p className="px-1 py-2 text-[11px] text-[var(--color-danger)]">
        审阅清单读取失败：{error}
      </p>
    );
  }
  if (!pendingItems.length && !pendingAuthorizations.length) {
    return (
      <div className="flex flex-col items-center gap-1.5 py-10 text-center">
        <CheckCircle2 className="h-8 w-8 text-[var(--color-success)]" />
        <p className="text-sm font-medium text-[var(--color-text-primary)]">
          暂无待处理的决策
        </p>
        <p className="text-[11px] text-[var(--color-text-tertiary)]">
          只有你提出修改后产生的变化才会进入审阅。
        </p>
      </div>
    );
  }

  return (
    <>
      {pendingAuthorizations.length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-tertiary)]">
            <span>生产确认</span>
            <span className="rounded-full bg-[var(--color-bg-secondary)] px-1.5 py-0.5">
              {pendingAuthorizations.length}
            </span>
          </div>
          <ul className="space-y-2">
            {pendingAuthorizations.map((authorization) => (
              <li key={authorization.id}>
                <ExecutionAuthorizationCard authorization={authorization} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {reviewGroups.map((group) => (
        <div
          key={group.id}
          className="mb-3"
          data-review-summary-group={group.id}
        >
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-text-tertiary)]">
            <span>{group.label}</span>
            <span className="rounded-full bg-[var(--color-bg-secondary)] px-1.5 py-0.5">
              {group.items.length}
            </span>
            {group.items.length > 1 && (
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => void acceptAll(group.items)}
                className="ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 disabled:opacity-50"
              >
                全部接受（{group.items.length}）
              </button>
            )}
          </div>
          <ul className="space-y-2">
            {group.items.map((item) => (
              <li key={item.group.id}>
                <ReviewSummaryCard
                  item={item}
                  onView={() => onViewReview?.(item.group.id)}
                />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
