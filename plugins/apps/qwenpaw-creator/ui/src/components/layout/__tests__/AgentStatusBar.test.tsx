import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import AgentStatusBar from "@/components/layout/AgentStatusBar";
import type { CreatorSessionStatus, TaskStatus } from "@/contracts/creator";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { installMockFetch } from "@/test/mockFetch";

function setSession(status: CreatorSessionStatus) {
  useCreatorSessionStore.setState({
    session: {
      id: "session-1",
      projectId: "p1",
      status,
      lastMessageSeq: 0,
      lastConsumedMessageSeq: 0,
      lastEventSeq: 0,
    },
    agentStatusBar: {
      progress: {
        phase: "visual_development",
        label: "正在制作",
        sourceEventSeq: 1,
        updatedAt: "now",
      },
      activity: { label: "镜头生成中", runningTaskCount: 1 },
      badges: [],
    },
  });
}

function task(id: string, status: TaskStatus) {
  return {
    id,
    projectId: "p1",
    transactionId: "tx1",
    specialistRunId: "run1",
    kind: "r2v_generation" as const,
    targetRef: `element:${id}`,
    status,
    progress: null,
    resultRefs: [],
  };
}

describe("AgentStatusBar origin/main state projection", () => {
  beforeEach(() => {
    useAgentDockUiStore.getState().reset();
    useCreatorSessionStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
  });

  it("renders the authoritative progress once without secondary status pills", () => {
    setSession("RUNNING");
    render(<AgentStatusBar />);

    expect(screen.getByText(/正在制作/)).toBeInTheDocument();
    expect(screen.queryByText("端到端生产中")).not.toBeInTheDocument();
    expect(screen.queryByText("执行中")).not.toBeInTheDocument();
    expect(screen.queryByText("镜头生成中")).not.toBeInTheDocument();
  });

  it("keeps the global hard-stop available while the AgentDock is closed", () => {
    setSession("RUNNING");
    const { container } = render(<AgentStatusBar />);
    // Apply the state after mount as well so late cleanup from a previously
    // mounted Project shell cannot race this isolated projection assertion.
    act(() => useAgentDockUiStore.getState().setOpen(false));

    const statusBar = container.querySelector("[data-agent-status-bar]")!;
    expect(
      within(statusBar as HTMLElement).getByRole("button", {
        name: "打开 Agent",
      }),
    ).toBeInTheDocument();
    expect(
      within(statusBar as HTMLElement).getByRole("button", {
        name: "停止所有 Agent",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("端到端生产中")).not.toBeInTheDocument();
    expect(screen.queryByText("执行中")).not.toBeInTheDocument();
    expect(screen.queryByText("镜头生成中")).not.toBeInTheDocument();
    expect(statusBar.querySelector(".border-l")).not.toBeInTheDocument();

    fireEvent.click(
      within(statusBar as HTMLElement).getByRole("button", {
        name: "打开 Agent",
      }),
    );
    expect(useAgentDockUiStore.getState().open).toBe(true);
    expect(
      within(statusBar as HTMLElement).getByRole("button", {
        name: "停止所有 Agent",
      }),
    ).toBeInTheDocument();
    expect(statusBar.querySelector(".border-l")).not.toBeInTheDocument();
  });

  it("exposes a global stop control and interrupts the whole Creator Session", async () => {
    const { calls } = installMockFetch([
      {
        match: "/projects/p1/interrupt",
        method: "POST",
        response: {
          json: {
            creatorSessionId: "session-1",
            status: "INTERRUPT_REQUESTED",
            stopRequested: true,
          },
        },
      },
    ]);
    setSession("RUNNING");
    render(<AgentStatusBar />);

    fireEvent.click(screen.getByRole("button", { name: "停止所有 Agent" }));

    expect(useCreatorSessionStore.getState().session?.status).toBe(
      "INTERRUPT_REQUESTED",
    );
    await waitFor(() =>
      expect(
        calls.some((call) => call.url.includes("/projects/p1/interrupt")),
      ).toBe(true),
    );
    expect(
      calls.find((call) => call.url.includes("/projects/p1/interrupt"))?.method,
    ).toBe("POST");
  });

  it("maps authorization wait to the origin decision-center interaction", () => {
    setSession("WAITING_EXECUTION_AUTH");
    useCreatorSessionStore.setState((state) => ({
      agentStatusBar: {
        ...state.agentStatusBar!,
        progress: { ...state.agentStatusBar!.progress, label: "等待执行授权" },
        badges: [
          { kind: "execution_authorization", label: "等待执行授权", count: 1 },
        ],
      },
    }));
    render(<AgentStatusBar />);

    fireEvent.click(screen.getByText("待处理 1"));
    expect(useAgentDockUiStore.getState().tab).toBe("review");
  });

  it("does not present stale runtime activity as running while waiting for user input", () => {
    setSession("WAITING_USER_INPUT");
    render(<AgentStatusBar />);

    expect(screen.queryByText("镜头生成中")).not.toBeInTheDocument();
    expect(screen.getByText("继续输入")).toBeInTheDocument();
  });

  it("does not reinterpret durable progress into client-side background or partial states", () => {
    setSession("WAITING_RUNTIME");
    useCreatorSessionStore.setState((state) => ({
      agentStatusBar: {
        ...state.agentStatusBar!,
        progress: {
          ...state.agentStatusBar!.progress,
          label: "素材理解等待工具结果",
        },
      },
    }));
    const { rerender } = render(<AgentStatusBar />);
    expect(screen.getByText(/素材理解等待工具结果/)).toBeInTheDocument();
    expect(screen.queryByText("后台等待中")).not.toBeInTheDocument();

    setSession("IDLE");
    useCreatorTaskViewStore.setState({
      tasks: [task("ok", "SUCCEEDED"), task("bad", "FAILED")],
    });
    rerender(<AgentStatusBar />);
    expect(screen.queryByText("部分完成")).not.toBeInTheDocument();
    expect(screen.queryByText("后台等待中")).not.toBeInTheDocument();
  });

  it("shows measurable runtime task progress in the authoritative label", () => {
    setSession("RUNNING");
    useCreatorSessionStore.setState((state) => ({
      agentStatusBar: {
        ...state.agentStatusBar!,
        progress: {
          ...state.agentStatusBar!.progress,
          phase: "source_ingest",
          label: "附件入库中 · 42%",
          completed: 42,
          total: 100,
        },
        activity: { label: "附件入库中 · 42%", runningTaskCount: 1 },
      },
    }));
    render(<AgentStatusBar />);

    expect(screen.getByText(/附件入库中 · 42%/)).toBeInTheDocument();
    expect(screen.queryByText("镜头生成中")).not.toBeInTheDocument();
  });

  it("sums review and authorization badges into the origin pending action", () => {
    setSession("IDLE");
    useCreatorSessionStore.setState((state) => ({
      agentStatusBar: {
        ...state.agentStatusBar!,
        badges: [
          { kind: "review", label: "待审", count: 2 },
          { kind: "execution_authorization", label: "生产确认", count: 1 },
          { kind: "error", label: "不计数", count: 8 },
        ],
      },
    }));
    render(<AgentStatusBar />);

    fireEvent.click(screen.getByText("待处理 3"));
    expect(useAgentDockUiStore.getState().tab).toBe("review");
  });
});
