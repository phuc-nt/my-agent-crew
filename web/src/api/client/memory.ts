import type {
  AgentMemory,
  ContentHit,
  FactBody,
  FactInfo,
  MemoryHit,
  MemoryProposal,
  UserMemory,
  WikiList,
  WikiPage,
  WikiPageEdit,
  WikiReport,
} from "../types";
import { query, request } from "./http";

const wikiPath = (agentId: string) => `/agents/${encodeURIComponent(agentId)}/memory/wiki`;

export const memoryApi = {
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
  searchMessages: (q: string, signal?: AbortSignal) =>
    request<{ hits: ContentHit[] }>(`/messages/search${query({ q })}`, { signal }),
  listProposals: (status?: string) =>
    request<{ proposals: MemoryProposal[] }>(`/memory/proposals${query({ status })}`),
  decideProposal: (id: string, approve: boolean) =>
    request<MemoryProposal>(`/memory/proposals/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),
  listWiki: (agentId: string, q?: string) =>
    request<WikiList>(`${wikiPath(agentId)}${query({ q })}`),
  getWikiPage: (agentId: string, slug: string) =>
    request<WikiPage>(`${wikiPath(agentId)}/pages/${encodeURIComponent(slug)}`),
  putWikiPage: (agentId: string, slug: string, body: WikiPageEdit) =>
    request<WikiPage>(`${wikiPath(agentId)}/pages/${encodeURIComponent(slug)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteWikiPage: (agentId: string, slug: string) =>
    request<{ slug: string; deleted: boolean }>(
      `${wikiPath(agentId)}/pages/${encodeURIComponent(slug)}`,
      { method: "DELETE" },
    ),
  getWikiReport: (agentId: string) => request<WikiReport>(`${wikiPath(agentId)}/report`),
  compileWiki: (agentId: string) =>
    request<{ agent_id: string; run_source: string }>(`${wikiPath(agentId)}/compile`, {
      method: "POST",
    }),
};
