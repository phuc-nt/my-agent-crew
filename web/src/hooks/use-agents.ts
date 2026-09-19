import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AgentInfo, JobInfo, StatsInfo } from "../api/types";

export interface CrewController {
  agents: AgentInfo[];
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  agentName: (id: string) => string;
  refreshJobs: () => Promise<void>;
  refreshStats: () => Promise<void>;
  runJob: (jobId: string) => Promise<void>;
}

/** Agents, their schedules and the cost totals — the slow-moving side of the UI. */
export function useCrew(): CrewController {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [jobs, setJobs] = useState<JobInfo[] | null>(null);
  const [stats, setStats] = useState<StatsInfo | null>(null);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await api.listJobs());
    } catch {
      setJobs(null);
    }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api.stats());
    } catch {
      setStats(null);
    }
  }, []);

  useEffect(() => {
    api.listAgents().then(setAgents, () => setAgents([]));
    void refreshJobs();
    void refreshStats();
  }, [refreshJobs, refreshStats]);

  const runJob = useCallback(
    async (jobId: string) => {
      await api.runJob(jobId);
      await refreshJobs();
    },
    [refreshJobs],
  );

  const agentName = useCallback(
    (id: string) => agents.find((a) => a.id === id)?.name ?? id,
    [agents],
  );

  return { agents, jobs, stats, agentName, refreshJobs, refreshStats, runJob };
}
