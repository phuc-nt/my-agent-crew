import type {
  AgentDetail,
  AgentInfo,
  AgentPatch,
  AgentSaved,
  InstallRequest,
  InstallResult,
  RegistryTool,
  SettingsInfo,
  TemplateInfo,
} from "../types";
import { request } from "./http";

export const agentsApi = {
  health: () => request<{ status: string; version: string }>("/health"),
  settings: () => request<SettingsInfo>("/settings"),
  templates: () => request<TemplateInfo[]>("/templates"),
  listAgents: () => request<AgentInfo[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${encodeURIComponent(id)}`),
  installTemplate: (body: InstallRequest) =>
    request<InstallResult>("/agents/install", { method: "POST", body: JSON.stringify(body) }),
  createAgent: (agentId: string, profile: AgentPatch) =>
    request<AgentSaved>("/agents", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, profile }),
    }),
  patchAgent: (id: string, profile: AgentPatch) =>
    request<AgentSaved>(`/agents/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ profile }),
    }),
  deleteAgent: (id: string) =>
    request<{ removed: string; kept_at: string }>(`/agents/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  personaFile: (agentId: string, name: string) =>
    request<{ name: string; content: string; chars: number }>(
      `/agents/${encodeURIComponent(agentId)}/files/${encodeURIComponent(name)}`,
    ),
  putPersonaFile: (agentId: string, name: string, content: string) =>
    request<{ name: string; chars: number }>(
      `/agents/${encodeURIComponent(agentId)}/files/${encodeURIComponent(name)}`,
      { method: "PUT", body: JSON.stringify({ content }) },
    ),
  agentPrompt: (agentId: string) =>
    request<{ prompt: string; chars: number; opening: string; opening_chars: number }>(
      `/agents/${encodeURIComponent(agentId)}/prompt`,
    ),
  reloadAgents: () => request<{ added: string[] }>("/agents/reload", { method: "POST" }),
  listTools: () => request<RegistryTool[]>("/tools"),
};
