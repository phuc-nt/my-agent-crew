import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { RunCard } from "./run-timeline";

interface Props {
  jobId: string;
  agentName: string;
  onOpenConversation?: (conversationId: string) => void;
}

/** The past runs of one schedule, newest first, fetched when the section is opened. */
export function JobRunHistory({ jobId, agentName, onOpenConversation }: Props) {
  const [runs, setRuns] = useState<RunInfo[] | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.listJobRuns(jobId).then(
      (loaded) => !cancelled && setRuns(loaded),
      () => !cancelled && setRuns(null),
    );
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (runs === undefined) return <p className="muted">{vi.loading}</p>;
  if (runs === null) return <p className="muted">{vi.loadFailed}</p>;
  if (runs.length === 0) return <p className="muted">{vi.jobHistoryEmpty}</p>;
  return (
    <div className="job-runs" data-testid="job-runs">
      {runs.map((run) => (
        <RunCard key={run.id} run={run} agentName={agentName} onOpenConversation={onOpenConversation} />
      ))}
    </div>
  );
}
