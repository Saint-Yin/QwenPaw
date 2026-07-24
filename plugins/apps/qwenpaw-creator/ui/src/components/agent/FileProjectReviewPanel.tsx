import { useState } from "react";
import { message } from "antd";
import { Check, Eye, FileDiff, Image as ImageIcon, Undo2, Video } from "lucide-react";
import type {
  FileProjectReviewDecision,
  FileProjectReviewOperation,
  FileProjectReviewOperationDecision,
  FileProjectReviewRecord,
} from "@/contracts/creator";
import { getArtifactVersionMediaUrl } from "@/api/creator";
import { navigateToLocator } from "@/routing/locators";
import { useFileProjectReviewStore } from "@/store/fileProjectReviewStore";
import OnboardingHint from "@/components/onboarding/OnboardingHint";
import DiffView from "./DiffView";

const DECISION_LABELS: Record<FileProjectReviewOperationDecision, string> = {
  PENDING: "待审",
  ACCEPTED: "已保留",
  REJECTED: "已撤销",
  REVISED: "已修订",
  SUPERSEDED_BY_USER_EDIT: "已被用户编辑替代",
};

const ARTIFACT_KIND_LABELS: Record<string, string> = {
  r2v_storyboard_image: "分镜图",
  visual_asset_image: "角色 / 视觉资产图",
  r2v_video: "视频",
};

function operationLocation(operation: FileProjectReviewOperation): string {
  return (
    operation.json_pointer ??
    (operation.file_id ? `file:${operation.file_id}` : null) ??
    operation.target_ref ??
    "unknown"
  );
}

/** The media artifact locator for a media-generation review, if any. */
function mediaLocatorOf(
  review: FileProjectReviewRecord,
): Record<string, string> | null {
  for (const operation of review.operations) {
    const locator = operation.ui_locator;
    if (locator && (locator.mediaType === "image" || locator.mediaType === "video")) {
      return locator;
    }
  }
  return null;
}

function mediaLabel(locator: Record<string, string>): string {
  if (locator.artifactKind && ARTIFACT_KIND_LABELS[locator.artifactKind]) {
    return ARTIFACT_KIND_LABELS[locator.artifactKind];
  }
  return locator.mediaType === "video" ? "视频" : "图片";
}

