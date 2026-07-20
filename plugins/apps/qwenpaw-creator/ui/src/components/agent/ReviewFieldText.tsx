/**
 * Origin-compatible Agent field diff backed by the sealed Review Manifest.
 *
 * The public component API and visible DOM intentionally match origin/main;
 * only the authority changed from local edit state to immutable review
 * operations and their lazily loaded before/after content.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { message } from "antd";
import { CircleCheck, Undo2 } from "lucide-react";
import type { ReviewDecisionGroup } from "@/contracts/creator";
import type { ReviewOperation } from "@/contracts/creator";
import { useReviewManifestStore } from "@/store/reviewManifestStore";

export interface DiffSeg {
  type: "equal" | "del" | "add";
  text: string;
}

const MAX_DIFF_CHAR_CELLS = 2_000_000;
const ReviewFocusPulseContext = createContext<{
  field: string | null;
  pulse: string | null;
}>({ field: null, pulse: null });

export function ReviewFocusPulseProvider({
  field,
  pulse,
  children,
}: {
  field: string | null;
  pulse: string | null;
  children: ReactNode;
}) {
  return (
    <ReviewFocusPulseContext.Provider value={{ field, pulse }}>
      {children}
    </ReviewFocusPulseContext.Provider>
  );
}

function diffTokens(value: string): string[] {
  return Array.from(value);
}

/** Character LCS with prefix/suffix trimming so long paragraphs expose exact edit points. */
export function diffSegments(before: string, after: string): DiffSeg[] {
  const segments: DiffSeg[] = [];
  const push = (type: DiffSeg["type"], text: string) => {
    if (!text) return;
    const last = segments.at(-1);
    if (last?.type === type) last.text += text;
    else segments.push({ type, text });
  };
  if (before === after) {
    push("equal", before);
    return segments;
  }
  const beforeTokens = diffTokens(before);
  const afterTokens = diffTokens(after);
  let prefix = 0;
  while (
    prefix < beforeTokens.length &&
    prefix < afterTokens.length &&
    beforeTokens[prefix] === afterTokens[prefix]
  )
    prefix += 1;
  let suffix = 0;
  while (
    suffix < beforeTokens.length - prefix &&
    suffix < afterTokens.length - prefix &&
    beforeTokens[beforeTokens.length - 1 - suffix] ===
      afterTokens[afterTokens.length - 1 - suffix]
  )
    suffix += 1;
  push("equal", beforeTokens.slice(0, prefix).join(""));
  const left = beforeTokens.slice(prefix, beforeTokens.length - suffix);
  const right = afterTokens.slice(prefix, afterTokens.length - suffix);
  const m = left.length;
  const n = right.length;
  if (m === 0 || n === 0 || m * n > MAX_DIFF_CHAR_CELLS) {
    push("del", left.join(""));
    push("add", right.join(""));
    push(
      "equal",
      suffix ? beforeTokens.slice(beforeTokens.length - suffix).join("") : "",
    );
    return segments;
  }
  const dp: Uint32Array[] = Array.from(
    { length: m + 1 },
    () => new Uint32Array(n + 1),
  );
  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      dp[i][j] =
        left[i] === right[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (left[i] === right[j]) {
      push("equal", left[i]);
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push("del", left[i]);
      i += 1;
    } else {
      push("add", right[j]);
      j += 1;
    }
  }
  while (i < m) {
    push("del", left[i]);
    i += 1;
  }
  while (j < n) {
    push("add", right[j]);
    j += 1;
  }
  push(
    "equal",
    suffix ? beforeTokens.slice(beforeTokens.length - suffix).join("") : "",
  );
  return segments;
}

interface SemanticField {
  scope: "section" | "unit" | "shot";
  ownerId: string;
  shotId?: string;
  field: string;
}

const SECTION_FIELD_LEAVES: Record<string, string[]> = {
  title: ["title.txt"],
  summary: ["summary.md"],
  pacing: ["pacing.md"],
  narrative: ["narrative.md"],
  script: ["script.md"],
  constraints: ["constraints.md"],
  transition: ["transition.md"],
  transitionNote: ["transition.md"],
  duration: ["duration-budget.txt"],
  durationBudget: ["duration-budget.txt"],
  dialogue: ["dialogue.md"],
};

