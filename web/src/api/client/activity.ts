import type { JobInfo, RunInfo, StatsInfo } from "../types";
import { query, request } from "./http";

export const activityApi = {
  listRuns: (params: { limit?: number; agent_id?: string; conversation_id?: string } = {}) =>
    request<RunInfo[]>(`/activity/runs${query(params)}`),
  getRun: (id: string) => request<RunInfo>(`/activity/runs/${encodeURIComponent(id)}`),
  stats: () => request<StatsInfo>("/stats"),
  listJobs: () => request<JobInfo[]>("/jobs"),
  runJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${jobId}/run`, { method: "POST" }),
  setJobEnabled: (jobId: string, enabled: boolean) =>
    request<JobInfo>(`/jobs/${jobId}/state`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  listJobRuns: (jobId: string, limit?: number) =>
    request<RunInfo[]>(`/jobs/${jobId}/runs${query({ limit })}`),
  // A profile job (`origin: "profile"`) 409s here; the caller only offers this for a chat
  // job in the first place, but the server is what actually refuses it.
  deleteJob: (jobId: string) => request<void>(`/jobs/${jobId}`, { method: "DELETE" }),
};
