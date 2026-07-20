import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentDock from "@/components/agent/AgentDock";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";
import { useFileProjectReviewStore } from "@/store/fileProjectReviewStore";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import { useWorkspaceViewStore } from "@/store/workspaceViewStore";
import { installMockFetch } from "@/test/mockFetch";
import type {
  FileProjectReviewRecord,
  ReviewDecisionGroup,
  ReviewManifest,
  ReviewOperation,
} from "@/contracts/creator";

const reviewGroup: ReviewDecisionGroup = {
  id: "g1",
  title: "Unit 文案",
  operationIds: ["op1"],
  groupingReasons: ["硬依赖闭包"],
  decisionToken: "token-1",
  decision: "PENDING",
};

const reviewOperation: ReviewOperation = {
  id: "op1",
  decisionGroupId: "g1",
  mutationIds: ["m1"],
  kind: "update",
  targetRef: "unit:u1",
  artifactKind: "markdown",
  path: "story/sections/s1/units/u1/narrative.md",
  beforeVersionRef: "workspace-content://before@ov1",
  afterVersionRef: "workspace-content://after@ov2",
  causalRefs: [],
  source: "user_direct",
  actorRunIds: [],
  triggerMessageSeqs: [1],
  dependencyReasons: [],
  uiLocator: { page: "workbench", unitId: "u1" },
};

function reviewManifest(
  group: ReviewDecisionGroup = reviewGroup,
): ReviewManifest {
  return {
    id: "review-1",
    transactionId: "tx1",
    reviewRound: 1,
    baseRevisionId: "revision-a",
    reviewRevisionId: "revision-b",
    manifestToken: "manifest-token",
    summary: "",
    journalSeqRange: { fromExclusive: 0, toInclusive: 1 },
    decisionGroups: [group],
    operations: [reviewOperation],
    createdArtifactVersionRefs: [],
    mediaComparisons: [],
    integrationPreviews: [],
    createdAt: "2026-07-11T00:00:00Z",
  };
}

function fileProjectReview(): FileProjectReviewRecord {
  return {
    review_id: "file-review-1",
    round_id: "round-1",
    request_id: "request-1",
    request_message_seq: 1,
    interrupted_run_id: "run-1",
    baseline_generation: 1,
    baseline_etag: "base-1",
    candidate_generation: 2,
    candidate_etag: "candidate-2",
    decision_token: "file-token-1",
    status: "PENDING",
    operations: [
      {
        kind: "update",
        json_pointer: "/story/title",
        file_id: null,
        target_ref: null,
        before_hash: "before",
        after_hash: "after",
        before: "旧标题",
        after: "新标题",
        operation_id: "file-operation-1",
        ui_locator: {},
        decision: "PENDING",
      },
    ],
    created_at: "2026-07-15T00:00:00Z",
    updated_at: "2026-07-15T00:00:01Z",
  };
}