const UNIT_FIELD_SUFFIXES: Record<string, string[]> = {
  title: ["title.txt"],
  goal: ["production/edit/intent.md"],
  storyText: ["narrative.md"],
  narrative: ["narrative.md"],
  duration: ["duration.txt"],
  storyboardPrompt: ["production/r2v/storyboard/prompt.md"],
  videoPrompt: ["production/r2v/video/prompt.md"],
  sceneRef: ["refs/scene.ref"],
};

const SHOT_FIELD_LEAVES: Record<string, string[]> = {
  description: ["description.md"],
  cameraDescription: ["camera-source.md"],
  cameraSource: ["camera-source.md"],
  camera: ["camera.md"],
  framing: ["camera.md"],
  dialogue: ["dialogue.md"],
  duration: ["duration.txt"],
};

function semanticField(field: string): SemanticField | null {
  const shot = /^unit:([^/]+)\/shot:([^/]+)\/([^/]+)$/.exec(field);
  if (shot)
    return { scope: "shot", ownerId: shot[1], shotId: shot[2], field: shot[3] };
  const entity = /^(section|unit):([^/]+)\/([^/]+)$/.exec(field);
  if (!entity) return null;
  return {
    scope: entity[1] as "section" | "unit",
    ownerId: entity[2],
    field: entity[3],
  };
}

function pathSegmentMatchesId(
  segment: string | undefined,
  id: string,
): boolean {
  if (!segment) return false;
  let decoded = segment;
  try {
    decoded = decodeURIComponent(segment);
  } catch {
    // Workspace paths normally contain raw stable ids; malformed escaping is not a match.
  }
  return (
    decoded === id ||
    decoded.includes(`--${id}--`) ||
    decoded.endsWith(`--${id}`)
  );
}

function pathHasEntity(
  path: string,
  collection: "sections" | "units" | "shots",
  id: string,
): boolean {
  const parts = path.split("/").filter(Boolean);
  const index = parts.lastIndexOf(collection);
  return index >= 0 && pathSegmentMatchesId(parts[index + 1], id);
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
  const sparseParts = segment.split("--");
  return sparseParts.length > 1 ? sparseParts[1] || null : segment;
}

function endsWithAny(path: string, suffixes: string[]): boolean {
  return suffixes.some(
    (suffix) => path === suffix || path.endsWith(`/${suffix}`),
  );
}

function targetMatches(operation: ReviewOperation, targetRef: string): boolean {
  return (
    operation.targetRef === targetRef ||
    operation.targetRef.startsWith(`${targetRef}/`)
  );
}

/**
 * Maps the semantic field ids retained by origin/main Plan DOM to the new
 * text-first workspace operation paths. This intentionally lists every
 * supported field instead of using fuzzy basename matching across entities.
 */
export function reviewFieldMatchesOperation(
  field: string,
  operation: ReviewOperation,
): boolean {
  if (operation.path === field || operation.uiLocator?.field === field)
    return true;
  const semantic = semanticField(field);
  if (!semantic) return false;
  const paths = [operation.path, operation.uiLocator?.field].filter(
    (value): value is string => Boolean(value),
  );
  if (paths.length === 0) return false;

  if (semantic.scope === "section") {
    const suffixes = SECTION_FIELD_LEAVES[semantic.field];
    if (!suffixes) return false;
    return paths.some(
      (path) =>
        endsWithAny(path, suffixes) &&
        (pathHasEntity(path, "sections", semantic.ownerId) ||
          targetMatches(operation, `section:${semantic.ownerId}`)),
    );
  }

  if (semantic.scope === "unit") {
    const suffixes = UNIT_FIELD_SUFFIXES[semantic.field];
    if (!suffixes) return false;
    return paths.some(
      (path) =>
        endsWithAny(path, suffixes) &&
        (pathHasEntity(path, "units", semantic.ownerId) ||
          targetMatches(operation, `unit:${semantic.ownerId}`)),
    );
  }

  const suffixes = SHOT_FIELD_LEAVES[semantic.field];
  if (!suffixes || !semantic.shotId) return false;
  return paths.some(
    (path) =>
      endsWithAny(path, suffixes) &&
      pathHasEntity(path, "shots", semantic.shotId) &&
      (pathHasEntity(path, "units", semantic.ownerId) ||
        targetMatches(operation, `unit:${semantic.ownerId}`) ||
        targetMatches(operation, `shot:${semantic.shotId}`)),
  );
}

