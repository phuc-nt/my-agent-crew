import type { RunInfo } from "../api/types";

/** The source a scheduled job's run carries, followed by the job's id (`JOB_SOURCE`). */
const JOB_SOURCE = "job:";

/**
 * The reply a check job gives when all is well. The server does not deliver it
 * (`nothing_to_report`), and the inbox does not list it either: a row saying "OK" every
 * morning teaches the eye to skip the one that says something.
 */
const NOTHING_TO_REPORT = "OK";

function saysNothing(summary: string): boolean {
  return summary.trim().replace(/[.!]+$/, "").trim().toUpperCase() === NOTHING_TO_REPORT;
}

const finishedAt = (run: RunInfo) => Date.parse(run.finished_at ?? run.started_at);

/**
 * What the jobs reported: each finished job run that has something to say, the latest
 * first. A job that failed or halted is not here — it waits on the person with the rest of
 * what went wrong, above this list.
 */
export function jobResults(runs: RunInfo[]): RunInfo[] {
  return runs
    .filter((r) => r.source.startsWith(JOB_SOURCE) && r.status === "done" && r.summary && !saysNothing(r.summary))
    .sort((a, b) => finishedAt(b) - finishedAt(a));
}

/** The results that finished after the inbox was last read here; all of them when it never was. */
export function unreadResults(results: RunInfo[], readAt: string | null): RunInfo[] {
  if (readAt === null) return results;
  const read = Date.parse(readAt);
  return results.filter((r) => finishedAt(r) > read);
}

/** Two lists of runs as one, by id: the later list's copy of a run is the newer one. */
export function mergeRuns(older: RunInfo[], newer: RunInfo[]): RunInfo[] {
  const byId = new Map(older.map((r) => [r.id, r]));
  for (const run of newer) byId.set(run.id, run);
  return [...byId.values()];
}
