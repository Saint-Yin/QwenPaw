import { creatorRequest } from "./client";

function project(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

export interface VoiceCapabilities {
  model: string;
  configured: boolean;
  /** True when the TTS model can design a timbre from a plain-language prompt. */
  supportsDesign: boolean;
}

export function getVoiceCapabilities(
  projectId: string,
): Promise<VoiceCapabilities> {
  return creatorRequest(`${project(projectId)}/voice-capabilities`);
}

export interface CreateCharacterVoiceRequest {
  characterRef: string;
  voicePrompt?: string;
  previewText?: string;
  sampleSourceVersionId?: string;
  sampleText?: string;
  preferredName?: string;
}

export interface CreateCharacterVoiceResult {
  ok: boolean;
  status: string;
  entityId: string;
  voiceBound: boolean;
  voiceOrigin: string;
  sampleSourceVersionId: string | null;
  generation: number;
  etag: string;
  replayed: boolean;
}

/** Direct enrollment — same executor as the agent tool, no agent turn. */
export function createCharacterVoice(
  projectId: string,
  body: CreateCharacterVoiceRequest,
): Promise<CreateCharacterVoiceResult> {
  return creatorRequest(
    `${project(projectId)}/character-voice`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    // Voice enrollment is a provider round-trip (10-30s); don't cut it off.
    { timeoutMs: 120_000 },
  );
}
