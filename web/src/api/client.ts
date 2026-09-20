import { readSse } from "./sse";
import type {
  ActivityPayload,
  AgentDetail,
  AgentEvent,
  AgentInfo,
  Conversation,
  ConversationDetail,
  ConversationPatch,
  JobInfo,
  RunInfo,
  SettingsInfo,
  StatsInfo,
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

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** URL of a file inside an agent's workspace, for images the agent produced. */
export function agentFileUrl(agentId: string, path: string): string {
  return `/api/agents/${encodeURIComponent(agentId)}/files${query({ path })}`;
}

/**
 * Long-lived subscription to every agent's activity. Reconnects are left to the
 * browser's EventSource; the server replays a snapshot of live runs on each connect.
 */
export function subscribeActivity(
  onPayload: (payload: ActivityPayload) => void,
  onStatus: (connected: boolean) => void = () => {},
): () => void {
  const source = new EventSource("/api/activity/stream");
  const handle = (message: MessageEvent<string>) =>
    onPayload(JSON.parse(message.data) as ActivityPayload);
  for (const name of ["snapshot", "run", "event"]) source.addEventListener(name, handle);
  source.onopen = () => onStatus(true);
  source.onerror = () => onStatus(false);
  return () => source.close();
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  settings: () => request<SettingsInfo>("/settings"),
  listAgents: () => request<AgentInfo[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${encodeURIComponent(id)}`),
  listConversations: (agentId?: string) =>
    request<Conversation[]>(`/conversations${query({ agent_id: agentId })}`),
  createConversation: (body: ConversationPatch & { agent_id?: string } = {}) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(body) }),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  patchConversation: (id: string, body: ConversationPatch) =>
    request<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),
  summarizeConversation: (id: string) =>
    request<{ id: string; summary: string }>(`/conversations/${id}/summary`, { method: "POST" }),
  sendMessage: (id: string, text: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) =>
    stream(`/conversations/${id}/messages`, { text }, onEvent, signal),
  resolveApproval: (
    id: string,
    approvalId: string,
    approve: boolean,
    onEvent: (e: AgentEvent) => void,
  ) => stream(`/conversations/${id}/approvals/${approvalId}`, { approve }, onEvent),
  listRuns: (params: { limit?: number; agent_id?: string } = {}) =>
    request<RunInfo[]>(`/activity/runs${query(params)}`),
  getRun: (id: string) => request<RunInfo>(`/activity/runs/${id}`),
  stats: () => request<StatsInfo>("/stats"),
  listJobs: () => request<JobInfo[]>("/jobs"),
  runJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${jobId}/run`, { method: "POST" }),
};

export type Api = typeof api;
