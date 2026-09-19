import type { JobInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatDateTime } from "./run-timeline";

interface Props {
  jobs: JobInfo[] | null;
  agentName: (id: string) => string;
  onRunNow: (jobId: string) => void;
}

/** Every agent's schedules with their next and last run, and a way to fire one now. */
export function JobsPanel({ jobs, agentName, onRunNow }: Props) {
  if (jobs === null) return <p className="muted">{vi.loadFailed}</p>;
  if (jobs.length === 0) return <p className="muted">{vi.jobsEmpty}</p>;
  return (
    <ul className="job-list" data-testid="jobs">
      {jobs.map((job) => (
        <li key={job.id} className={`job ${job.enabled ? "" : "disabled"}`} data-testid="job">
          <div className="job-head">
            <span className="job-name">
              <strong>{agentName(job.agent_id)}</strong> · {job.name}
              {!job.enabled && <span className="badge warn"> {vi.jobDisabled}</span>}
              {job.running && <span className="badge live"> {vi.jobRunning}</span>}
            </span>
            <button
              type="button"
              className="ghost"
              disabled={job.running}
              onClick={() => onRunNow(job.id)}
              aria-label={`${vi.runNow}: ${job.name}`}
            >
              ▶ {vi.runNow}
            </button>
          </div>
          <div className="job-meta muted">
            <code>{job.cron ?? job.every}</code> · {job.prompt ? vi.jobKindPrompt : vi.jobKindCommand}
          </div>
          <div className="job-meta muted">
            {vi.jobNext}: {job.next_run ? formatDateTime(job.next_run) : vi.jobDisabled} · {vi.jobLast}:{" "}
            {job.last_run
              ? `${formatDateTime(job.last_run.started_at)} (${vi.runStatus[job.last_run.status]})`
              : vi.jobNever}
          </div>
        </li>
      ))}
    </ul>
  );
}
