import { useCallback, useEffect, useRef } from "react";
import { useNavigationStore } from "@/store/navigationStore";

type ReviewFocusRuntime = Window & {
  __creatorReviewFocus?: (request: {
    path: string;
    query: Record<string, string>;
  }) => void;
};

interface UseReviewFieldFocusOptions {
  /** 当前页面路径（不含 query），用于忽略发往其它页面的审阅定位请求。 */
  path: string;
  /** URL 中的 field 参数；支持刷新后直接恢复定位。 */
  field: string | null;
  /** URL 中 review=1 时为 true。 */
  enabled: boolean;
  /** 同一路由、同一字段重复查看时用于重放动画。 */
  pulse: string | null;
}

const RETRY_INTERVAL_MS = 50;
const MAX_RETRIES = 40;
const FLASH_DURATION_MS = 2400;
const fallbackFlashTokens = new WeakMap<HTMLElement, number>();
let fallbackFlashSequence = 0;

/** 精确寻找字段节点，避免把 `:`、`/` 等字段路径直接拼进 CSS selector。 */
export function findCreatorFieldElement(
  field: string,
  root: ParentNode = document,
): HTMLElement | null {
  // A review operation's locator field is the RFC 6901 JSON pointer of the
  // change.  DOM fields expose that pointer via data-creator-path, plus a
  // human data-creator-field/data-review-field alias.  Match any of them so a
  // backend-derived locator (which uses the pointer) can find the node.
  return (
    Array.from(
      root.querySelectorAll<HTMLElement>(
        "[data-review-field], [data-creator-field], [data-creator-path]",
      ),
    ).find(
      (element) =>
        element.getAttribute("data-review-field") === field ||
        element.getAttribute("data-creator-field") === field ||
        element.getAttribute("data-creator-path") === field,
    ) ?? null
  );
}

/** textarea/input 不能可靠承载 ::after，定位时改为闪烁其所在内容块。 */
export function reviewFlashElementForField(
  field: string,
  root: ParentNode = document,
): HTMLElement | null {
  const fieldElement = findCreatorFieldElement(field, root);
  if (!fieldElement) return null;
  if (fieldElement.matches("textarea, input")) {
    return (
      fieldElement.closest<HTMLElement>("section") ??
      fieldElement.parentElement ??
      fieldElement
    );
  }
  return fieldElement;
}

/** Immediate same-page fallback used after AgentDock closes on “查看”. */
export function flashCreatorReviewField(
  field: string,
  root: ParentNode = document,
): HTMLElement | null {
  const target = reviewFlashElementForField(field, root);
  if (!target) return null;
  const token = ++fallbackFlashSequence;
  fallbackFlashTokens.set(target, token);
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.remove("review-flash");
  void target.offsetWidth;
  target.classList.add("review-flash");
  window.setTimeout(() => {
    if (fallbackFlashTokens.get(target) !== token) return;
    target.classList.remove("review-flash");
    fallbackFlashTokens.delete(target);
  }, FLASH_DURATION_MS);
  return target;
}

/**
 * 方案页字段级审阅定位。
 *
 * 同时消费 URL 与 navigationStore 请求，并注册 refNavigation 的即时重放入口。
 * 目标详情可能在路由切换/项目加载后才挂载，因此用短轮询代替固定延时。
 */
