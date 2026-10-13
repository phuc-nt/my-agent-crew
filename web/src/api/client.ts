import { activityApi } from "./client/activity";
import { agentsApi } from "./client/agents";
import { browserApi } from "./client/browser";
import { connectionsApi } from "./client/connections";
import { conversationsApi } from "./client/conversations";
import { query } from "./client/http";
import { memoryApi } from "./client/memory";
import type { ActivityPayload } from "./types";

export { ApiError, query, request } from "./client/http";

/** URL of a file inside an agent's workspace, for images the agent produced. */
export function agentFileUrl(agentId: string, path: string): string {
  return `/api/agents/${encodeURIComponent(agentId)}/files${query({ path })}`;
}

/** A run written out whole, which the server sends as a file to save. */
export function runTrajectoryUrl(runId: string, format: "json" | "md"): string {
  return `/api/activity/runs/${encodeURIComponent(runId)}/trajectory${query({ format })}`;
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
  // The server names each SSE event after its payload type; a type not listed here
  // never reaches the app.
  for (const name of ["snapshot", "run", "event", "conversation", "artifact", "jobs"]) {
    source.addEventListener(name, handle);
  }
  source.onopen = () => onStatus(true);
  source.onerror = () => onStatus(false);
  return () => source.close();
}

export const api = {
  ...agentsApi,
  ...browserApi,
  ...connectionsApi,
  ...conversationsApi,
  ...activityApi,
  ...memoryApi,
};

export type Api = typeof api;
