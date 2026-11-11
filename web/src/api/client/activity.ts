import type { JobInfo, ReportInfo, RunInfo, SpendInfo, StatsInfo } from "../types";
import { query, request } from "./http";

export const activityApi = {
  listRuns: (params: { limit?: number; agent_id?: string; conversation_id?: string } = {}) =>
    request<RunInfo[]>(`/activity/runs${query(params)}`),
  listReports: (limit?: number) => request<ReportInfo[]>(`/activity/reports${query({ limit })}`),
  getRun: (id: string) => request<RunInfo>(`/activity/runs/${encodeURIComponent(id)}`),
  stats: () => request<StatsInfo>("/stats"),
  spend: () => request<SpendInfo>("/spend"),
  listJobs: () => request<JobInfo[]>("/jobs"),
  runJob: (jobId: string) =>
    request<{ job_id: string; status: string }>(`/jobs/${jobId}/run`, { method: "POST" }),
  setJobEnabled: (jobId: string, enabled: boolean) =>
    request<JobInfo>(`/jobs/${jobId}/state`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  listJobRuns: (jobId: string, limit?: number) =>
    request<RunInfo[]>(`/jobs/${jobId}/runs${query({ limit })}`),
};