function refId(
  targetRef: string,
  kind: "section" | "unit" | "shot",
): string | null {
  const prefix = `${kind}:`;
  return targetRef.startsWith(prefix)
    ? targetRef.slice(prefix.length).split("/", 1)[0] || null
    : null;
}

/** Reverse projection used by “查看” so workspace paths focus origin Plan fields. */
export function reviewFieldForOperation(
  operation: ReviewOperation,
): string | null {
  for (const candidate of [operation.uiLocator?.field, operation.path]) {
    if (candidate && semanticField(candidate)) return candidate;
  }
  const path = operation.path ?? operation.uiLocator?.field;
  if (!path) return null;

  const shotId =
    refId(operation.targetRef, "shot") ?? entityIdFromPath(path, "shots");
  if (shotId && path.includes("/shots/")) {
    const unitId =
      refId(operation.targetRef, "unit") ?? entityIdFromPath(path, "units");
    if (!unitId) return null;
    const field = endsWithAny(path, ["description.md"])
      ? "description"
      : endsWithAny(path, ["camera-source.md", "camera.md"])
      ? "cameraDescription"
      : endsWithAny(path, ["dialogue.md"])
      ? "dialogue"
      : endsWithAny(path, ["duration.txt"])
      ? "duration"
      : null;
    return field ? `unit:${unitId}/shot:${shotId}/${field}` : null;
  }

  const unitId =
    refId(operation.targetRef, "unit") ?? entityIdFromPath(path, "units");
  if (unitId && path.includes("/units/")) {
    const field = endsWithAny(path, ["production/edit/intent.md"])
      ? "goal"
      : endsWithAny(path, ["production/r2v/storyboard/prompt.md"])
      ? "storyboardPrompt"
      : endsWithAny(path, ["production/r2v/video/prompt.md"])
      ? "videoPrompt"
      : endsWithAny(path, ["refs/scene.ref"])
      ? "sceneRef"
      : endsWithAny(path, ["title.txt"])
      ? "title"
      : endsWithAny(path, ["narrative.md"])
      ? "storyText"
      : endsWithAny(path, ["duration.txt"])
      ? "duration"
      : null;
    return field ? `unit:${unitId}/${field}` : null;
  }

  const sectionId =
    refId(operation.targetRef, "section") ?? entityIdFromPath(path, "sections");
  if (!sectionId) return null;
  const field = endsWithAny(path, ["title.txt"])
    ? "title"
    : endsWithAny(path, ["summary.md"])
    ? "summary"
    : endsWithAny(path, ["pacing.md"])
    ? "pacing"
    : endsWithAny(path, ["narrative.md"])
    ? "narrative"
    : endsWithAny(path, ["script.md"])
    ? "script"
    : endsWithAny(path, ["constraints.md"])
    ? "constraints"
    : endsWithAny(path, ["transition.md"])
    ? "transitionNote"
    : endsWithAny(path, ["duration-budget.txt"])
    ? "durationBudget"
    : endsWithAny(path, ["dialogue.md"])
    ? "dialogue"
    : null;
  return field ? `section:${sectionId}/${field}` : null;
}

function useReviewFieldState(field: string): {
  segs: DiffSeg[] | null;
  group: ReviewDecisionGroup | null;
} {
  const manifest = useReviewManifestStore((state) => state.manifest);
  const operationContents = useReviewManifestStore(
    (state) => state.operationContents,
  );
  const loadOperationContent = useReviewManifestStore(
    (state) => state.loadOperationContent,
  );
  const review = useMemo(() => {
    if (!manifest) return { operation: null, group: null };
    for (const group of manifest.decisionGroups) {
      if (group.decision !== "PENDING") continue;
      const operationIds = new Set(group.operationIds);
      const operation = manifest.operations.find(
        (item) =>
          operationIds.has(item.id) && reviewFieldMatchesOperation(field, item),
      );
      if (operation) return { operation, group };
    }
    return { operation: null, group: null };
  }, [field, manifest]);
  const { operation, group } = review;

  useEffect(() => {
    if (operation && !operationContents[operation.id]) {
      void loadOperationContent(operation.id).catch(() => undefined);
    }
  }, [loadOperationContent, operation, operationContents]);

  const segs = useMemo(() => {
    if (!operation) return null;
    const content = operationContents[operation.id];
    if (!content) return null;
    const before = content.before ?? "";
    const after = content.after ?? "";
    if (before === after) return null;
    return diffSegments(before, after);
  }, [operation, operationContents]);
  return { segs, group };
}

