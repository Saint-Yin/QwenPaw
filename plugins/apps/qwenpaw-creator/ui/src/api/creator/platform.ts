import { creatorRequest, jsonBody } from "./client";

/**
 * Platform one-click model configuration.
 *
 * Creator runs as a container on a QwenPaw subdomain, and the platform hands
 * out its model key to the browser only: the credential endpoint authenticates
 * with the `console_token` cookie that the subdomain gateway checks against the
 * deployment owner. The Creator backend cannot call it - it holds no platform
 * identity, and the platform explicitly refuses its login JWT - so the key
 * travels browser -> Creator backend, which is the only place able to persist
 * it into the model configuration.
 */

export const PLATFORM_CREDENTIALS_PATH = "/api/v1/qwenpaw/creator-credentials";

export interface PlatformCredentials {
  user_id?: string;
  deployment_id?: string;
  api_key: string;
  /** True when this call minted the key rather than returning an existing one. */
  api_key_created?: boolean;
  display_available_credits?: number | string | null;
  balance_credits?: number | string | null;
  chat_completions_url: string;
  /** Redundant with `api_key`; never consumed, so nothing can double the Bearer. */
  auth_header?: string;
}

export interface PlatformApplySection {
  section: string;
  model_name: string;
  ready: boolean;
  /** True when the preset replaced whatever the section held before. */
  replaced?: boolean;
}

export interface PlatformApplyResult {
  ok: boolean;
  base_url: string;
  sections: PlatformApplySection[];
}

function requireText(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`平台响应缺少 ${field}`);
  }
  return value.trim();
}

/**
 * Read the credentials of this deployment.
 *
 * A bare same-origin fetch on purpose: the platform ignores Authorization here
 * (its credential is the cookie, not Creator's bearer), and `credentials` must
 * opt the cookie back in for callers that default to `same-origin` semantics.
 */
export async function fetchPlatformCredentials(): Promise<PlatformCredentials> {
  const response = await fetch(PLATFORM_CREDENTIALS_PATH, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? "平台未识别本子域的登录会话（console_token 缺失或已过期）"
        : `平台凭据获取失败：HTTP ${response.status}`,
    );
  }
  const payload: unknown = await response.json().catch(() => null);
  // Documented shape wraps the fields in `data`; tolerate a bare object so a
  // gateway-side simplification does not break the button.
  const body =
    payload && typeof payload === "object" && "data" in payload
      ? (payload as { data: unknown }).data
      : payload;
  if (!body || typeof body !== "object") {
    throw new Error("平台响应不是对象");
  }
  const record = body as Record<string, unknown>;
  return {
    ...record,
    api_key: requireText(record.api_key, "api_key"),
    chat_completions_url: requireText(
      record.chat_completions_url,
      "chat_completions_url",
    ),
  } as PlatformCredentials;
}

/** Point every proxy-served section at the platform with the issued key. */
export function applyPlatformCredentials(
  credentials: Pick<PlatformCredentials, "api_key" | "chat_completions_url">,
): Promise<PlatformApplyResult> {
  return creatorRequest("/models/platform-autoconfigure", {
    method: "POST",
    body: jsonBody({
      api_key: credentials.api_key,
      chat_completions_url: credentials.chat_completions_url,
    }),
  });
}
