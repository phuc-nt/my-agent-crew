import type { JobInfo, RunStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { formatDateTime } from "./run-timeline";

// The badge tones the rest of the page already reads: green for done, red for a
// failure, amber for a run that stopped or is waiting on the person, the live fill
// for one still going.
const TONE: Record<RunStatus, string> = {
  done: "ok",
  error: "danger",
  halted: "warn",
  awaiting_approval: "warn",
  running: "live",
};

/** How many schedules ended their latest run in an error: the count the nav shows. */
export function failingJobs(jobs: JobInfo[] | null): number {
  return (jobs ?? []).filter((job) => job.last_run?.status === "error").length;
}

interface Props {
  job: JobInfo;
  onOpenRun?: (runId: string) => void;
}

/**
 * The latest run of a schedule on the row itself: how it ended, when, and what it
 * said. Whether this morning's brief went out is the question the jobs list is opened
 * for, and it used to take opening the history and a run card to answer.
 */
export function JobLastRun({ job, onOpenRun }: Props) {
  const last = job.last_run;
  return (
    <div className="job-meta job-last muted" data-testid="job-last">
      <span>{vi.jobLast}:</span>
      {last ? (
        <>
          <span className={`badge ${TONE[last.status]}`}>{vi.runStatus[last.status]}</span>
          <time dateTime={last.started_at}>{formatDateTime(last.started_at)}</time>
          {onOpenRun && (
            <button
              type="button"
              className="link-button"
              aria-label={vi.jobRow.openRunOf(job.name)}
              onClick={() => onOpenRun(last.id)}
            >
              {vi.replay.openLink}
            </button>
          )}
          {last.summary && <p className="job-last-summary">{last.summary}</p>}
        </>
      ) : (
        <span>{vi.jobNever}</span>
      )}
    </div>
  );
}
