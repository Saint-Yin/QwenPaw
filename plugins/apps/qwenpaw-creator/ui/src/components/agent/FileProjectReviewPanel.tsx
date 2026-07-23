import { useState } from "react";
import { message } from "antd";
import { Check, FileDiff, Undo2 } from "lucide-react";
import type {
  FileProjectReviewDecision,
  FileProjectReviewOperation,
  FileProjectReviewOperationDecision,
} from "@/contracts/creator";
import { useFileProjectReviewStore } from "@/store/fileProjectReviewStore";
import OnboardingHint from "@/components/onboarding/OnboardingHint";

const DECISION_LABELS: Record<FileProjectReviewOperationDecision, string> = {
  PENDING: "待审",
  ACCEPTED: "已保留",
  REJECTED: "已撤销",
  REVISED: "已修订",
  SUPERSEDED_BY_USER_EDIT: "已被用户编辑替代",
};

function formattedValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ReviewValue({ label, value }: { label: string; value: unknown }) {
  const text = formattedValue(value);
  const long = text.length > 240 || text.split("\n").length > 8;
  const preview = text.length > 120 ? `${text.slice(0, 120)}…` : text;
  return (
    <div className="min-w-0 rounded-md bg-[var(--color-bg-secondary)] p-2">
      <p className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">
        {label}
      </p>
      {long ? (
        <details>
          <summary className="cursor-pointer list-none text-[10px] leading-4 text-[var(--color-text-secondary)]">
            <span className="line-clamp-3 whitespace-pre-wrap break-all">
              {preview}
            </span>
            <span className="mt-1 inline-block text-[var(--color-accent)]">
              展开完整值
            </span>
          </summary>
          <pre className="mt-1 max-h-52 overflow-auto whitespace-pre-wrap break-all text-[10px] leading-4 text-[var(--color-text-secondary)]">
            {text}
          </pre>
        </details>
      ) : (
        <pre className="whitespace-pre-wrap break-all text-[10px] leading-4 text-[var(--color-text-secondary)]">
          {text}
        </pre>
      )}
    </div>
  );
}

function operationLocation(operation: FileProjectReviewOperation): string {
  return (
    operation.json_pointer ??
    (operation.file_id ? `file:${operation.file_id}` : null) ??
    operation.target_ref ??
    "unknown"
  );
}

export default function FileProjectReviewPanel({
  projectId,
}: {
  projectId: string;
}) {
  const storeProjectId = useFileProjectReviewStore((state) => state.projectId);
  const review = useFileProjectReviewStore((state) => state.review);
  const decisionInFlight = useFileProjectReviewStore(
    (state) => state.decisionInFlight,
  );
  const syncError = useFileProjectReviewStore((state) => state.syncError);
  const decide = useFileProjectReviewStore((state) => state.decide);
  const [localBusy, setLocalBusy] = useState(false);

  if (storeProjectId !== projectId || !review || review.status !== "PENDING")
    return null;
  const pending = review.operations.filter(
    (operation) => operation.decision === "PENDING",
  );
  const busy = decisionInFlight || localBusy;

  const submit = async (
    operations: FileProjectReviewOperation[],
    decision: FileProjectReviewDecision,
  ) => {
    if (operations.length === 0) return;
    setLocalBusy(true);
    try {
      await decide(
        projectId,
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
            <FileDiff className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            文件项目修改
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
            Keep all
          </button>
          <button
            type="button"
            disabled={busy || pending.length === 0}
            onClick={() => void submit(pending, "REJECT")}
            className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[10px] font-medium text-[var(--color-text-secondary)] disabled:opacity-50"
          >
            Undo all
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

      <ul className="mt-2 space-y-2">
        {review.operations.map((operation) => {
          const operationPending = operation.decision === "PENDING";
          const location = operationLocation(operation);
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
                {operationPending && (
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      aria-label={`Keep ${location}`}
                      disabled={busy}
                      onClick={() => void submit([operation], "ACCEPT")}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] disabled:opacity-50"
                    >
                      <Check className="h-3 w-3" />
                      Keep
                    </button>
                    <button
                      type="button"
                      aria-label={`Undo ${location}`}
                      disabled={busy}
                      onClick={() => void submit([operation], "REJECT")}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-danger)] disabled:opacity-50"
                    >
                      <Undo2 className="h-3 w-3" />
                      Undo
                    </button>
                  </div>
                )}
              </div>
              <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                <ReviewValue label="Before" value={operation.before} />
                <ReviewValue label="After" value={operation.after} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