function renderDock() {
  return render(
    <MemoryRouter initialEntries={["/project/p1/plan"]}>
      <Routes>
        <Route path="/project/:id/plan" element={<AgentDock />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AgentDock origin/main visible fidelity", () => {
  beforeEach(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      },
    });
    useAgentDockUiStore.getState().reset();
    useCreatorInteractionStore.getState().reset();
    useFileProjectReviewStore.getState().reset();
    useReviewManifestStore.getState().reset();
    useCreatorTaskViewStore.getState().reset();
    useWorkspaceViewStore.getState().reset("p1");
    useCreatorSessionStore.getState().reset();
    useCreatorSessionStore.setState({
      projectId: "p1",
      session: {
        id: "session-1",
        projectId: "p1",
        status: "IDLE",
        lastMessageSeq: 0,
        lastConsumedMessageSeq: 0,
        lastEventSeq: 0,
      },
      conversations: [
        {
          conversationId: "conversation-1",
          title: "默认对话",
          isDefault: true,
          createdAt: "2026-07-11T00:00:00Z",
        },
      ],
      activeConversationId: "conversation-1",
      messages: [],
      queuedUi: [],
      events: [],
      hasMoreMessages: false,
      agentStatusBar: null,
    });
  });

  it("matches the right-side closed trigger and exact 440x620 floating shell", async () => {
    useAgentDockUiStore.getState().setOpen(false);
    renderDock();
    const trigger = screen.getByRole("button", { name: "打开 Agent" });
    expect(trigger).toHaveClass(
      "fixed",
      "bottom-5",
      "right-5",
      "h-11",
      "w-11",
      "rounded-full",
      "z-40",
    );

    fireEvent.click(trigger);
    const dock = document.querySelector<HTMLElement>("[data-agent-dock]")!;
    await waitFor(() =>
      expect(dock).toHaveStyle({ width: "440px", height: "620px" }),
    );
    expect(dock).toHaveAttribute("data-agent-dock-width", "440");
    expect(dock).toHaveAttribute("data-agent-dock-height", "620");
    expect(dock).toHaveClass(
      "agent-dock-enter",
      "fixed",
      "bottom-5",
      "right-5",
      "z-40",
      "rounded-2xl",
      "backdrop-blur-xl",
    );
    expect(screen.getByText("Creator Agent")).toBeInTheDocument();
    expect(
      screen.getByText("未绑定上下文，作用于整个项目"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "审阅与决策中心" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新对话" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "历史聊天" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "工作区事实" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "最大化面板" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "关闭 Agent 面板" }),
    ).toBeInTheDocument();
    expect(document.querySelector('[title="拖拽调整高度"]')).toHaveClass(
      "cursor-ns-resize",
    );
    expect(document.querySelector('[title="拖拽调整宽度"]')).toHaveClass(
      "cursor-ew-resize",
    );
    expect(document.querySelector('[title="拖拽调整大小"]')).toHaveClass(
      "cursor-nwse-resize",
    );
    expect(
      screen.getByRole("textbox", { name: "输入修改意图，@ 可引用对象…" }),
    ).toHaveClass("min-h-[32px]", "max-h-24");
  });

  it("automatically opens every newly sealed review round in the decision center", async () => {
    useAgentDockUiStore.getState().setOpen(false);
    renderDock();
    expect(useAgentDockUiStore.getState().open).toBe(false);

    act(() => {
      useReviewManifestStore.setState({
        projectId: "p1",
        transactionId: "tx1",
        manifest: reviewManifest(),
      });
    });

    await waitFor(() => {
      expect(useAgentDockUiStore.getState().open).toBe(true);
      expect(useAgentDockUiStore.getState().tab).toBe("review");
    });
    expect(screen.getByText("Agent 改动")).toBeInTheDocument();
    expect(
      screen.getByLabelText("视频方案 / Unit 文案 / 正文"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤销" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看" })).toBeInTheDocument();
  });

  it("opens the existing decision center when a production confirmation arrives live", async () => {
    useAgentDockUiStore.getState().setOpen(false);
    renderDock();
    expect(document.querySelector("[data-agent-dock]")).not.toBeInTheDocument();

    act(() =>
      useReviewManifestStore.setState({
        projectId: "p1",
        transactionId: "tx1",
        authorizations: [
          {
            id: "auth-image-live",
            transactionId: "tx1",
            specialistRunId: "run-visual",
            executionRequestId: "request-image",
            targetRef: "project:assets",
            scope: { operation: "image_generation" },
            status: "PENDING",
            authorizationToken: "token-image",
            provider: "dashscope",
            model: "qwen-image-2.0-pro",
            maxCandidates: 1,
            createdAt: "now",
          },
        ],
      }),
    );

    await waitFor(() => {
      expect(document.querySelector("[data-agent-dock]")).toBeInTheDocument();
      expect(useAgentDockUiStore.getState().tab).toBe("review");
    });
    expect(screen.getAllByText("生产确认").length).toBeGreaterThan(0);
  });

  it("keeps history, workspace, decisions and close interactions without maximize controls", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();

    fireEvent.click(screen.getByRole("button", { name: "历史聊天" }));
    expect(screen.getByText("默认对话")).toBeInTheDocument();
    expect(screen.getByText("当前")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "工作区事实" }));
    expect(screen.getByText("任务上下文")).toBeInTheDocument();
    expect(screen.getByText("素材事实（0）")).toBeInTheDocument();
    expect(screen.queryByText("当前")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "审阅与决策中心" }));
    expect(screen.getByText("暂无待处理的决策")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "返回对话" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "输入修改意图，@ 可引用对象…" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "最大化面板" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "还原面板" }),
    ).not.toBeInTheDocument();
    expect(
      document.querySelector('[title="拖拽调整高度"]'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭 Agent 面板" }));
    expect(document.querySelector("[data-agent-dock]")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "打开 Agent" }),
    ).toBeInTheDocument();
  });

  it("resizes from the top and left handles and closes with Escape", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();
    fireEvent.pointerDown(document.querySelector('[title="拖拽调整大小"]')!, {
      clientX: 440,
      clientY: 100,
    });
    fireEvent.pointerMove(window, { clientX: 380, clientY: 40 });
    fireEvent.pointerUp(window);
    await waitFor(() => {
      expect(useAgentDockUiStore.getState().width).toBe(500);
      expect(useAgentDockUiStore.getState().height).toBe(680);
    });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(
      screen.getByRole("button", { name: "打开 Agent" }),
    ).toBeInTheDocument();
  });

  it("renders an in-flight Creator SSE message as origin-sized rich Markdown", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: { ...state.session!, status: "RUNNING" },
      messages: [
        {
          messageId: "user-1",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "汇报实时进度" }],
          metadata: {},
          createdAt: "now",
        },
      ],
      streamingAssistantMessages: {
        "assistant-stream-1": {
          messageId: "assistant-stream-1",
          firstEventSeq: 10,
          deltas: {
            1: "- **第一项**\n- [详情](https://example.com) 与 `内联代码`",
            0: "## 实时结果\n\n",
          },
          thinkingDeltas: { 2: "正在核对真实上下文。" },
          createdAt: "now",
        },
      },
    }));
    renderDock();

    const heading = screen.getByRole("heading", { level: 2, name: "实时结果" });
    const assistant = heading.closest<HTMLElement>("[data-agent-message]")!;
    expect(assistant).toHaveClass(
      "text-[11px]",
      "leading-5",
      "text-[var(--color-text-secondary)]",
    );
    expect(assistant.querySelector("ul")).toBeInTheDocument();
    expect(screen.getByText("第一项").tagName).toBe("STRONG");
    expect(screen.getByText("内联代码").tagName).toBe("CODE");
    expect(screen.getByRole("link", { name: "详情" })).toHaveAttribute(
      "href",
      "https://example.com",
    );
    const thinking = document.querySelector<HTMLElement>(
      "[data-agent-thinking]",
    )!;
    expect(thinking).toBeInTheDocument();
    expect(thinking).toHaveAttribute("data-expanded", "true");
    expect(thinking).toHaveTextContent("思考...");
    expect(thinking).toHaveTextContent("正在核对真实上下文。");
  });

  it("streams partial Action JSON inside one tool card and auto-collapses thinking and tool details", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    const user = {
      messageId: "user-stream-tool",
      messageSeq: 1,
      role: "user" as const,
      source: "initial_goal",
      content: [{ type: "text" as const, text: "读取计划" }],
      metadata: {},
      createdAt: "now",
    };
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: { ...state.session!, status: "RUNNING" },
      messages: [user],
      streamingAssistantMessages: {
        "assistant-stream-tool": {
          messageId: "assistant-stream-tool",
          firstEventSeq: 10,
          deltas: {
            0: '我先读取计划。\n```json\n{"action":"tool_call","tool":"read_project_file",',
            1: '"arguments":{"path":"plan',
          },
          thinkingDeltas: { 0: "确认需要读取的文件。" },
          createdAt: "now",
        },
      },
    }));
    renderDock();

    const streamingAction = document.querySelector<HTMLElement>(
      '[data-agent-action="tool_call"]',
    )!;
    expect(streamingAction).toHaveAttribute("data-streaming-action", "true");
    expect(streamingAction).toHaveAttribute("data-expanded", "true");
    expect(streamingAction).toHaveTextContent("read_project_file...");
    expect(
      within(streamingAction).getByText(/"path":"plan/),
    ).toBeInTheDocument();
    expect(screen.getByText("我先读取计划。")).toBeInTheDocument();

    act(() =>
      useCreatorSessionStore.setState((state) => ({
        streamingAssistantMessages: {
          ...state.streamingAssistantMessages,
          "assistant-stream-tool": {
            ...state.streamingAssistantMessages["assistant-stream-tool"],
            deltas: {
              ...state.streamingAssistantMessages["assistant-stream-tool"]
                .deltas,
              2: '.json"}}\n```',
            },
          },
        },
      })),
    );
    await waitFor(() =>
      expect(
        within(streamingAction).getByText(/"path": "plan.json"/),
      ).toBeInTheDocument(),
    );

    act(() =>
      useCreatorSessionStore.setState({
        streamingAssistantMessages: {},
        messages: [
          user,
          {
            messageId: "assistant-stream-tool",
            messageSeq: 2,
            role: "assistant",
            source: "creator_agent",
            content: [
              {
                type: "text",
                text: '我先读取计划。\n```json\n{"action":"tool_call","tool":"read_project_file","arguments":{"path":"plan.json"}}\n```',
              },
            ],
            metadata: {
              providerThinking: "确认需要读取的文件。",
              actionId: "action-stream-tool",
              parsedAction: {
                action: "tool_call",
                tool: "read_project_file",
                arguments: { path: "plan.json" },
              },
            },
            createdAt: "now",
          },
        ],
        events: [
          {
            eventId: "tool-started-live",
            seq: 20,
            type: "agent.tool_started",
            projectId: "p1",
            creatorSessionId: "session-1",
            at: "now",
            data: { actionId: "action-stream-tool", tool: "read_project_file" },
          },
        ],
      }),
    );
    const thinking = document.querySelector<HTMLElement>(
      "[data-agent-thinking]",
    )!;
    const tool = document.querySelector<HTMLElement>(
      '[data-agent-tool="action-stream-tool"]',
    )!;
    await waitFor(() =>
      expect(thinking).toHaveAttribute("data-expanded", "false"),
    );
    expect(thinking).toHaveTextContent("✓ 思考");
    expect(
      thinking.querySelector("[data-agent-thinking-output]"),
    ).not.toBeInTheDocument();
    expect(tool).toHaveAttribute("data-expanded", "true");
    expect(within(tool).getByText(/"path": "plan.json"/)).toBeInTheDocument();

    act(() =>
      useCreatorSessionStore.setState((state) => ({
        messages: [
          ...state.messages,
          {
            messageId: "result-stream-tool",
            messageSeq: 3,
            role: "user",
            source: "runtime_action_result",
            content: [
              { type: "text", text: '[RUNTIME_ACTION_RESULT]\n\n{"ok":true}' },
            ],
            metadata: {
              actionId: "action-stream-tool",
              tool: "read_project_file",
            },
            createdAt: "now",
          },
        ],
        events: [
          ...state.events,
          {
            eventId: "tool-completed-live",
            seq: 21,
            type: "agent.tool_completed",
            projectId: "p1",
            creatorSessionId: "session-1",
            at: "now",
            data: { actionId: "action-stream-tool", tool: "read_project_file" },
          },
        ],
      })),
    );
    await waitFor(() => expect(tool).toHaveAttribute("data-expanded", "false"));
    expect(
      within(tool).queryByText(/"path": "plan.json"/),
    ).not.toBeInTheDocument();
  });

  it("renders yield_until_runtime_event as a collapsed waiting action with inspectable details", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState({
      messages: [
        {
          messageId: "user-yield",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "等待剪辑" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-yield",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [
            {
              type: "text",
              text: '剪辑任务仍在运行。\n```json\n{"action":"yield_until_runtime_event","arguments":{"waitForRunIds":["run-video-1"],"reason":"等待 Source Intelligence 完成素材分析，以便 Runtime 投影 Section 和 Unit，然后委派 AI Editing Director 进行剪辑"}}\n```',
            },
          ],
          metadata: {
            parsedAction: {
              action: "yield_until_runtime_event",
              arguments: {
                waitForRunIds: ["run-video-1"],
                reason:
                  "等待 Source Intelligence 完成素材分析，以便 Runtime 投影 Section 和 Unit，然后委派 AI Editing Director 进行剪辑",
              },
            },
          },
          createdAt: "now",
        },
      ],
    });
    renderDock();

    const waiting = document.querySelector<HTMLElement>(
      '[data-agent-action="yield_until_runtime_event"]',
    )!;
    expect(waiting).toHaveAttribute("data-expanded", "false");
    expect(waiting).toHaveTextContent(
      "等待 Source Intelligence 完成素材分析，以便 Runtime 投影 Section 和 Unit，然后委派 AI Editing Director 进行剪辑中",
    );
    expect(waiting).not.toHaveTextContent("等待等待");
    fireEvent.click(within(waiting).getByRole("button", { name: "详情" }));
    expect(within(waiting).getByText(/"run-video-1"/)).toBeInTheDocument();
    expect(screen.queryByText(/yield_until_runtime_event/)).toBeInTheDocument();
  });

  it("keeps the focused modification editor writable and submits at a live SSE boundary", async () => {
    const { calls } = installMockFetch([
      {
        match: "/projects/p1/messages",
        method: "POST",
        response: {
          json: {
            messageSeq: 2,
            eventSeq: 20,
            classification: "mutation_instruction",
            appendState: "queued_until_message_boundary",
            creatorSessionId: "session-1",
            conversationId: "conversation-1",
          },
        },
      },
    ]);
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();

    const textbox = screen.getByRole("textbox", {
      name: "输入修改意图，@ 可引用对象…",
    });
    textbox.focus();
    textbox.textContent = "请把故事设定在温暖厨房";
    fireEvent.input(textbox);
    expect(document.activeElement).toBe(textbox);
    expect(textbox).toHaveAttribute("contenteditable", "true");

    act(() =>
      useCreatorSessionStore.setState((state) => ({
        session: { ...state.session!, status: "RUNNING" },
        streamingAssistantMessages: {
          "assistant-live": {
            messageId: "assistant-live",
            firstEventSeq: 19,
            deltas: { 0: "正在处理已有计划。" },
            thinkingDeltas: {},
            createdAt: "now",
          },
        },
      })),
    );

    await waitFor(() => {
      const liveTextbox = screen.getByRole("textbox", {
        name: "输入修改意图，@ 可引用对象…",
      });
      expect(liveTextbox).toBe(textbox);
      expect(liveTextbox).toHaveAttribute("contenteditable", "true");
      expect(liveTextbox).toHaveTextContent("请把故事设定在温暖厨房");
      expect(document.activeElement).toBe(liveTextbox);
    });

    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() =>
      expect(
        calls.some((call) => call.url.includes("/projects/p1/messages")),
      ).toBe(true),
    );
    expect(
      calls.find((call) => call.url.includes("/projects/p1/messages"))?.body,
    ).toMatchObject({
      creatorSessionId: "session-1",
      conversationId: "conversation-1",
      message: "请把故事设定在温暖厨房",
    });
  });

  it("clears submitted text immediately while the server is still accepting the message", async () => {
    let releaseRequest!: (response: Response) => void;
    const requestPending = new Promise<Response>((resolve) => {
      releaseRequest = resolve;
    });
    const fetchMock = vi.fn(() => requestPending);
    vi.stubGlobal("fetch", fetchMock);
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();

    const textbox = screen.getByRole("textbox", {
      name: "输入修改意图，@ 可引用对象…",
    });
    textbox.textContent = "立即发送，不要留在输入框";
    fireEvent.input(textbox);
    fireEvent.keyDown(textbox, { key: "Enter" });

    expect(textbox).toHaveTextContent("");
    expect(screen.getByText("立即发送，不要留在输入框")).toBeInTheDocument();
    expect(useCreatorSessionStore.getState().queuedUi[0]?.state).toBe(
      "sending",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);

    releaseRequest({
      ok: true,
      status: 202,
      statusText: "Accepted",
      json: async () => ({
        messageSeq: 2,
        eventSeq: 20,
        classification: "mutation_instruction",
        appendState: "queued_until_message_boundary",
        creatorSessionId: "session-1",
        conversationId: "conversation-1",
      }),
    } as Response);
    await waitFor(() =>
      expect(useCreatorSessionStore.getState().queuedUi[0]?.state).toBe(
        "queued",
      ),
    );
  });

  it("does not duplicate the global stop control inside AgentDock", () => {
    useCreatorSessionStore.setState((state) => ({
      session: { ...state.session!, status: "RUNNING" },
    }));
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();

    expect(
      screen.queryByRole("button", { name: "停止所有 Agent" }),
    ).not.toBeInTheDocument();
  });

  it("mounts the origin run block and current-change summary in the conversation surface", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorTaskViewStore.setState({
      projectId: "p1",
      runs: [
        {
          id: "run-1",
          role: "story_planning_agent",
          displayName: "故事规划",
          status: "SUCCEEDED",
          targetRefs: ["unit:u1"],
          taskRefs: [],
          metadata: {},
        },
      ],
    });
    useReviewManifestStore.setState({
      projectId: "p1",
      transactionId: "tx1",
      manifest: reviewManifest(),
    });
    renderDock();
    act(() => useAgentDockUiStore.getState().setTab("conversation"));

    expect(screen.getByText("端到端生产")).toBeInTheDocument();
    expect(
      screen.getByText(/故事规划 · unit:u1 · SUCCEEDED/),
    ).toBeInTheDocument();
    expect(screen.getByText("本轮 Agent 改动（1）")).toBeInTheDocument();
    expect(screen.getByText("视频方案 / Unit 文案 / 正文")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "接受全部" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤销" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看" })).toBeInTheDocument();
  });

  it("does not expose a detached revise card for inline review items", async () => {
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: {
        ...state.session!,
        status: "PENDING_REVIEW",
        activeTransactionId: "tx1",
      },
    }));
    useReviewManifestStore.setState({
      projectId: "p1",
      transactionId: "tx1",
      manifest: reviewManifest(),
    });
    useAgentDockUiStore.getState().setTab("review");
    renderDock();

    expect(await screen.findByText("Agent 改动")).toBeInTheDocument();
    expect(screen.getByText("Unit 文案")).toBeInTheDocument();
    expect(screen.queryByText("要求修改")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤销" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看" })).toBeInTheDocument();
  });

  it("routes ordinary PENDING_REVIEW input to a group comment without waking Creator", async () => {
    const { calls } = installMockFetch([
      {
        match: "/comments",
        response: {
          json: {
            commentId: "comment-1",
            groupId: "g1",
            text: "先记录这条意见",
            createdAt: "now",
          },
        },
      },
    ]);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: {
        ...state.session!,
        status: "PENDING_REVIEW",
        activeTransactionId: "tx1",
      },
    }));
    useReviewManifestStore.setState({
      projectId: "p1",
      transactionId: "tx1",
      manifest: reviewManifest(),
    });
    useAgentDockUiStore.getState().setReviewContext({
      groupId: "g1",
      decisionToken: "token-1",
      title: "Unit 文案",
      targetRef: "unit:u1",
    });
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();
    act(() => useAgentDockUiStore.getState().setTab("conversation"));

    const textbox = screen.getByRole("textbox", {
      name: "输入修改意图，@ 可引用对象…",
    });
    textbox.textContent = "先记录这条意见";
    fireEvent.input(textbox);
    fireEvent.keyDown(textbox, { key: "Enter" });

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/comments"))).toBe(true),
    );
    const commentCall = calls.find((call) => call.url.endsWith("/comments"))!;
    expect(commentCall.body).toMatchObject({ text: "先记录这条意见" });
    expect(commentCall.body).toHaveProperty("clientCommentId");
    expect(calls.some((call) => call.url.endsWith("/messages"))).toBe(false);
    expect(calls.some((call) => call.url.endsWith("/decision"))).toBe(false);
  });

  it("keeps file-native review feedback on the Session message API", async () => {
    const { calls } = installMockFetch([
      {
        match: "/projects/p1/messages",
        response: {
          json: {
            messageSeq: 1,
            eventSeq: 1,
            classification: "review_revise",
            appendState: "queued_until_message_boundary",
            creatorSessionId: "session-1",
            conversationId: "conversation-1",
          },
        },
      },
    ]);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: { ...state.session!, status: "PENDING_REVIEW" },
    }));
    useFileProjectReviewStore.setState({
      projectId: "p1",
      review: fileProjectReview(),
      etag: '"file-token-1"',
      syncStatus: "healthy",
    });
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();
    await waitFor(() =>
      expect(useAgentDockUiStore.getState().tab).toBe("review"),
    );
    act(() => useAgentDockUiStore.getState().setTab("conversation"));

    const textbox = screen.getByRole("textbox", {
      name: "输入修改意图，@ 可引用对象…",
    });
    textbox.textContent = "请根据这处 diff 再调整标题";
    fireEvent.input(textbox);
    fireEvent.keyDown(textbox, { key: "Enter" });

    await waitFor(() =>
      expect(
        calls.some((call) => call.url.endsWith("/projects/p1/messages")),
      ).toBe(true),
    );
    expect(calls.some((call) => call.url.includes("/transactions/"))).toBe(
      false,
    );
    expect(calls.some((call) => call.url.endsWith("/comments"))).toBe(false);
  });

  it("does not guess a comment target when multiple review groups are pending", () => {
    const { calls } = installMockFetch([]);
    const secondGroup: ReviewDecisionGroup = {
      ...reviewGroup,
      id: "g2",
      title: "另一个待审项",
      operationIds: ["op2"],
      decisionToken: "token-2",
    };
    const secondOperation: ReviewOperation = {
      ...reviewOperation,
      id: "op2",
      decisionGroupId: "g2",
      targetRef: "unit:u2",
      path: "story/sections/s1/units/u2/narrative.md",
    };
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: {
        ...state.session!,
        status: "PENDING_REVIEW",
        activeTransactionId: "tx1",
      },
    }));
    useReviewManifestStore.setState({
      projectId: "p1",
      transactionId: "tx1",
      manifest: {
        ...reviewManifest(),
        decisionGroups: [reviewGroup, secondGroup],
        operations: [reviewOperation, secondOperation],
      },
    });
    useAgentDockUiStore.getState().setOpen(true);
    renderDock();
    act(() => useAgentDockUiStore.getState().setTab("conversation"));

    const textbox = screen.getByRole("textbox", {
      name: "输入修改意图，@ 可引用对象…",
    });
    textbox.textContent = "这条意见没有指定目标";
    fireEvent.input(textbox);
    fireEvent.keyDown(textbox, { key: "Enter" });

    expect(calls.some((call) => call.url.endsWith("/comments"))).toBe(false);
    expect(calls.some((call) => call.url.endsWith("/messages"))).toBe(false);
    expect(calls.some((call) => call.url.endsWith("/decision"))).toBe(false);
    expect(textbox.textContent).toBe("这条意见没有指定目标");
  });

  it("keeps real user authority, hides Runtime rows and renders the expandable origin tool card", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState({
      messages: [
        {
          messageId: "user-1",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "请检查当前计划" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-1",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [
            {
              type: "text",
              text: '我先读取当前计划。\n```json\n{"action":"tool_call","tool":"read_project_file"}\n```',
            },
          ],
          metadata: {
            actionId: "action-1",
            parsedAction: {
              action: "tool_call",
              tool: "read_project_file",
              arguments: { path: "plan.json" },
            },
          },
          createdAt: "now",
        },
        {
          messageId: "result-1",
          messageSeq: 3,
          role: "user",
          source: "runtime_action_result",
          content: [
            {
              type: "text",
              text: '[RUNTIME_ACTION_RESULT]\n\n{"head":"h2","ok":true}',
            },
          ],
          metadata: {
            actionId: "action-1",
            tool: "read_project_file",
            resultKind: "workspace_read",
          },
          createdAt: "now",
        },
      ],
      events: [
        {
          eventId: "tool-started",
          seq: 1,
          type: "agent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: { actionId: "action-1", tool: "read_project_file" },
        },
        {
          eventId: "tool-completed",
          seq: 2,
          type: "agent.tool_completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: { actionId: "action-1", remainingActionIds: [] },
        },
      ],
    });
    useCreatorSessionStore.setState((state) => ({
      session: { ...state.session!, status: "RUNNING" },
    }));
    renderDock();

    const userBubble = screen
      .getByText("请检查当前计划")
      .closest("[data-agent-message]");
    expect(userBubble).toHaveClass("bg-[var(--color-accent)]", "text-white");
    const turn = userBubble?.closest("[data-agent-turn]");
    expect(turn).toHaveClass("space-y-2");
    const responseFlow = turn?.querySelector(
      ":scope > [data-agent-response-flow]",
    );
    expect(responseFlow).toHaveClass("space-y-2");
    expect(screen.getByText("我先读取当前计划。")).toBeInTheDocument();
    expect(screen.queryByText(/"action"/)).not.toBeInTheDocument();
    expect(screen.queryByText(/RUNTIME_ACTION_RESULT/)).not.toBeInTheDocument();
    expect(
      responseFlow?.querySelector("[data-agent-thinking]"),
    ).not.toBeInTheDocument();

    const toolStatus = screen.getByText(/✓\s+read_project_file/);
    expect(toolStatus).toHaveClass("text-[var(--color-success)]");
    expect(toolStatus.parentElement?.parentElement?.parentElement).toBe(
      responseFlow,
    );
    fireEvent.click(screen.getByRole("button", { name: "详情" }));
    expect(screen.getByText(/"path": "plan.json"/)).toBeInTheDocument();
    expect(screen.getByText(/"head": "h2"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
  });

  it("folds legacy file Runtime tool turns into the anchored tool card without placeholder bubbles", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState({
      messages: [
        {
          messageId: "user-file-runtime",
          messageSeq: 1,
          role: "user",
          source: "agent_dock",
          content: [{ type: "text", text: "读取当前项目" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-file-runtime",
          messageSeq: 2,
          role: "assistant",
          source: "file_agent_runtime",
          content: [{ type: "text", text: "准备调用工具：read_project" }],
          metadata: {
            runId: "run-file-runtime",
            toolCalls: [{ id: "call-file-runtime", name: "read_project" }],
          },
          createdAt: "now",
        },
        {
          messageId: "tool-file-runtime",
          messageSeq: 3,
          role: "tool",
          source: "file_agent_runtime",
          content: [{ type: "text", text: '{"ok":true,"generation":2}' }],
          metadata: {
            runId: "run-file-runtime",
            toolCallId: "call-file-runtime",
            toolName: "read_project",
          },
          createdAt: "now",
        },
      ],
      events: [
        {
          eventId: "file-runtime-completed",
          seq: 1,
          type: "agent.tool.completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            runId: "run-file-runtime",
            toolCallId: "call-file-runtime",
            toolName: "read_project",
            messageId: "tool-file-runtime",
            messageSeq: 3,
          },
        },
      ],
    });
    renderDock();

    expect(
      screen.queryByText("准备调用工具：read_project"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('{"ok":true,"generation":2}'),
    ).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-agent-message]")).toHaveLength(1);
    const tool = document.querySelector<HTMLElement>(
      '[data-agent-tool="call-file-runtime"]',
    )!;
    expect(tool).toBeInTheDocument();
    expect(tool).toHaveTextContent("✓ read_project");
    expect(tool.closest("[data-agent-response-flow]")).toBeInTheDocument();
    fireEvent.click(within(tool).getByRole("button", { name: "详情" }));
    expect(tool).toHaveTextContent('"generation": 2');
  });

  it("embeds the replayable Sub-agent SSE stream in one natural delegate tool card", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      session: { ...state.session!, status: "RUNNING" },
      messages: [
        {
          messageId: "user-delegate",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "完善第一幕" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-delegate",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [
            {
              type: "text",
              text: '我会请故事规划 Agent 完善第一幕。\n```json\n{"action":"tool_call","tool":"delegate_to_agent"}\n```',
            },
          ],
          metadata: {
            actionId: "delegate-action",
            parsedAction: {
              action: "tool_call",
              tool: "delegate_to_agent",
              arguments: {
                role: "story_planning_agent",
                target_refs: ["section:s1"],
                task: "请完善第一幕冲突，并说明改动结果。",
              },
            },
          },
          createdAt: "now",
        },
      ],
    }));
    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "delegate-started",
          seq: 1,
          type: "agent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            actionId: "delegate-action",
            tool: "delegate_to_agent",
            role: "story_planning_agent",
            roleDisplayName: "故事规划",
            delegationText: "请完善第一幕冲突，并说明改动结果。",
            targetRefs: ["section:s1"],
          },
        },
        {
          eventId: "sub-delta",
          seq: 2,
          type: "subagent.message_delta",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-action",
            runId: "run-story-1",
            role: "story_planning_agent",
            messageId: "sub-message-1",
            deltaIndex: 0,
            delta: "## 正在规划\n\n先梳理冲突。",
          },
        },
        {
          eventId: "nested-started",
          seq: 3,
          type: "subagent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-action",
            runId: "run-story-1",
            role: "story_planning_agent",
            toolCallId: "nested-tool-1",
            tool: "read_project_file",
            arguments: { path: "story/outline.md" },
            state: "started",
          },
        },
        {
          eventId: "nested-completed",
          seq: 4,
          type: "subagent.tool_completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-action",
            runId: "run-story-1",
            role: "story_planning_agent",
            toolCallId: "nested-tool-1",
            tool: "read_project_file",
            result: { summary: "读取完成" },
            state: "succeeded",
          },
        },
      ]),
    );
    renderDock();

    expect(screen.getByText(/▸\s+委派给 故事规划/)).toBeInTheDocument();
    expect(
      document.querySelector('[data-agent-tool="delegate-action"]'),
    ).toHaveAttribute("data-expanded", "true");
    expect(
      screen.getByText("请完善第一幕冲突，并说明改动结果。"),
    ).toBeInTheDocument();
    expect(screen.getByText("目标：section:s1")).toBeInTheDocument();
    expect(screen.getByText(/## 正在规划/)).toBeInTheDocument();
    expect(screen.getByText("SSE 实时输出中")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    const subagentMessage = document.querySelector(
      '[data-subagent-message="sub-message-1"]',
    )!;
    expect(subagentMessage).toHaveClass(
      "text-[11px]",
      "leading-5",
      "text-[var(--color-text-secondary)]",
    );
    expect(subagentMessage).not.toHaveClass(
      "rounded-md",
      "bg-[var(--color-bg-card)]/80",
    );
    expect(document.querySelector("[data-subagent-input]")).toHaveClass(
      "max-h-32",
      "overflow-y-auto",
    );
    expect(document.querySelector("[data-subagent-output]")).toHaveClass(
      "max-h-[min(24rem,50vh)]",
      "overflow-y-auto",
      "overscroll-contain",
      "touch-pan-y",
    );
    expect(screen.getByText(/✓\s+read_project_file/)).toBeInTheDocument();
    expect(screen.queryByText(/"role":/)).not.toBeInTheDocument();
    expect(screen.queryByText(/"target_refs":/)).not.toBeInTheDocument();

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "sub-completed",
        seq: 5,
        type: "subagent.message_completed",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          parentActionId: "delegate-action",
          runId: "run-story-1",
          role: "story_planning_agent",
          messageId: "sub-message-1",
          text: "[SUCCESS]\n## 已完成\n\n第一幕冲突已完善。",
          finishReason: "stop",
        },
      }),
    );
    await waitFor(() =>
      expect(
        document.querySelector('[data-subagent-message="sub-message-1"]'),
      ).toHaveTextContent("## 已完成"),
    );
    expect(
      document.querySelector('[data-subagent-message="sub-message-1"]'),
    ).not.toHaveTextContent("## 正在规划");
    expect(
      document.querySelector('[data-subagent-message="sub-message-1"]'),
    ).toHaveTextContent("[SUCCESS]");
    expect(
      document.querySelector('[data-subagent-message="sub-message-1"]'),
    ).toHaveTextContent("已完成");

    const nestedTool = document.querySelector(
      '[data-subagent-tool="nested-tool-1"]',
    )!;
    fireEvent.click(
      within(nestedTool as HTMLElement).getByRole("button", { name: "详情" }),
    );
    expect(screen.getByText(/"path": "story\/outline.md"/)).toBeInTheDocument();
    expect(screen.getByText(/"summary": "读取完成"/)).toBeInTheDocument();
  });

  it("renders native Sub-agent tool argument deltas in one live tool card", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      messages: [
        {
          messageId: "assistant-native-tool",
          messageSeq: 1,
          role: "assistant",
          source: "creator_agent",
          content: [{ type: "text", text: "委派故事规划。" }],
          metadata: {
            actionId: "delegate-native-tool",
            parsedAction: {
              action: "tool_call",
              tool: "delegate_to_agent",
              arguments: { role: "story_planning_agent", task: "读取故事文件" },
            },
          },
          createdAt: "now",
        },
      ],
    }));
    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "delegate-native-start",
          seq: 1,
          type: "agent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            actionId: "delegate-native-tool",
            tool: "delegate_to_agent",
            role: "story_planning_agent",
            roleDisplayName: "故事规划",
            delegationText: "读取故事文件",
          },
        },
        {
          eventId: "native-tool-delta-0",
          seq: 2,
          type: "subagent.tool_delta",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-native-tool",
            runId: "run-native-tool",
            role: "story_planning_agent",
            messageId: "message-native-tool",
            toolCallId: "call-native-tool",
            tool: "read_project_file",
            deltaIndex: 0,
            argumentsDelta: '{"path":"story/',
            state: "streaming",
          },
        },
      ]),
    );
    renderDock();

    const tool = document.querySelector<HTMLElement>(
      '[data-subagent-tool="call-native-tool"]',
    )!;
    expect(tool).toHaveAttribute("data-expanded", "true");
    expect(tool).toHaveTextContent("read_project_file");
    expect(
      tool.querySelector("[data-subagent-tool-arguments]"),
    ).toHaveTextContent('{"path":"story/');

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "native-tool-delta-1",
        seq: 3,
        type: "subagent.tool_delta",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          parentActionId: "delegate-native-tool",
          runId: "run-native-tool",
          role: "story_planning_agent",
          messageId: "message-native-tool",
          toolCallId: "call-native-tool",
          tool: "read_project_file",
          deltaIndex: 1,
          argumentsDelta: 'outline.md"}',
          state: "streaming",
        },
      }),
    );
    await waitFor(() =>
      expect(
        tool.querySelector("[data-subagent-tool-arguments]"),
      ).toHaveTextContent('"path": "story/outline.md"'),
    );

    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "native-tool-started",
          seq: 4,
          type: "subagent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-native-tool",
            runId: "run-native-tool",
            role: "story_planning_agent",
            messageId: "message-native-tool",
            toolCallId: "call-native-tool",
            tool: "read_project_file",
            arguments: { path: "story/outline.md" },
            state: "started",
          },
        },
        {
          eventId: "native-tool-completed",
          seq: 5,
          type: "subagent.tool_completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-native-tool",
            runId: "run-native-tool",
            role: "story_planning_agent",
            messageId: "message-native-tool",
            toolCallId: "call-native-tool",
            tool: "read_project_file",
            result: { ok: true },
            state: "succeeded",
          },
        },
      ]),
    );
    await waitFor(() => expect(tool).toHaveAttribute("data-expanded", "false"));
    expect(
      document.querySelectorAll('[data-subagent-tool="call-native-tool"]'),
    ).toHaveLength(1);
  });

  it("moves a streamed Sub-agent function call into its tool card and preserves detail scrolling", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      messages: [
        {
          messageId: "user-function",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "读取故事文件" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-function",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [{ type: "text", text: "委派故事规划。" }],
          metadata: {
            actionId: "delegate-function",
            parsedAction: {
              action: "tool_call",
              tool: "delegate_to_agent",
              arguments: {
                role: "story_planning_agent",
                target_refs: ["section:s1"],
                task: "读取故事文件",
              },
            },
          },
          createdAt: "now",
        },
      ],
    }));
    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "delegate-function-start",
          seq: 1,
          type: "agent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            actionId: "delegate-function",
            tool: "delegate_to_agent",
            role: "story_planning_agent",
            roleDisplayName: "故事规划",
            delegationText: "读取故事文件",
            targetRefs: ["section:s1"],
          },
        },
        {
          eventId: "function-delta-1",
          seq: 2,
          type: "subagent.message_delta",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-function",
            runId: "run-function",
            role: "story_planning_agent",
            messageId: "message-function",
            deltaIndex: 0,
            delta:
              '<function=read_project_file><parameter=arguments>{"path":"story/',
          },
        },
      ]),
    );
    renderDock();

    const subagentMessage = document.querySelector<HTMLElement>(
      '[data-subagent-message="message-function"]',
    )!;
    const streamingFunction = subagentMessage.querySelector<HTMLElement>(
      '[data-agent-action="tool_call"]',
    )!;
    expect(streamingFunction).toHaveAttribute("data-expanded", "true");
    expect(streamingFunction).toHaveTextContent("read_project_file...");
    expect(streamingFunction).toHaveTextContent('"path":"story/');

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "function-delta-2",
        seq: 3,
        type: "subagent.message_delta",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          parentActionId: "delegate-function",
          runId: "run-function",
          role: "story_planning_agent",
          messageId: "message-function",
          deltaIndex: 1,
          delta: 'outline.md"}</parameter></function></tool_call>',
        },
      }),
    );
    await waitFor(() =>
      expect(streamingFunction).toHaveTextContent('"path": "story/outline.md"'),
    );

    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "function-message-completed",
          seq: 4,
          type: "subagent.message_completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-function",
            runId: "run-function",
            role: "story_planning_agent",
            messageId: "message-function",
            text: '<function=read_project_file><parameter=arguments>{"path":"story/outline.md"}</parameter></function></tool_call>',
            finishReason: "tool_call",
          },
        },
        {
          eventId: "function-tool-started",
          seq: 5,
          type: "subagent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-function",
            runId: "run-function",
            role: "story_planning_agent",
            toolCallId: "function-tool",
            tool: "read_project_file",
            arguments: { path: "story/outline.md" },
            state: "started",
          },
        },
        {
          eventId: "function-progress-1",
          seq: 6,
          type: "task.progress_updated",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            specialistRunId: "run-function",
            taskId: "task-function",
            progress: 0.4,
            detail: "已读取前 400 行",
          },
        },
      ]),
    );
    let nestedTool: HTMLElement | null = null;
    await waitFor(() => {
      nestedTool = document.querySelector<HTMLElement>(
        '[data-subagent-tool="function-tool"]',
      );
      expect(nestedTool).toHaveAttribute("data-expanded", "true");
    });
    expect(nestedTool).not.toBeNull();
    expect(
      subagentMessage.querySelector('[data-agent-action="tool_call"]'),
    ).not.toBeInTheDocument();
    const toolOutput = nestedTool!.querySelector<HTMLElement>(
      "[data-subagent-tool-stream]",
    )!;
    expect(toolOutput).toHaveClass(
      "overflow-auto",
      "overscroll-contain",
      "touch-pan-y",
    );
    expect(toolOutput).toHaveTextContent("已读取前 400 行");
    Object.defineProperties(toolOutput, {
      scrollHeight: { configurable: true, value: 900 },
      clientHeight: { configurable: true, value: 180 },
    });
    toolOutput.scrollTop = 420;

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "function-progress-2",
        seq: 7,
        type: "task.progress_updated",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          specialistRunId: "run-function",
          taskId: "task-function",
          progress: 0.8,
          detail: "已读取前 800 行",
        },
      }),
    );
    await waitFor(() =>
      expect(toolOutput).toHaveTextContent("已读取前 800 行"),
    );
    expect(toolOutput.scrollTop).toBe(420);
    toolOutput.scrollTop = toolOutput.scrollHeight - toolOutput.clientHeight;
    expect(toolOutput.scrollTop).toBe(720);

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "function-tool-completed",
        seq: 8,
        type: "subagent.tool_completed",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          parentActionId: "delegate-function",
          runId: "run-function",
          role: "story_planning_agent",
          toolCallId: "function-tool",
          tool: "read_project_file",
          result: { lines: 800 },
          state: "succeeded",
        },
      }),
    );
    await waitFor(() =>
      expect(nestedTool).toHaveAttribute("data-expanded", "false"),
    );
    expect(
      nestedTool!.querySelector("[data-subagent-tool-stream]"),
    ).not.toBeInTheDocument();
  });

  it("treats delegate acceptance as waiting and only a Sub-agent terminal event as finished", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      ...state,
      messages: [
        {
          messageId: "user-service",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "执行剪辑" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-service",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [{ type: "text", text: "我会委派剪辑任务。" }],
          metadata: {
            actionId: "delegate-service-action",
            parsedAction: {
              action: "tool_call",
              tool: "delegate_to_agent",
              arguments: {
                role: "ai_editing_director",
                target_refs: ["unit:u1"],
                task: "根据当前素材完成 Unit 1 的剪辑。",
              },
            },
          },
          createdAt: "now",
        },
      ],
    }));
    act(() =>
      useCreatorSessionStore.getState().ingestEvents([
        {
          eventId: "delegate-service-started",
          seq: 1,
          type: "agent.tool_started",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            actionId: "delegate-service-action",
            tool: "delegate_to_agent",
            role: "ai_editing_director",
            roleDisplayName: "AI 剪辑导演",
            delegationText: "根据当前素材完成 Unit 1 的剪辑。",
            targetRefs: ["unit:u1"],
          },
        },
        {
          eventId: "delegate-service-completed",
          seq: 2,
          type: "agent.tool_completed",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            actionId: "delegate-service-action",
            tool: "delegate_to_agent",
            status: "succeeded",
          },
        },
        {
          eventId: "sub-service-accepted",
          seq: 3,
          type: "subagent.accepted",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            parentActionId: "delegate-service-action",
            runId: "run-service-1",
            role: "ai_editing_director",
            roleDisplayName: "AI 剪辑导演",
            delegationText: "根据当前素材完成 Unit 1 的剪辑。",
            targetRefs: ["unit:u1"],
          },
        },
      ]),
    );
    renderDock();

    const delegateTool = document.querySelector<HTMLElement>(
      '[data-agent-tool="delegate-service-action"]',
    )!;
    expect(delegateTool).toHaveAttribute("data-expanded", "true");
    expect(screen.getByText("等待输出…")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.queryByText("Sub-agent 已结束")).not.toBeInTheDocument();

    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "sub-service-terminal",
        seq: 4,
        type: "subagent.completed",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          parentActionId: "delegate-service-action",
          runId: "run-service-1",
          role: "ai_editing_director",
          marker: "SUCCESS",
          status: "SUCCEEDED",
          summary: "剪辑方案已生成并等待执行确认。",
        },
      }),
    );
    act(() =>
      useCreatorSessionStore.getState().ingestEvent({
        eventId: "delegate-service-parent-completed",
        seq: 5,
        type: "agent.tool_completed",
        projectId: "p1",
        creatorSessionId: "session-1",
        at: "now",
        data: {
          actionId: "delegate-service-action",
          runId: "parent-agent-run-1",
          tool: "delegate_to_agent",
          status: "succeeded",
        },
      }),
    );
    await waitFor(() =>
      expect(delegateTool).toHaveAttribute("data-expanded", "false"),
    );
    expect(
      screen.queryByText("剪辑方案已生成并等待执行确认。"),
    ).not.toBeInTheDocument();
    fireEvent.click(within(delegateTool).getByRole("button", { name: "详情" }));
    expect(
      screen.getByText("剪辑方案已生成并等待执行确认。"),
    ).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.queryByText("等待输出…")).not.toBeInTheDocument();
  });

  it("does not synthesize a thinking block when the provider emitted none", async () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      session: { ...state.session!, status: "RUNNING" },
      messages: [
        {
          messageId: "user-1",
          messageSeq: 1,
          role: "user",
          source: "agent_dock",
          content: [{ type: "text", text: "继续处理" }],
          metadata: {},
          createdAt: "now",
        },
      ],
    }));
    renderDock();

    const responseFlow = screen
      .getByText("继续处理")
      .closest("[data-agent-turn]")
      ?.querySelector(":scope > [data-agent-response-flow]");
    expect(
      responseFlow?.querySelector("[data-agent-thinking]"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("正在分析上下文并决定下一步操作。"),
    ).not.toBeInTheDocument();

    act(() =>
      useCreatorSessionStore.setState((state) => ({
        messages: [
          ...state.messages,
          {
            messageId: "assistant-1",
            messageSeq: 2,
            role: "assistant",
            source: "creator_agent",
            content: [{ type: "text", text: "已找到需要处理的内容。" }],
            metadata: {},
            createdAt: "now",
          },
        ],
      })),
    );
    await waitFor(() =>
      expect(
        responseFlow?.querySelector("[data-agent-thinking]"),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.getByText("已找到需要处理的内容。").closest("[data-agent-message]")
        ?.parentElement,
    ).toBe(responseFlow);

    act(() =>
      useCreatorSessionStore.setState((state) => ({
        session: { ...state.session!, status: "IDLE" },
      })),
    );
    await waitFor(() =>
      expect(
        responseFlow?.querySelector("[data-agent-thinking]"),
      ).not.toBeInTheDocument(),
    );
  });

  it("keeps each native tool call directly after its own thinking message", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState({
      messages: [
        {
          messageId: "user-native-order",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "依次读取并写入文件" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-native-read",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [],
          metadata: {
            providerThinking: "先检查当前文件。",
            actionId: "call-native-read",
            toolCall: {
              id: "call-native-read",
              name: "read_file",
              arguments: { file_path: "plan.txt" },
            },
          },
          createdAt: "now",
        },
        {
          messageId: "result-native-read",
          messageSeq: 3,
          role: "tool",
          source: "runtime_action_result",
          content: [{ type: "text", text: '{"content":"旧内容"}' }],
          metadata: { actionId: "call-native-read", tool: "read_file" },
          createdAt: "now",
        },
        {
          messageId: "assistant-native-write",
          messageSeq: 4,
          role: "assistant",
          source: "creator_agent",
          content: [],
          metadata: {
            providerThinking: "读取完成，现在写入。",
            actionId: "call-native-write",
            toolCall: {
              id: "call-native-write",
              name: "write_file",
              arguments: { file_path: "plan.txt", content: "新内容" },
            },
          },
          createdAt: "now",
        },
        {
          messageId: "result-native-write",
          messageSeq: 5,
          role: "tool",
          source: "runtime_action_result",
          content: [{ type: "text", text: '{"ok":true}' }],
          metadata: { actionId: "call-native-write", tool: "write_file" },
          createdAt: "now",
        },
      ],
    });
    renderDock();

    const responseFlow = screen
      .getByText("依次读取并写入文件")
      .closest("[data-agent-turn]")
      ?.querySelector(":scope > [data-agent-response-flow]")!;
    const readTool = responseFlow.querySelector<HTMLElement>(
      '[data-agent-tool="call-native-read"]',
    )!;
    const writeTool = responseFlow.querySelector<HTMLElement>(
      '[data-agent-tool="call-native-write"]',
    )!;
    const orderedItems = Array.from(responseFlow.children);
    const [readThinking, , writeThinking] = orderedItems;

    expect(orderedItems).toHaveLength(4);
    expect(readThinking).toHaveAttribute("data-agent-message");
    expect(orderedItems[1]).toBe(readTool);
    expect(writeThinking).toHaveAttribute("data-agent-message");
    expect(orderedItems[3]).toBe(writeTool);
    expect(responseFlow.querySelectorAll("[data-agent-thinking]")).toHaveLength(
      2,
    );
  });

  it("anchors the origin plan card after assistant narration inside the same human turn", () => {
    useAgentDockUiStore.getState().setOpen(true);
    useCreatorSessionStore.setState((state) => ({
      session: { ...state.session!, status: "RUNNING" },
      messages: [
        {
          messageId: "user-1",
          messageSeq: 1,
          role: "user",
          source: "initial_goal",
          content: [{ type: "text", text: "先制定计划" }],
          metadata: {},
          createdAt: "now",
        },
        {
          messageId: "assistant-1",
          messageSeq: 2,
          role: "assistant",
          source: "creator_agent",
          content: [
            {
              type: "text",
              text: '我会分两步推进。\n```json\n{"action":"plan","summary":"先完成故事规划"}\n```',
            },
          ],
          metadata: {
            parsedAction: {
              action: "plan",
              summary: "先完成故事规划",
              steps: ["1. 拆分 Section", "2、规划 Unit"],
              scope: ["section:s1"],
            },
          },
          createdAt: "now",
        },
      ],
      events: [
        {
          eventId: "plan-1",
          seq: 1,
          type: "agent.plan",
          projectId: "p1",
          creatorSessionId: "session-1",
          at: "now",
          data: {
            summary: "先完成故事规划",
            steps: ["1. 拆分 Section", "2、规划 Unit"],
            scope: ["section:s1"],
          },
        },
      ],
    }));
    renderDock();

    const turn = screen.getByText("先制定计划").closest("[data-agent-turn]");
    const responseFlow = turn?.querySelector(
      ":scope > [data-agent-response-flow]",
    );
    const narration = screen
      .getByText("我会分两步推进。")
      .closest("[data-agent-message]")!;
    const plan = screen.getByText("执行计划：先完成故事规划").closest("div")!;
    expect(narration.parentElement).toBe(responseFlow);
    expect(plan.parentElement).toBe(responseFlow);
    expect(
      narration.compareDocumentPosition(plan) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(plan).toHaveClass(
      "border-[var(--color-accent)]/30",
      "bg-[var(--color-accent-soft)]",
    );
    expect(screen.getByText("拆分 Section")).toBeInTheDocument();
    expect(screen.getByText("规划 Unit")).toBeInTheDocument();
    expect(screen.queryByText("1. 拆分 Section")).not.toBeInTheDocument();
    expect(screen.queryByText("2、规划 Unit")).not.toBeInTheDocument();
    expect(screen.queryByText(/"action"/)).not.toBeInTheDocument();
    expect(
      responseFlow?.querySelector("[data-agent-thinking]"),
    ).not.toBeInTheDocument();
  });
});