export function useReviewFieldFocus({
  path,
  field,
  enabled,
  pulse,
}: UseReviewFieldFocusOptions): void {
  const reviewFocusRequest = useNavigationStore((state) => state.reviewFocus);
  const requestSequenceRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const settleTimerRef = useRef<number | null>(null);
  const clearTimerRef = useRef<number | null>(null);
  const activeTargetRef = useRef<HTMLElement | null>(null);

  const clearTimers = useCallback(() => {
    if (retryTimerRef.current != null)
      window.clearTimeout(retryTimerRef.current);
    if (settleTimerRef.current != null)
      window.clearTimeout(settleTimerRef.current);
    if (clearTimerRef.current != null)
      window.clearTimeout(clearTimerRef.current);
    activeTargetRef.current?.classList.remove("review-flash");
    activeTargetRef.current = null;
    retryTimerRef.current = null;
    settleTimerRef.current = null;
    clearTimerRef.current = null;
  }, []);

  const trigger = useCallback(
    (targetField: string) => {
      clearTimers();
      const sequence = ++requestSequenceRef.current;
      let retries = 0;
      let settleChecks = 0;

      const applyFlash = (target: HTMLElement) => {
        if (clearTimerRef.current != null)
          window.clearTimeout(clearTimerRef.current);
        if (activeTargetRef.current && activeTargetRef.current !== target) {
          activeTargetRef.current.classList.remove("review-flash");
        }
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.remove("review-flash");
        void target.offsetWidth;
        target.classList.add("review-flash");
        activeTargetRef.current = target;
        clearTimerRef.current = window.setTimeout(() => {
          if (sequence === requestSequenceRef.current) {
            target.classList.remove("review-flash");
            if (activeTargetRef.current === target)
              activeTargetRef.current = null;
          }
          clearTimerRef.current = null;
        }, FLASH_DURATION_MS);
      };

      // Closing AgentDock and opening a Plan detail can replace the matching DOM
      // node after the first successful lookup. Re-check through the transition
      // window and replay only when React mounted a new target (or stripped the
      // class), so a same-route repeated “查看” remains visible.
      const verifyMountedTarget = () => {
        if (sequence !== requestSequenceRef.current) return;
        const workspaceRoot = document.querySelector<HTMLElement>(
          "[data-creator-workspace-root]",
        );
        const mountedTarget = reviewFlashElementForField(
          targetField,
          workspaceRoot ?? document,
        );
        if (
          mountedTarget &&
          (mountedTarget !== activeTargetRef.current ||
            !mountedTarget.classList.contains("review-flash"))
        ) {
          applyFlash(mountedTarget);
        }
        if (settleChecks++ < 12) {
          settleTimerRef.current = window.setTimeout(
            verifyMountedTarget,
            RETRY_INTERVAL_MS,
          );
        } else {
          settleTimerRef.current = null;
        }
      };

      const tryFocus = () => {
        if (sequence !== requestSequenceRef.current) return;
        const workspaceRoot = document.querySelector<HTMLElement>(
          "[data-creator-workspace-root]",
        );
        const target = reviewFlashElementForField(
          targetField,
          workspaceRoot ?? document,
        );
        if (!target) {
          if (retries++ < MAX_RETRIES) {
            retryTimerRef.current = window.setTimeout(
              tryFocus,
              RETRY_INTERVAL_MS,
            );
          }
          return;
        }

        retryTimerRef.current = null;
        applyFlash(target);
        settleTimerRef.current = window.setTimeout(
          verifyMountedTarget,
          RETRY_INTERVAL_MS,
        );
      };

      tryFocus();
    },
    [clearTimers],
  );

  // 直接打开/刷新带审阅 query 的方案页时也能恢复定位；pulse 变化会重放同一字段。
  useEffect(() => {
    if (enabled && field) trigger(field);
  }, [enabled, field, pulse, trigger]);

  // 跨页与同页重复“查看”都通过 reviewFocus.nonce 到达这里。
  useEffect(() => {
    if (!enabled) return;
    if (!reviewFocusRequest || reviewFocusRequest.path !== path) return;
    if (
      reviewFocusRequest.query.review !== "1" ||
      !reviewFocusRequest.query.field
    )
      return;
    trigger(reviewFocusRequest.query.field);
  }, [enabled, path, reviewFocusRequest, trigger]);

  // 与资产页/工作台保持一致，为 navigateToRef 的即时重放提供当前页面处理器。
  useEffect(() => {
    const runtime = window as ReviewFocusRuntime;
    const handler = (request: {
      path: string;
      query: Record<string, string>;
    }) => {
      if (
        !enabled ||
        request.path !== path ||
        request.query.review !== "1" ||
        !request.query.field
      )
        return;
      trigger(request.query.field);
    };
    runtime.__creatorReviewFocus = handler;
    return () => {
      if (runtime.__creatorReviewFocus === handler)
        delete runtime.__creatorReviewFocus;
    };
  }, [enabled, path, trigger]);

  useEffect(
    () => () => {
      requestSequenceRef.current += 1;
      clearTimers();
    },
    [clearTimers],
  );
}
