// @vitest-environment jsdom

import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  flashCreatorReviewField,
  useReviewFieldFocus,
} from "@/routing/reviewFocus";
import { useNavigationStore } from "@/store/navigationStore";

const PATH = "/project/p1/plan";
const FIELD = "unit:unit-1/storyText";

function Harness({
  field = FIELD,
  showTarget = true,
}: {
  field?: string;
  showTarget?: boolean;
}) {
  useReviewFieldFocus({ path: PATH, field, enabled: true, pulse: "1" });
  return showTarget ? <div data-creator-field={field}>原文</div> : null;
}

function MultiFieldHarness() {
  useReviewFieldFocus({ path: PATH, field: FIELD, enabled: true, pulse: "1" });
  return (
    <>
      <div data-creator-field={FIELD}>原文 A</div>
      <div data-creator-field="unit:unit-1/videoPrompt">原文 B</div>
    </>
  );
}

function DockCollisionHarness() {
  useReviewFieldFocus({ path: PATH, field: FIELD, enabled: true, pulse: "1" });
  return (
    <>
      <aside data-agent-dock>
        <div data-creator-field={FIELD}>AgentDock diff</div>
      </aside>
      <main data-creator-workspace-root>
        <div data-creator-field={FIELD}>工作区正文</div>
      </main>
    </>
  );
}

describe("useReviewFieldFocus", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useNavigationStore.setState({ reviewFocus: null });
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("URL 审阅定位会滚动并闪烁字段", () => {
    const { container } = render(<Harness />);
    const target = container.querySelector<HTMLElement>(
      "[data-creator-field]",
    )!;
    expect(target).toHaveClass("review-flash");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(2400));
    expect(target).not.toHaveClass("review-flash");
  });

  it("AgentDock 关闭后的同页兜底会立即重放字段闪烁", () => {
    const { container } = render(<div data-creator-field={FIELD}>原文</div>);
    const target = container.querySelector<HTMLElement>(
      "[data-creator-field]",
    )!;

    expect(flashCreatorReviewField(FIELD, container)).toBe(target);
    expect(target).toHaveClass("review-flash");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(2400));
    expect(target).not.toHaveClass("review-flash");
  });

  it("同名字段同时存在时只定位工作区，不会闪烁 AgentDock", () => {
    const { container } = render(<DockCollisionHarness />);
    const dockTarget = container.querySelector<HTMLElement>(
      "[data-agent-dock] [data-creator-field]",
    )!;
    const workspaceTarget = container.querySelector<HTMLElement>(
      "[data-creator-workspace-root] [data-creator-field]",
    )!;

    expect(workspaceTarget).toHaveClass("review-flash");
    expect(dockTarget).not.toHaveClass("review-flash");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("同一字段的重复 reviewFocus 请求会重放定位", () => {
    render(<Harness />);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);

    act(() => {
      useNavigationStore.getState().setReviewFocus({
        path: PATH,
        ref: "unit:unit-1",
        query: { review: "1", field: FIELD, reviewPulse: "2" },
      });
    });
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(2);

    act(() => {
      useNavigationStore.getState().setReviewFocus({
        path: PATH,
        ref: "unit:unit-1",
        query: { review: "1", field: FIELD, reviewPulse: "3" },
      });
    });
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(3);
  });

  it("详情节点延迟挂载时会重试，不依赖固定 360ms", () => {
    const { container, rerender } = render(<Harness showTarget={false} />);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(400));
    rerender(<Harness showTarget />);
    act(() => vi.advanceTimersByTime(50));

    expect(container.querySelector("[data-creator-field]")).toHaveClass(
      "review-flash",
    );
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("切换查看字段会清理上一个目标的闪烁类", () => {
    const { container } = render(<MultiFieldHarness />);
    const first = container.querySelector<HTMLElement>(
      `[data-creator-field="${FIELD}"]`,
    )!;
    const second = container.querySelector<HTMLElement>(
      '[data-creator-field="unit:unit-1/videoPrompt"]',
    )!;
    expect(first).toHaveClass("review-flash");

    act(() => {
      useNavigationStore.getState().setReviewFocus({
        path: PATH,
        ref: "unit:unit-1",
        query: {
          review: "1",
          field: "unit:unit-1/videoPrompt",
          reviewPulse: "2",
        },
      });
    });

    expect(first).not.toHaveClass("review-flash");
    expect(second).toHaveClass("review-flash");
  });
});
