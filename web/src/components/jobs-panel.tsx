import { useEffect, useRef, useState } from "react";
import type { JobInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { scheduleText } from "../lib/cron-text";
import { timeUntil } from "../lib/relative-time";
import { AtClock } from "./job-clock";
import { JobLastRun } from "./job-last-run";
import { JobRunHistory } from "./job-run-history";
import { formatDateTime } from "./run-timeline";
import { AgentAvatar } from "./ui/agent-avatar";
import { EmptyState } from "./empty-state";
import { Icon } from "./ui/icon";

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
  /** Opens one run on its own page, from the row's last run or its history. The job goes
   *  along so that page's back link returns to this row. */
  onOpenRun?: (runId: string, jobId: string) => void;
  /** Opens the agent's editor on its schedules: where a job is added, changed or turned on. */
  onEditSchedules?: (agentId: string, jobId: string) => void;
  onOpenCrew?: () => void;
  /** The row to bring into view and focus: the one a person came back to. */
  focusJob?: string;
}

/** Every agent's schedules with their next and last run, a pause switch, run history and run-now. */
export function JobsPanel(props: Props) {
  const { jobs, agentName, onRunNow, onToggle, onOpenConversation, onOpenRun, onEditSchedules, onOpenCrew, focusJob } =
    props;
  const [open, setOpen] = useState<string | null>(null);
  const target = useRef<HTMLLIElement>(null);
  const arrived = jobs?.some((job) => job.id === focusJob) ?? false;
  // "sau 3 giờ" and "5 phút" are true for a minute; a list left open on a wall screen
  // redraws once a minute so the countdowns keep moving.
  const [, setMinute] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setMinute((n) => n + 1), 60_000);
    return () => clearInterval(timer);
  }, []);
  // Back from a job's editor or run: on a long list the person was on one row, not at the
  // top. Waits for that row, since a reload reaches here before the jobs do.
  useEffect(() => {
    if (!arrived) return;
    target.current?.scrollIntoView?.({ block: "center" });
    target.current?.focus({ preventScroll: true });
  }, [arrived, focusJob]);
  if (jobs === null) return <p className="muted">{vi.loadFailed}</p>;
  if (jobs.length === 0) {
    const action = onOpenCrew ? { label: vi.jobRow.openCrew, onClick: onOpenCrew } : undefined;
    return <EmptyState icon="clock" says={vi.jobsEmpty} action={action} />;
  }
  return (
    <ul className="job-list" data-testid="jobs">
      {jobs.map((job) => {
        // A schedule switched off in agent.yaml cannot be resumed from here.
        const offInProfile = !job.enabled && !job.paused;
        const offHint = `job-off-${job.id}`;
        const openRun = onOpenRun && ((runId: string) => onOpenRun(runId, job.id));
        return (
          <li
            key={job.id}
            ref={job.id === focusJob ? target : undefined}
            tabIndex={job.id === focusJob ? -1 : undefined}
            className={`job ${job.enabled ? "" : "disabled"}`}
            data-testid="job"
          >
            <div className="job-head">
              <AgentAvatar id={job.agent_id} name={agentName(job.agent_id)} />
              <span className="job-name">
                <strong>{agentName(job.agent_id)}</strong> · {job.name}
                {offInProfile && <span className="badge warn"> {vi.jobDisabled}</span>}
                {job.paused && <span className="badge warn"> {vi.jobPaused}</span>}
                {job.running && <span className="badge live"> {vi.jobRunning}</span>}
              </span>
              <span className="job-actions">
                <label className="toggle">
                  <input
                    type="checkbox"
                    className="switch"
                    checked={!job.paused}
                    disabled={offInProfile}
                    aria-label={`${vi.jobEnabled}: ${job.name}`}
                    aria-describedby={offInProfile ? offHint : undefined}
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
                  <Icon name="play" />
                  {vi.runNow}
                </button>
                {onEditSchedules && (
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => onEditSchedules(job.agent_id, job.id)}
                    aria-label={vi.jobRow.editOf(job.name)}
                  >
                    {vi.jobRow.edit}
                  </button>
                )}
              </span>
            </div>
            {/* Why the switch will not move, on the row: a hover title never shows on a
                phone and is not read out with the switch. */}
            {offInProfile && (
              <p className="job-meta muted" id={offHint}>
                {vi.jobDisabledInProfile}
              </p>
            )}
            <JobTiming job={job} />
            {job.skills.length > 0 && (
              <div className="job-meta muted">
                {vi.jobSkills}: <code>{job.skills.join(", ")}</code>
              </div>
            )}
            <div className="job-meta muted">
              {vi.jobNext}:{" "}
              {/* A job that will not run has no next time: an interval job's is its last run
                  plus the interval, long gone once it has been off for a while. */}
              {job.enabled && job.next_run ? (
                // Relative while it is close, the date once it is not; the clock time follows
                // on the row, since a phone never shows the title.
                <>
                  <time dateTime={job.next_run} title={formatDateTime(job.next_run)}>
                    {timeUntil(job.next_run)}
                  </time>
                  <AtClock iso={job.next_run} words={timeUntil(job.next_run)} />
                </>
              ) : job.paused ? (
                vi.jobPaused
              ) : (
                vi.jobDisabled
              )}
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
            <JobLastRun job={job} onOpenRun={openRun} />
            {open === job.id && (
              <JobRunHistory
                jobId={job.id}
                agentName={agentName(job.agent_id)}
                onOpenConversation={onOpenConversation}
                onOpenRun={openRun}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** When a schedule runs, in words, with the cron or interval it was written as beside it
 *  for whoever wants to check the reading; a shape with no words shows only once. */
function JobTiming({ job }: { job: JobInfo }) {
  const written = job.cron ?? job.every ?? "";
  const words = scheduleText(job.cron, job.every);
  return (
    <div className="job-meta muted">
      {words !== written && <span className="job-when">{words}</span>} <code>{written}</code> ·{" "}
      {JOB_KINDS[job.kind]}
    </div>
  );
}
