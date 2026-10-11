// What a job's row says of its schedule: when it runs, what kind of job it is, and, for
// the kind that runs a script, the script.
import type { JobInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { scheduleText } from "../lib/cron-text";

const JOB_KINDS: Record<string, string> = {
  prompt: vi.jobKindPrompt,
  command: vi.jobKindCommand,
  script: vi.jobKindScript,
  consolidate: vi.jobKindConsolidate,
};

/** When a schedule runs, in words, with the cron or interval it was written as beside it
 *  for whoever wants to check the reading; a shape with no words shows only once. */
export function JobTiming({ job }: { job: JobInfo }) {
  const written = job.cron ?? job.every ?? "";
  const words = scheduleText(job.cron, job.every);
  return (
    <div className="job-meta muted">
      {words !== written && <span className="job-when">{words}</span>} <code>{written}</code> ·{" "}
      {JOB_KINDS[job.kind]}
    </div>
  );
}

/**
 * What a script job runs, and the prompt its output is handed on with.
 *
 * A prompt or a command is one line a person wrote in the form and can open there. A
 * script is code written in `agent.yaml` that runs with no model reading it, so the row
 * shows the start of it: enough to tell which script this is and whether it is the one
 * that was meant. The whole of it is in the editor, one tap away on Sửa lịch.
 *
 * A job that is no script, or comes from a server older than script jobs, has neither line.
 */
export function JobScript({ job }: { job: JobInfo }) {
  if (!job.script) return null;
  return (
    <>
      <div className="job-meta muted" data-testid="job-script">
        <pre className="job-script-source">
          <code>{job.script}</code>
        </pre>
      </div>
      {job.then_prompt && (
        <div className="job-meta muted job-then-prompt" data-testid="job-then-prompt">
          {vi.jobThenPrompt}: <span>{job.then_prompt}</span>
        </div>
      )}
    </>
  );
}
