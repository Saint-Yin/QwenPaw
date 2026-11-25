import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Switch, Tooltip, message } from "antd";
import { useProjectSnapshotStore } from "@/store/projectSnapshotStore";
import { projectJsonPointer } from "@/lib/projectJsonPointer";

/**
 * Project-level "段间连贯优先" switch living in the shared TopNav toolbar,
 * so the dial is reachable at any point of a session (creation, storyboards,
 * generation) instead of only inside the timeline editor. ON keeps same-scene
 * segments serialized and anchored; OFF (throughput) parallelizes every
 * segment as plain omni-reference. Persisted through the same CAS Patch
 * channel as any other project setting; affects undispatched segments only.
 */
export default function ContinuityToggle({
  compact = false,
}: {
  compact?: boolean;
} = {}) {
  const { t } = useTranslation();
  const projectId = useProjectSnapshotStore((state) => state.projectId);
  const stored = useProjectSnapshotStore(
    (state) => state.project?.settings?.video_continuity,
  );
  const patch = useProjectSnapshotStore((state) => state.patch);

  const apply = useCallback(
    async (checked: boolean) => {
      const value = checked ? "continuity" : "throughput";
      if ((stored ?? "continuity") === value) return;
      try {
        await patch(projectId!, [
          {
            // The migrated server view always carries the key (default
            // null), so the replace branch is what production exercises;
            // add stays for documents that predate the field entirely.
            op: stored === undefined ? "add" : "replace",
            path: projectJsonPointer("settings", "video_continuity"),
            before: stored,
            missingBefore: stored === undefined,
            value,
          },
        ]);
        message.success(t("nav.continuityUpdated"));
      } catch (error) {
        message.error(
          t("nav.continuityUpdateFailed", {
            detail: (error as Error).message,
          }),
        );
      }
    },
    [patch, projectId, stored, t],
  );

  if (!projectId) {
    // No project bound to this view yet (home/creation landing): the dial
    // is a per-project setting, so the chip stays out of the toolbar.
    return null;
  }
  return (
    <Tooltip title={t("nav.continuityTooltip")}>
      <label
        className={`flex shrink-0 cursor-pointer items-center gap-1.5 ${
          compact
            ? "rounded-full bg-[rgba(43,27,0,0.04)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-secondary)] dark:bg-white/5"
            : "rounded-lg border border-[var(--color-border)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--color-text-secondary)] dark:bg-[var(--color-bg-elevated)]"
        }`}
      >
        <Switch
          size="small"
          checked={(stored ?? "continuity") === "continuity"}
          onChange={(checked) => void apply(checked)}
          aria-label={t("nav.continuityLabel")}
        />
        {compact ? t("nav.continuityShort") : t("nav.continuityLabel")}
      </label>
    </Tooltip>
  );
}
