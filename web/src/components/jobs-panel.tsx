import { useState } from "react";
import type { JobInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { JobRunHistory } from "./job-run-history";
import { formatDateTime } from "./run-timeline";

const JOB_KINDS: Record<string, string> = {
  prompt: vi.jobKindPrompt,
  command: vi.jobKindCommand,
  consolidate: vi.jobKindConsolidate,
};

interface Props {
  jobs: JobInfo[] | null;
  agentName: (id: string) => string;
  onRunNow: (jobId: string) => void;
  /** Pause or resume a schedule at runtime without editing its profile. */
  onToggle: (jobId: string, enabled: boolean) => void;
  onOpenConversation?: (conversationId: string) => void;
}

/** Every agent's schedules with their next and last run, a pause switch, run history and run-now. */
export function JobsPanel({ jobs, agentName, onRunNow, onToggle, onOpenConversation }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  if (jobs === null) return <p className="muted">{vi.loadFailed}</p>;
  if (jobs.length === 0) return <p className="muted">{vi.jobsEmpty}</p>;
  return (
    <ul className="job-list" data-testid="jobs">
      {jobs.map((job) => {
        // A schedule switched off in agent.yaml cannot be resumed from here.
        const offInProfile = !job.enabled && !job.paused;
        return (
          <li key={job.id} className={`job ${job.enabled ? "" : "disabled"}`} data-testid="job">
            <div className="job-head">
              <span className="job-name">
                <strong>{agentName(job.agent_id)}</strong> · {job.name}
                {offInProfile && <span className="badge warn"> {vi.jobDisabled}</span>}
                {job.paused && <span className="badge warn"> {vi.jobPaused}</span>}
                {job.running && <span className="badge live"> {vi.jobRunning}</span>}
              </span>
              <span className="job-actions">
                <label className="toggle" title={offInProfile ? vi.jobDisabledInProfile : undefined}>
                  <input
                    type="checkbox"
                    className="switch"
                    checked={!job.paused}
                    disabled={offInProfile}
                    aria-label={`${vi.jobEnabled}: ${job.name}`}
                    onChange={(event) => onToggle(job.id, event.currentTarget.checked)}
                  />
                  {vi.jobEnabled}
                </label>
                <button
                  type="button"
                  className="ghost"
                  disabled={job.running}
                  onClick={() => onRunNow(job.id)}
                  aria-label={`${vi.runNow}: ${job.name}`}
                >
                  ▶ {vi.runNow}
                </button>
              </span>
            </div>
            <div className="job-meta muted">
              <code>{job.cron ?? job.every}</code> · {JOB_KINDS[job.kind]}
            </div>
            {job.skills.length > 0 && (
              <div className="job-meta muted">
                {vi.jobSkills}: <code>{job.skills.join(", ")}</code>
              </div>
            )}
            <div className="job-meta muted">
              {vi.jobNext}: {job.next_run ? formatDateTime(job.next_run) : vi.jobDisabled} · {vi.jobLast}:{" "}
              {job.last_run
                ? `${formatDateTime(job.last_run.started_at)} (${vi.runStatus[job.last_run.status]})`
                : vi.jobNever}
              {" · "}
              <button
                type="button"
                className="link-button"
                aria-expanded={open === job.id}
                onClick={() => setOpen((current) => (current === job.id ? null : job.id))}
              >
                {open === job.id ? vi.hideHistory : vi.showHistory}
              </button>
            </div>
            {open === job.id && (
              <JobRunHistory
                jobId={job.id}
                agentName={agentName(job.agent_id)}
                onOpenConversation={onOpenConversation}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}