export default function FileProjectReviewPanel({
  projectId,
  review,
}: {
  projectId: string;
  review: FileProjectReviewRecord;
}) {
  const decisionInFlight = useFileProjectReviewStore(
    (state) => state.decisionInFlight,
  );
  const syncError = useFileProjectReviewStore((state) => state.syncError);
  const decide = useFileProjectReviewStore((state) => state.decide);
  const [localBusy, setLocalBusy] = useState(false);

  if (review.status !== "PENDING") return null;
  const pending = review.operations.filter(
    (operation) => operation.decision === "PENDING",
  );
  const busy = decisionInFlight || localBusy;
  const mediaLocator = mediaLocatorOf(review);

  const submit = async (
    operations: FileProjectReviewOperation[],
    decision: FileProjectReviewDecision,
  ) => {
    if (operations.length === 0) return;
    setLocalBusy(true);
    try {
      await decide(
        projectId,
        review.review_id,
        operations.map((operation) => ({
          operation_id: operation.operation_id,
          decision,
        })),
      );
      message.success(
        decision === "ACCEPT"
          ? `已保留 ${operations.length} 处修改`
          : `已撤销 ${operations.length} 处修改`,
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error));
    } finally {
      setLocalBusy(false);
    }
  };

  const openLocator = (
    locator: Record<string, string>,
    fallbackField?: string | null,
  ) => {
    const field = locator.field ?? fallbackField ?? undefined;
    navigateToLocator(projectId, locator, {
      review: true,
      field: field ?? undefined,
      description: "审阅 / 查看修改",
    });
  };

  return (
    <section
      data-file-project-review={review.review_id}
      className="mb-3 rounded-xl border border-[var(--color-accent)]/35 bg-[var(--color-bg-primary)]/70 p-2.5"
    >
      <OnboardingHint hintKey="review" className="mb-2">
        首次说明：Agent 对项目的每处修改都会在这里待你审阅：「保留」采纳修改，「撤销」回退到修改前；也可逐条处理。
      </OnboardingHint>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
            {mediaLocator ? (
              mediaLocator.mediaType === "video" ? (
                <Video className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              ) : (
                <ImageIcon className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              )
            ) : (
              <FileDiff className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            )}
            {mediaLocator ? `${mediaLabel(mediaLocator)}审阅` : "文件项目修改"}
            <span className="rounded-full bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-[9px] text-[var(--color-accent)]">
              {pending.length} 待审
            </span>
          </h3>
          <p
            className="mt-0.5 truncate font-mono text-[9px] text-[var(--color-text-tertiary)]"
            title={review.round_id}
          >
            round {review.round_id} · generation {review.baseline_generation} →{" "}
            {review.candidate_generation}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            disabled={busy || pending.length === 0}
            onClick={() => void submit(pending, "ACCEPT")}
            className="rounded-md bg-[var(--color-accent)] px-2 py-1 text-[10px] font-medium text-white disabled:opacity-50"
          >
            {mediaLocator ? "保留" : "全部保留"}
          </button>
          <button
            type="button"
            disabled={busy || pending.length === 0}
            onClick={() => void submit(pending, "REJECT")}
            className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[10px] font-medium text-[var(--color-text-secondary)] disabled:opacity-50"
          >
            {mediaLocator ? "撤销" : "全部撤销"}
          </button>
        </div>
      </div>

      {syncError && (
        <p
          role="alert"
          className="mt-2 rounded-md bg-[var(--color-warning-soft)] px-2 py-1 text-[10px] text-[var(--color-warning)]"
        >
          同步异常，当前显示上次成功结果：{syncError}
        </p>
      )}

      {mediaLocator ? (
        <MediaReviewBody
          locator={mediaLocator}
          onOpen={() => openLocator(mediaLocator)}
        />
      ) : (
        <ul className="mt-2 space-y-2">
          {review.operations.map((operation) => {
            const operationPending = operation.decision === "PENDING";
            const location = operationLocation(operation);
            const locator = operation.ui_locator ?? {};
            const canJump =
              Boolean(locator.field) || Boolean(operation.json_pointer);
            return (
              <li
                key={operation.operation_id}
                data-file-review-operation={operation.operation_id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-all font-mono text-[10px] font-semibold text-[var(--color-text-primary)]">
                      {location}
                    </p>
                    <p className="mt-0.5 text-[9px] text-[var(--color-text-tertiary)]">
                      {operation.kind} · {DECISION_LABELS[operation.decision]}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    {canJump && (
                      <button
                        type="button"
                        aria-label={`查看 ${location}`}
                        onClick={() =>
                          openLocator(locator, operation.json_pointer)
                        }
                        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-text-secondary)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-accent)]"
                      >
                        <Eye className="h-3 w-3" />
                        查看
                      </button>
                    )}
                    {operationPending && (
                      <>
                        <button
                          type="button"
                          aria-label={`保留 ${location}`}
                          disabled={busy}
                          onClick={() => void submit([operation], "ACCEPT")}
                          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] disabled:opacity-50"
                        >
                          <Check className="h-3 w-3" />
                          保留
                        </button>
                        <button
                          type="button"
                          aria-label={`撤销 ${location}`}
                          disabled={busy}
                          onClick={() => void submit([operation], "REJECT")}
                          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] disabled:opacity-50"
                        >
                          <Undo2 className="h-3 w-3" />
                          撤销
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <div className="mt-2">
                  <DiffView before={operation.before} after={operation.after} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function MediaReviewBody({
  locator,
  onOpen,
}: {
  locator: Record<string, string>;
  onOpen: () => void;
}) {
  const versionId = locator.artifactVersionId;
  const mediaUrl = versionId ? getArtifactVersionMediaUrl(versionId) : null;
  const isVideo = locator.mediaType === "video";
  return (
    <div
      data-file-review-media={versionId ?? ""}
      className="mt-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-2"
    >
      <div className="overflow-hidden rounded-md bg-[var(--color-bg-secondary)]">
        {mediaUrl ? (
          isVideo ? (
            <video
              src={mediaUrl}
              controls
              className="max-h-48 w-full object-contain"
            />
          ) : (
            <img
              src={mediaUrl}
              alt={mediaLabel(locator)}
              className="max-h-48 w-full object-contain"
            />
          )
        ) : (
          <p className="p-4 text-center text-[10px] text-[var(--color-text-tertiary)]">
            预览不可用
          </p>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-[10px] text-[var(--color-text-secondary)]">
          {mediaLabel(locator)}
          {locator.elementId ? ` · 分镜 ${locator.elementId}` : ""}
          {locator.assetId ? ` · 资产 ${locator.assetId}` : ""}
        </p>
        <button
          type="button"
          onClick={onOpen}
          className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]"
        >
          <Eye className="h-3 w-3" />
          查看生成详情
        </button>
      </div>
    </div>
  );
}
