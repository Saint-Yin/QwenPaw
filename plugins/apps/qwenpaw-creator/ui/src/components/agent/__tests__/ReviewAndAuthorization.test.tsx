import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import AgentDecisionCenter from "@/components/agent/AgentDecisionCenter";
import { installMockFetch } from "@/test/mockFetch";
import { useExecutionAuthorizationStore } from "@/store/executionAuthorizationStore";

const pending = {
  id: "authorization-1",
  transactionId: "round-1",
  specialistRunId: "run-1",
  executionRequestId: "request-1",
  targetRef: "element:r2v-window",
  scope: { operation: "r2v_generation", message: "生成 Element 视频" },
  status: "PENDING" as const,
  authorizationToken: "token-1",
  provider: "dashscope",
  model: "wan2.7-r2v",
  estimatedCost: 2.5,
  currency: "CNY",
  maxCandidates: 2,
  createdAt: "now",
};

describe("file-native execution authorization decisions", () => {
  beforeEach(() => {
    useExecutionAuthorizationStore.getState().reset();
    useExecutionAuthorizationStore.getState().bindProject("p1");
  });

  it("approves the exact project-level authorization request", async () => {
    useExecutionAuthorizationStore.setState({ items: [pending] });
    const { calls } = installMockFetch([
      {
        match: "/projects/p1/execution-authorizations/authorization-1/approve",
        response: { json: { ...pending, status: "APPROVED" } },
      },
    ]);

    render(<AgentDecisionCenter projectId="p1" />);
    expect(screen.getByText("生成 Element 视频")).toBeInTheDocument();
    fireEvent.click(screen.getByText("继续"));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).not.toContain("/transactions/");
    expect(calls[0].body).toEqual({
      authorizationToken: "token-1",
      provider: "dashscope",
      model: "wan2.7-r2v",
      maxCost: 2.5,
      maxCandidates: 2,
    });
  });

  it("declines with the exact token and shows the empty decision state afterwards", async () => {
    useExecutionAuthorizationStore.setState({ items: [pending] });
    installMockFetch([
      {
        match: "/projects/p1/execution-authorizations/authorization-1/decline",
        response: { json: { ...pending, status: "DECLINED" } },
      },
    ]);

    render(<AgentDecisionCenter projectId="p1" />);
    fireEvent.click(screen.getByText("取消"));

    await waitFor(() =>
      expect(screen.getByText("暂无待处理的决策")).toBeInTheDocument(),
    );
  });
});
