import type { RunInfo } from "../api/types";

/** A failure listed once for every run of the same job that ended the same way. */
export interface Repeated {
  run: RunInfo;
  /** The other runs folded into it; empty for a row of its own. */
  earlier: RunInfo[];
}

/**
 * A nightly job that keeps failing listed one row a night: three identical "gặp lỗi" rows
 * with the same clock and the same cut-off text, read as one fault told three times. Its
 * failures fold into the newest one, which says how many there were. Only a scheduled job's
 * runs fold: two conversations that failed are two different things to read, and a request
 * that waits on a decision is never folded, since each is settled on its own.
 */
export function foldRepeats(runs: RunInfo[]): Repeated[] {
  const rows: Repeated[] = [];
  const byJob = new Map<string, Repeated>();
  for (const run of runs) {
    const key = run.status !== "awaiting_approval" && run.source.startsWith("job:") ? `${run.source}#${run.status}` : null;
    const row = key === null ? undefined : byJob.get(key);
    if (row === undefined) {
      const own: Repeated = { run, earlier: [] };
      rows.push(own);
      if (key !== null) byJob.set(key, own);
    } else if (run.started_at > row.run.started_at) {
      row.earlier.unshift(row.run);
      row.run = run;
    } else {
      row.earlier.push(run);
    }
  }
  return rows;
}
