import type { CreatorApiError } from "@/contracts/creator";

export const CREATOR_API_BASE = "/api/qwenpaw-creator";

type HostWindow = Window & {
  QwenPaw?: { host?: { getApiToken?: () => string } };
};

export class CreatorHttpError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;

  constructor(status: number, error: Partial<CreatorApiError> = {}) {
    super(error.message || `Creator 请求失败（${status}）`);
    this.name = "CreatorHttpError";
    this.status = status;
    this.code = error.code || `HTTP_${status}`;
    this.retryable = error.retryable ?? false;
    this.details = error.details ?? {};
  }
}

export function creatorApiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${CREATOR_API_BASE}${normalized}`;
}

export function newClientId(prefix = "client"): string {
  const id =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${id}`;
}

function hostToken(): string | null {
  try {
    const current = window as HostWindow;
    const parent = window.parent as HostWindow;
    return (
      parent?.QwenPaw?.host?.getApiToken?.() ||
      current.QwenPaw?.host?.getApiToken?.() ||
      null
    );
  } catch {
    return null;
  }
}

export function creatorHeaders(initial?: HeadersInit): Headers {
  const headers = new Headers(initial);
  const token = hostToken();
  if (token && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function errorFrom(response: Response): Promise<CreatorHttpError> {
  let body: Partial<CreatorApiError> = {};
  try {
    body = (await response.json()) as Partial<CreatorApiError>;
  } catch {
    body = { message: response.statusText };
  }
  return new CreatorHttpError(response.status, body);
}

/** Perform an authenticated Creator request without interpreting its status. */
export async function creatorFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = creatorHeaders(init.headers);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(creatorApiUrl(path), { ...init, headers });
}

export async function creatorRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await creatorFetch(path, init);
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}
