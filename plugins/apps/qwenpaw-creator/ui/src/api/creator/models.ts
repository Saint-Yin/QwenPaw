import type {
  ModelConfigData,
  ModelConnectionTestRequest,
  ConnectionTestResponse,
  OssConfig,
} from "@/contracts/creator";
import { creatorRequest, jsonBody, newClientId } from "./client";

export function getModelConfig(): Promise<ModelConfigData> {
  return creatorRequest("/models/config");
}

export function saveModelConfig(
  config: ModelConfigData,
): Promise<{ ok: boolean }> {
  const id = newClientId("model-config");
  return creatorRequest("/models/config", {
    method: "POST",
    headers: { "Idempotency-Key": id },
    body: jsonBody(config),
  });
}

export function testModelConnection(
  request: ModelConnectionTestRequest,
): Promise<ConnectionTestResponse> {
  return creatorRequest("/models/test", {
    method: "POST",
    body: jsonBody(request),
  });
}

export function testOssConnection(
  request: OssConfig,
): Promise<ConnectionTestResponse> {
  return creatorRequest("/models/test-oss", {
    method: "POST",
    body: jsonBody(request),
  });
}

export function patchModelConfigSection(
  section: string,
  data: Record<string, unknown>,
): Promise<{ ok: boolean }> {
  const id = newClientId("model-config-patch");
  return creatorRequest(`/models/config/${section}`, {
    method: "PATCH",
    headers: { "Idempotency-Key": id },
    body: jsonBody(data),
  });
}

export function patchExecutionAuthorization(
  mode: "required" | "allow_all",
): Promise<{ ok: boolean }> {
  const id = newClientId("execution-auth");
  return creatorRequest("/models/config/execution-authorization", {
    method: "PATCH",
    headers: { "Idempotency-Key": id },
    body: jsonBody({ mode }),
  });
}
