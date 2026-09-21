import { readSse } from "./sse";
import type {
  ActivityPayload,
  AgentDetail,
  AgentEvent,
  AgentInfo,
  AgentMemory,
  ApprovalInfo,
  Conversation,
  ConversationDetail,
  ConversationPatch,
  FactBody,
  FactInfo,
  InstallRequest,
  InstallResult,
  JobInfo,
  MemoryHit,
  MemoryProposal,
  RunInfo,
  SettingsInfo,
  StatsInfo,
  TemplateInfo,
  UserMemory,
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
  templates: () => request<TemplateInfo[]>("/templates"),
  listAgents: () => request<AgentInfo[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${encodeURIComponent(id)}`),
  installTemplate: (body: InstallRequest) =>
    request<InstallResult>("/agents/install", { method: "POST", body: JSON.stringify(body) }),
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
    always = false,
  ) =>
    stream(
      `/conversations/${id}/approvals/${approvalId}`,
      always ? { approve, always: true } : { approve },
      onEvent,
    ),
  listApprovals: (limit?: number) => request<ApprovalInfo[]>(`/approvals${query({ limit })}`),
  listRuns: (params: { limit?: number; agent_id?: string } = {}) =>
    request<RunInfo[]>(`/activity/runs${query(params)}`),
  getRun: (id: string) => request<RunInfo>(`/activity/runs/${id}`),
  stats: () => request<StatsInfo>("/stats"),
  listJobs: () => request<JobInfo[]>("/jobs"),
  runJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${jobId}/run`, { method: "POST" }),
  setJobEnabled: (jobId: string, enabled: boolean) =>
    request<JobInfo>(`/jobs/${jobId}/state`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  listJobRuns: (jobId: string, limit?: number) =>
    request<RunInfo[]>(`/jobs/${jobId}/runs${query({ limit })}`),
  getUserMemory: () => request<UserMemory>("/memory/user"),
  putUserMd: (userMd: string) =>
    request<UserMemory>("/memory/user", { method: "PUT", body: JSON.stringify({ user_md: userMd }) }),
  putFact: (name: string, body: FactBody) =>
    request<FactInfo>(`/memory/user/facts/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteFact: (name: string) =>
    request<void>(`/memory/user/facts/${encodeURIComponent(name)}`, { method: "DELETE" }),
  getAgentMemory: (agentId: string) =>
    request<AgentMemory>(`/agents/${encodeURIComponent(agentId)}/memory`),
  putAgentMemory: (agentId: string, memoryMd: string) =>
    request<AgentMemory>(`/agents/${encodeURIComponent(agentId)}/memory`, {
      method: "PUT",
      body: JSON.stringify({ memory_md: memoryMd }),
    }),
  getNote: (agentId: string, day: string) =>
    request<{ day: string; body: string }>(`/agents/${encodeURIComponent(agentId)}/memory/notes/${day}`),
  putNote: (agentId: string, day: string, body: string) =>
    request<{ day: string; body: string }>(
      `/agents/${encodeURIComponent(agentId)}/memory/notes/${day}`,
      { method: "PUT", body: JSON.stringify({ body }) },
    ),
  consolidateMemory: (agentId: string) =>
    request<{ agent_id: string; run_source: string }>(
      `/agents/${encodeURIComponent(agentId)}/memory/consolidate`,
      { method: "POST" },
    ),
  searchMemory: (q: string, agentId?: string) =>
    request<{ hits: MemoryHit[] }>(`/memory/search${query({ q, agent_id: agentId })}`),
  listProposals: (status?: string) =>
    request<{ proposals: MemoryProposal[] }>(`/memory/proposals${query({ status })}`),
  decideProposal: (id: string, approve: boolean) =>
    request<MemoryProposal>(`/memory/proposals/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),
};

export type Api = typeof api;
