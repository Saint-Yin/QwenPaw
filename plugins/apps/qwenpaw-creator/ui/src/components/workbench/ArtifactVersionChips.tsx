import type { ArtifactVersionView } from "@/contracts/creator";

const REVIEW_DOT = {
  accepted: "bg-[var(--color-success)]",
  pending: "bg-[var(--color-warning)]",
  draft: "bg-[var(--color-text-tertiary)]",
} as const;

/**
 * 与 origin/main Workbench 的 VersionChips 保持同一 DOM 与样式。
 * 点击 chip 只切换本地查看版本；版本接受由相邻的“接受”按钮显式提交。
 */
export default function ArtifactVersionChips({
  versions,
  currentId,
  viewingId,
  focusVersion,
  onView,
}: {
  versions: ArtifactVersionView[];
  currentId?: string | null;
  viewingId: string | null;
  focusVersion?: string | null;
  onView: (id: string) => void;
}) {
  if (versions.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {versions.map((version, index) => {
        const active = version.id === viewingId;
        const current = version.id === currentId || version.selected;
        const status = current
          ? "accepted"
          : version.reviewOperationId
          ? "pending"
          : "draft";
        return (
          <button
            key={version.id}
            type="button"
            data-artifact-version={version.id}
            onClick={() => onView(version.id)}
            title={`${status}${current ? " · 当前版本" : ""}`}
            className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors ${
              active
                ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                : "border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]"
            } ${focusVersion === version.id ? "review-flash" : ""}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${REVIEW_DOT[status]}`}
            />
            v{index + 1}
            {current && <span className="opacity-70">·当前</span>}
          </button>
        );
      })}
    </div>
  );
}
