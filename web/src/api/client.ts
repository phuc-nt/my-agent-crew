import { readSse } from "./sse";
import type {
  AgentEvent,
  Conversation,
  ConversationDetail,
  ConversationPatch,
  SettingsInfo,
} from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

async function stream(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  if (!response.body) throw new ApiError(response.status, "empty stream");
  await readSse(response.body, onEvent);
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  settings: () => request<SettingsInfo>("/settings"),
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (body: ConversationPatch = {}) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(body) }),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  patchConversation: (id: string, body: ConversationPatch) =>
    request<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),
  sendMessage: (id: string, text: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) =>
    stream(`/conversations/${id}/messages`, { text }, onEvent, signal),
  resolveApproval: (
    id: string,
    approvalId: string,
    approve: boolean,
    onEvent: (e: AgentEvent) => void,
  ) => stream(`/conversations/${id}/approvals/${approvalId}`, { approve }, onEvent),
};

export type Api = typeof api;