export function useReviewFieldDiff(field: string): DiffSeg[] | null {
  return useReviewFieldState(field).segs;
}

function DiffSegments({ segs }: { segs: DiffSeg[] }) {
  return (
    <>
      {segs.map((seg, index) => {
        if (seg.type === "equal") return <span key={index}>{seg.text}</span>;
        if (seg.type === "del")
          return (
            <span key={index} className="agent-diff-del">
              {seg.text}
            </span>
          );
        return (
          <span key={index} className="agent-diff-add">
            {seg.text}
          </span>
        );
      })}
    </>
  );
}

function InlineReviewActions({
  field,
  group,
}: {
  field: string;
  group: ReviewDecisionGroup;
}) {
  const [busy, setBusy] = useState<"ACCEPT" | "REJECT" | null>(null);
  const decide = async (decision: "ACCEPT" | "REJECT") => {
    const current = useReviewManifestStore
      .getState()
      .manifest?.decisionGroups.find(
        (item) => item.id === group.id && item.decision === "PENDING",
      );
    if (!current) return;
    setBusy(decision);
    try {
      await useReviewManifestStore.getState().decide(current.id, {
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
    <span
      className="ml-2 inline-flex items-center gap-1 align-middle"
      data-review-inline-actions
    >
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => void decide("ACCEPT")}
        aria-label={`接受 ${field} 修改`}
        className="inline-flex items-center gap-1 rounded border border-[var(--color-accent)]/25 bg-[var(--color-bg-card)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] disabled:opacity-50"
      >
        <CircleCheck className="h-3 w-3" />
        接受
      </button>
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => void decide("REJECT")}
        aria-label={`撤销 ${field} 修改`}
        className="inline-flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-secondary)] hover:border-[var(--color-danger)]/35 hover:text-[var(--color-danger)] disabled:opacity-50"
      >
        <Undo2 className="h-3 w-3" />
        撤销
      </button>
    </span>
  );
}

export default function ReviewFieldText({
  field,
  children,
}: {
  field: string;
  children: ReactNode;
}) {
  const { segs, group } = useReviewFieldState(field);
  const focus = useContext(ReviewFocusPulseContext);
  const pulse = focus.field === field ? focus.pulse : null;
  const targetRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (pulse && segs)
      targetRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
  }, [pulse, segs]);
  if (!segs) return <>{children}</>;
  return (
    <span
      ref={targetRef}
      key={pulse || undefined}
      data-agent-diff
      data-review-field={field}
      data-review-field-label="待审改动"
      data-review-pulse={pulse || undefined}
      className={pulse ? "review-flash-query" : undefined}
    >
      <DiffSegments segs={segs} />
      {group && <InlineReviewActions field={field} group={group} />}
    </span>
  );
}

export function ReviewDiffPreview({
  field,
  label,
  focusTarget = false,
}: {
  field: string;
  label?: string;
  focusTarget?: boolean;
}) {
  const { segs, group } = useReviewFieldState(field);
  const focus = useContext(ReviewFocusPulseContext);
  const pulse = focus.field === field ? focus.pulse : null;
  const targetRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (pulse && segs)
      targetRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
  }, [pulse, segs]);
  if (!segs) return null;
  const focusAttrs = {
    "data-review-field": field,
    "data-review-field-label": label ?? "待审改动",
    ...(focusTarget ? { "data-review-focus-primary": "true" } : {}),
  };
  return (
    <div
      ref={targetRef}
      key={pulse || undefined}
      {...focusAttrs}
      data-review-pulse={pulse || undefined}
      className={`mt-2 rounded-lg border border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)]/45 px-2.5 py-2${
        pulse ? " review-flash-query" : ""
      }`}
      data-agent-diff-preview
    >
      {label && (
        <p className="mb-1 text-[10px] font-semibold text-[var(--color-text-tertiary)]">
          {label}
        </p>
      )}
      <p className="whitespace-pre-wrap break-words text-xs leading-5 text-[var(--color-text-primary)]">
        <DiffSegments segs={segs} />
      </p>
      {group && (
        <div className="mt-2 flex justify-end">
          <InlineReviewActions field={field} group={group} />
        </div>
      )}
    </div>
  );
}
