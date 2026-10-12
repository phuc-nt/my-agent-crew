import type { JobFailing, JobInfo, RunStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { dayClock, timeAgo } from "../lib/relative-time";
import { AtClock } from "./job-clock";
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
  /** The time the row's other labels read against, so one frame tells one time. */
  now: Date;
  onOpenRun?: (runId: string) => void;
}

/**
 * The latest run of a schedule on the row itself: how it ended, when, and what it
 * said. Whether this morning's brief went out is the question the jobs list is opened
 * for, and it used to take opening the history and a run card to answer.
 */
export function JobLastRun({ job, now, onOpenRun }: Props) {
  const last = job.last_run;
  return (
    <div className="job-meta job-last muted" data-testid="job-last">
      <span>{vi.jobLast}:</span>
      {last ? (
        <>
          <span className={`badge ${TONE[last.status]}`}>{vi.runStatus[last.status]}</span>
          {/* Read the way the next run is: relative and on the viewer's calendar, with the
              clock time after it. The span keeps the badge, time and link on one line. */}
          <span>
            <time dateTime={last.started_at} title={formatDateTime(last.started_at)}>
              {timeAgo(last.started_at, now)}
            </time>
            <AtClock iso={last.started_at} words={timeAgo(last.started_at, now)} />
          </span>
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
      {job.failing && <FailingStreak failing={job.failing} now={now} />}
    </div>
  );
}

/** A job that keeps failing, in a sentence under its last run: one failed run reads the
 *  same on the badge above as a job that has been down for a week, and whether the owner
 *  was told about it is on no other page. */
function FailingStreak({ failing, now }: { failing: JobFailing; now: Date }) {
  const t = vi.jobRow;
  // A notice on its way is said only while none of this streak has got through: one that
  // is being sent again leaves the row saying when the owner was last told.
  const told = failing.told_at
    ? t.streakTold(dayClock(failing.told_at, now), failing.next_notice_at && dayClock(failing.next_notice_at, now))
    : failing.telling ? t.streakTelling : t.streakUntold;
  return (
    <p className="job-failing" data-testid="job-failing">
      {t.streak(failing.count, dayClock(failing.since, now))} {told}
    </p>
  );
}
