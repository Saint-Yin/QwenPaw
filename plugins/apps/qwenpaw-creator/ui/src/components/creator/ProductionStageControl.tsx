import { useState } from "react";
import { Modal, message } from "antd";
import { useTranslation } from "react-i18next";
import { creatorRequest, jsonBody } from "@/api/creator/client";
import { useProjectSnapshotStore } from "@/store/projectSnapshotStore";

export default function ProductionStageControl({
  projectId,
}: {
  projectId: string;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const project = useProjectSnapshotStore((state) =>
    state.projectId === projectId ? state.project : null,
  );
  const etag = useProjectSnapshotStore((state) =>
    state.projectId === projectId ? state.etag : null,
  );
  const patching = useProjectSnapshotStore(
    (state) => state.projectId === projectId && state.patching,
  );
  if (!project) return null;
  const scriptOnly = project.settings.production_stage === "script";

  const update = async (stage: "script" | "media", etag: string) => {
    setBusy(true);
    try {
      await creatorRequest(
        `/projects/${encodeURIComponent(projectId)}/production-stage`,
        {
          method: "POST",
          body: jsonBody({ stage, projectEtag: etag }),
        },
      );
      await useProjectSnapshotStore.getState().pollOnce(projectId);
    } catch (error) {
      message.error((error as Error).message || t("productionStage.failed"));
      await useProjectSnapshotStore
        .getState()
        .pollOnce(projectId)
        .catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  const changeStage = () => {
    if (!etag) return;
    const current = etag;
    if (scriptOnly) {
      Modal.confirm({
        title: t("productionStage.confirmTitle"),
        content: t("productionStage.confirmDescription"),
        okText: t("productionStage.allowMedia"),
        cancelText: t("common.cancel"),
        onOk: () => update("media", current),
      });
    } else {
      void update("script", current).catch(() => undefined);
    }
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] px-4 py-2 text-xs">
      <span>
        {t(
          scriptOnly
            ? "productionStage.scriptOnly"
            : "productionStage.mediaEnabled",
        )}
      </span>
      <button
        type="button"
        disabled={busy || patching || !etag}
        className="btn-secondary"
        onClick={changeStage}
      >
        {t(
          scriptOnly
            ? "productionStage.confirmScript"
            : "productionStage.pauseMedia",
        )}
      </button>
    </div>
  );
}
