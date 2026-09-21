import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AgentInfo, InstallResult, JobInfo, StatsInfo } from "../api/types";

export interface CrewController {
  agents: AgentInfo[];
  /** The agent the person talks to; null until the crew has loaded. */
  master: AgentInfo | null;
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  agentName: (id: string) => string;
  reload: () => Promise<void>;
  refreshJobs: () => Promise<void>;
  refreshStats: () => Promise<void>;
  /** Installs a bundled template and reloads the crew so the master can reach it. */
  installTemplate: (template: string) => Promise<InstallResult>;
  runJob: (jobId: string) => Promise<void>;
  setJobEnabled: (jobId: string, enabled: boolean) => Promise<void>;
}

/** Agents, their schedules and the cost totals — the slow-moving side of the UI. */
export function useCrew(): CrewController {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [jobs, setJobs] = useState<JobInfo[] | null>(null);
  const [stats, setStats] = useState<StatsInfo | null>(null);

  const reload = useCallback(async () => {
    try {
      setAgents(await api.listAgents());
    } catch {
      setAgents([]);
    }
  }, []);

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
    void reload();
    void refreshJobs();
    void refreshStats();
  }, [reload, refreshJobs, refreshStats]);

  const installTemplate = useCallback(
    async (template: string) => {
      const result = await api.installTemplate({ template });
      await reload();
      await refreshJobs();
      return result;
    },
    [reload, refreshJobs],
  );

  const runJob = useCallback(
    async (jobId: string) => {
      await api.runJob(jobId);
      await refreshJobs();
    },
    [refreshJobs],
  );

  const setJobEnabled = useCallback(async (jobId: string, enabled: boolean) => {
    const updated = await api.setJobEnabled(jobId, enabled);
    setJobs((current) => current?.map((job) => (job.id === updated.id ? updated : job)) ?? null);
  }, []);

  const agentName = useCallback(
    (id: string) => agents.find((a) => a.id === id)?.name ?? id,
    [agents],
  );

  const master = agents.find((a) => a.is_master) ?? agents[0] ?? null;

  return {
    agents,
    master,
    jobs,
    stats,
    agentName,
    reload,
    refreshJobs,
    refreshStats,
    installTemplate,
    runJob,
    setJobEnabled,
  };
}
