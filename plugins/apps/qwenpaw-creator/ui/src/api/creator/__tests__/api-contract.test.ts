import { describe, expect, it } from "vitest";
import { installMockFetch } from "@/test/mockFetch";
import {
  createAssetImport,
  createProject,
  decideReviewGroup,
  sendCreatorMessage,
  saveModelConfig,
  submitCreatorCommand,
  testModelConnection,
} from "@/api/creator";

describe("new Creator API contract", () => {
  it("uses only project/session/command/review routes with stable idempotency ids", async () => {
    const { calls } = installMockFetch([
      {
        match: "/projects/p1/transactions/tx1/review/groups/g1/decision",
        response: { json: { group: {}, manifest: {} } },
      },
      {
        match: "/projects/p1/commands",
        response: {
          json: { commandId: "cmd", status: "APPLIED", eventSeq: 1 },
        },
      },
      {
        match: "/projects/p1/messages",
        response: {
          json: {
            messageSeq: 1,
            eventSeq: 2,
            classification: "mutation_instruction",
            appendState: "appended",
            creatorSessionId: "s1",
            conversationId: "c1",
          },
        },
      },
      {
        match: "/projects",
        response: {
          json: {
            projectId: "p1",
            creatorSessionId: "s1",
            conversationId: "c1",
            approvedRevisionId: "r1",
            header: {},
          },
        },
      },
    ]);
    await createProject({
      clientRequestId: "project-key",
      name: "P",
      scenario: "general",
      aspectRatio: "16:9",
      resolution: "720P",
    });
    await sendCreatorMessage("p1", {
      clientMessageId: "message-key",
      conversationId: "c1",
      message: "目标",
    });
    await submitCreatorCommand("p1", {
      clientCommandId: "command-key",
      type: "SET_UNIT_TEXT",
      targetRef: "unit:u1",
      arguments: { field: "storyText", value: "新文本" },
      expectedTargetVersions: [{ ref: "unit:u1", objectVersion: "ov1" }],
    });
    await decideReviewGroup("p1", "tx1", "g1", {
      decisionToken: "token-1",
      decision: "ACCEPT",
    });
    expect(calls.map((call) => [call.method, call.url])).toEqual([
      ["POST", "/api/qwenpaw-creator/projects"],
      ["POST", "/api/qwenpaw-creator/projects/p1/messages"],
      ["POST", "/api/qwenpaw-creator/projects/p1/commands"],
      [
        "PUT",
        "/api/qwenpaw-creator/projects/p1/transactions/tx1/review/groups/g1/decision",
      ],
    ]);
    expect(calls[0].headers["idempotency-key"]).toBe("project-key");
    expect(calls[1].headers["idempotency-key"]).toBe("message-key");
    expect(calls[2].headers["idempotency-key"]).toBe("command-key");
    expect(
      calls.every((call) =>
        call.url.startsWith("/api/qwenpaw-creator/projects"),
      ),
    ).toBe(true);
  });

  it("preserves browser folder paths and uses the canonical model probe", async () => {
    const { calls } = installMockFetch([
      {
        match: "/asset-imports",
        response: { json: { importId: "t1", taskId: "t1", eventSeq: 1 } },
      },
      { match: "/models/test", response: { json: { ok: true, ms: 12 } } },
    ]);
    const file = new File(["hello"], "story.txt", { type: "text/plain" });
    Object.defineProperty(file, "webkitRelativePath", {
      value: "sources/chapter/story.txt",
    });
    await createAssetImport("p1", [file], "ATTACH_SOURCE", "folder-key");
    await testModelConnection({
      type: "vlm",
      base_url: "https://example.test/v1",
      api_key: "secret",
      model_name: "qwen3.7-plus",
      protocol: "OpenAI 协议",
    });
    expect((calls[0].body as { files: File }).files.name).toBe(
      "sources/chapter/story.txt",
    );
    expect(
      (calls[0].body as { postIngestAction: string }).postIngestAction,
    ).toBe("ATTACH_SOURCE");
    expect(calls[0].headers["idempotency-key"]).toBe("folder-key");
    expect(calls[1]).toMatchObject({
      method: "POST",
      url: "/api/qwenpaw-creator/models/test",
      body: {
        type: "vlm",
        base_url: "https://example.test/v1",
        api_key: "secret",
        model_name: "qwen3.7-plus",
        protocol: "OpenAI 协议",
      },
    });
  });

  it("saves the complete single-file model configuration", async () => {
    const { calls } = installMockFetch([
      {
        match: "/models/config",
        method: "POST",
        response: { json: { ok: true } },
      },
    ]);
    await saveModelConfig({
      llm: {
        enabled: true,
        model_name: "configured-model",
        api_key: "new-secret",
        base_url: "https://example.test/v1",
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
      asr: {
        enabled: false,
        model_name: "fun-asr",
        api_key: "",
        base_url: "https://dashscope.aliyuncs.com/api/v1",
        protocol: "DashScope Fun-ASR",
        custom_protocol: "",
        provider: "fun-asr",
        language: "",
        reuse_llm_key: true,
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
        access_key_id: "LTAI-x",
        access_key_secret: "oss-secret",
        endpoint: "https://oss-cn-hangzhou.aliyuncs.com",
        bucket: "creator-store",
        public_base_url: "",
        policy_api_key: "",
      },
      executionAuthorization: { mode: "required" },
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      method: "POST",
      url: "/api/qwenpaw-creator/models/config",
      body: {
        llm: { model_name: "configured-model", api_key: "new-secret" },
      },
    });
    expect(calls[0].headers["idempotency-key"]).toMatch(/^model-config-/);
    expect(
      (calls[0].body as { oss: Record<string, unknown> }).oss,
    ).toMatchObject({
      enabled: false,
      access_key_id: "LTAI-x",
      access_key_secret: "oss-secret",
      endpoint: "https://oss-cn-hangzhou.aliyuncs.com",
    });
  });
});
