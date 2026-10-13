import type { AgentBrowser } from "../types";
import { request } from "./http";

const browserOf = (agentId: string) => `/agents/${encodeURIComponent(agentId)}/browser`;

export const browserApi = {
  /** Reads what runs; it starts nothing. A server older than the route answers 404. */
  agentBrowser: (agentId: string) => request<AgentBrowser>(browserOf(agentId)),
  /** Stops the browser now; `stopped` is false when there was none to stop. */
  stopAgentBrowser: (agentId: string) => request<{ stopped: boolean }>(`${browserOf(agentId)}/stop`, { method: "POST" }),
  /** Closes one tab now; a 404 says the tab is already gone. */
  closeAgentBrowserTab: (agentId: string, tabId: number) =>
    request<{ closed: number }>(`${browserOf(agentId)}/tabs/${encodeURIComponent(tabId)}`, { method: "DELETE" }),
  /** Opens the window a person signs in through, on `url` when one is given. One that is
   *  open already is answered as it is. A 409 or a 422 says in a sentence why none opened. */
  openAgentBrowserLogin: (agentId: string, url: string) =>
    request<{ open: boolean; until: string }>(`${browserOf(agentId)}/login`, {
      method: "POST",
      body: JSON.stringify(url ? { url } : {}),
    }),
  /** Closes that window; `closed` is false when there was none to close. */
  closeAgentBrowserLogin: (agentId: string) => request<{ closed: boolean }>(`${browserOf(agentId)}/login/done`, { method: "POST" }),
};
