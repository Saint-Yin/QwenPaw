import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ModelConfigModal from "../ModelConfigModal";
import { installMockFetch } from "@/test/mockFetch";

const emptyConfig = {
  llm: {
    enabled: true,
    model_name: "",
    api_key: "",
    base_url: "",
    protocol: "OpenAI 协议",
    custom_protocol: "",
    multimodal: false,
  },
  vlm: {
    enabled: false,
    model_name: "",
    api_key: "",
    base_url: "",
    protocol: "OpenAI 协议",
    custom_protocol: "",
    use_llm: false,
    multimodal: false,
  },
  grounding: {
    enabled: true,
    model_name: "",
    api_key: "",
    base_url: "",
    protocol: "OpenAI 协议",
    custom_protocol: "",
    reuse_llm: true,
    tavily_api_key: "",
  },
  image: {
    enabled: false,
    model_name: "",
    api_key: "",
    base_url: "",
    protocol: "OpenAI 协议",
    custom_protocol: "",
  },
  video: {
    enabled: false,
    model_name: "",
    api_key: "",
    base_url: "",
    protocol: "Volcano Engine（火山引擎）",
    custom_protocol: "",
  },
  oss: {
    enabled: false,
    access_key_id: "",
    access_key_secret: "",
    endpoint: "",
    bucket: "",
    public_base_url: "",
    policy_api_key: "",
  },
  executionAuthorization: { mode: "required" as const },
};

const configuredGroundingConfig = {
  ...emptyConfig,
  llm: {
    ...emptyConfig.llm,
    enabled: true,
    model_name: "qwen3.7-plus",
    api_key: "saved-secret",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  },
  grounding: {
    ...emptyConfig.grounding,
    tavily_api_key: "tvly-saved-secret",
  },
};

describe("ModelConfigModal configuration lifecycle", () => {
  it("stays unconfigured until the user tests and saves entered model data", async () => {
    const onClose = vi.fn();
    const { calls } = installMockFetch([
      {
        match: "/models/config/llm",
        method: "PATCH",
        response: { json: { ok: true } },
      },
      {
        match: "/models/config",
        method: "GET",
        response: { json: emptyConfig },
      },
      {
        match: "/models/test",
        method: "POST",
        response: { json: { ok: true, ms: 8 } },
      },
    ]);
    render(<ModelConfigModal open onClose={onClose} />);

    await waitFor(() => expect(screen.getAllByText("未配置")).toHaveLength(5));
    const keyInput = screen.getByPlaceholderText("sk-...");
    expect(keyInput).toHaveAttribute("type", "password");
    expect(
      screen.queryByRole("button", { name: "显示" }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("model"), {
      target: { value: "saved-model" },
    });
    fireEvent.change(keyInput, { target: { value: "saved-secret" } });
    fireEvent.change(screen.getByPlaceholderText("https://api.example.com"), {
      target: { value: "https://provider.test/v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /测试连通性/ }));
    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/models/test"))).toBe(
        true,
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));
    // 分段保存只 PATCH 当前标签页的 section，保存成功后自动关闭窗口
    await waitFor(() => {
      const save = calls.find(
        (call) =>
          call.method === "PATCH" && call.url.endsWith("/models/config/llm"),
      );
      expect(save?.body).toMatchObject({
        model_name: "saved-model",
        api_key: "saved-secret",
        base_url: "https://provider.test/v1",
      });
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });

  it("shows fixed Grounding providers and can disable grounding without exposing runtime budgets", async () => {
    const onClose = vi.fn();
    const { calls } = installMockFetch([
      {
        match: "/models/config/grounding",
        method: "PATCH",
        response: { json: { ok: true } },
      },
      {
        match: "/models/config",
        method: "GET",
        response: { json: configuredGroundingConfig },
      },
    ]);
    render(<ModelConfigModal open onClose={onClose} />);

    expect(
      await screen.findByRole("button", {
        name: /Grounding.*tavily\/qwen3\.7-plus/,
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Grounding/ }),
    );
    expect(screen.getByText("Tavily → Qwen Web Search")).toBeInTheDocument();
    expect(
      screen.getByText("Tavily Images → Qwen web_search_image"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("tavily/qwen3.7-plus")).toHaveLength(2);
    expect(screen.queryByText("复用 qwen3.7-plus")).not.toBeInTheDocument();
    expect(screen.getByText("复用 LLM 配置")).toBeInTheDocument();
    expect(screen.queryByText("超时、重试与来源上限")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "启用 Grounding" }));
    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const save = calls.find(
        (call) =>
          call.method === "PATCH" &&
          call.url.endsWith("/models/config/grounding"),
      );
      expect(save?.body).toMatchObject({
        enabled: false,
        reuse_llm: true,
        tavily_api_key: "tvly-saved-secret",
      });
    });
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });

  it("shows only the reused model name when Tavily is not configured", async () => {
    installMockFetch([
      {
        match: "/models/config",
        method: "GET",
        response: {
          json: {
            ...configuredGroundingConfig,
            grounding: {
              ...configuredGroundingConfig.grounding,
              tavily_api_key: "",
            },
          },
        },
      },
    ]);

    render(<ModelConfigModal open onClose={vi.fn()} />);

    expect(
      await screen.findByRole("button", {
        name: /Grounding.*qwen3\.7-plus/,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("tavily/qwen3.7-plus")).not.toBeInTheDocument();
    expect(screen.queryByText("复用 qwen3.7-plus")).not.toBeInTheDocument();
  });
});
