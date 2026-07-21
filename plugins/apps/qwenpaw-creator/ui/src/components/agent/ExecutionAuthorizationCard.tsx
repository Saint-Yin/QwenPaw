import { useState } from "react";
import { message } from "antd";
import { PlayCircle } from "lucide-react";
import type {
  ExecutionAuthorizationApproval,
  ExecutionAuthorizationView,
} from "@/contracts/creator";
import { useExecutionAuthorizationStore } from "@/store/executionAuthorizationStore";
import { creatorTargetLabel, taskKindLabel } from "@/lib/creatorPresentation";

const BUTTON_BASE =
  "rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50";
const BUTTON_PRIMARY = `${BUTTON_BASE} bg-[var(--color-accent)] text-white hover:opacity-90`;
const BUTTON_GHOST = `${BUTTON_BASE} border border-[var(--color-border)] bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]`;

export function authorizationApprovalPayload(
  authorization: ExecutionAuthorizationView,
): ExecutionAuthorizationApproval {
  return {
    authorizationToken: authorization.authorizationToken,
    provider: authorization.provider,
    model: authorization.model,
    maxCost: authorization.estimatedCost ?? 0,
    maxCandidates: authorization.maxCandidates,
  };
}

export function authorizationDetail(
  authorization: ExecutionAuthorizationView,
): string {
  const messageText = authorization.scope.message;
  if (typeof messageText === "string" && messageText.trim()) return messageText;
  const operation =
    typeof authorization.scope.operation === "string"
      ? taskKindLabel(authorization.scope.operation)
      : "高成本媒体执行";
  return `${operation} · ${creatorTargetLabel(authorization.targetRef)} · ${
    authorization.provider
  }/${authorization.model}`;
}

export default function ExecutionAuthorizationCard({
  authorization,
}: {
  authorization: ExecutionAuthorizationView;
}) {
  const approve = useExecutionAuthorizationStore((state) => state.approve);
  const decline = useExecutionAuthorizationStore((state) => state.decline);
  const [busy, setBusy] = useState(false);
  if (authorization.status !== "PENDING") return null;

  const continueRun = async () => {
    setBusy(true);
    try {
      await approve(
        authorization.id,
        authorizationApprovalPayload(authorization),
      );
      message.success("已确认，专业制作将继续");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const cancelRun = async () => {
    setBusy(true);
    try {
      await decline(authorization.id, authorization.authorizationToken);
      message.success("已取消，当前制作已终止");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article
      data-execution-authorization-card={authorization.id}
      className="rounded-xl border border-[var(--color-warning)]/50 bg-[var(--color-warning-soft)]/40 p-2.5"
    >
      <div className="flex items-start gap-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded bg-[var(--color-warning-soft)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--color-warning)]">
              <PlayCircle className="h-3 w-3" />
              生产确认
            </span>
            <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--color-text-primary)]">
              端到端生产等待确认
            </span>
          </div>
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-[var(--color-text-tertiary)]">
            {authorizationDetail(authorization)}
          </p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => void continueRun()}
          className={`flex-1 ${BUTTON_PRIMARY}`}
        >
          继续
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void cancelRun()}
          className={`flex-1 ${BUTTON_GHOST}`}
        >
          取消
        </button>
      </div>
    </article>
  );
}
