import type { RunInfo } from "../api/types";

/**
 * Newest first, the order every list of runs is shown in.
 *
 * Start times are whole seconds, so runs can share one. Of those, one still going comes
 * first, then the one that ended later. Runs that tie on both keep the order they are given
 * in, which is the order they were heard of, newest first. A comparison that never calls two
 * runs equal orders them by however the sort happened to compare them, and two lists of the
 * same runs then disagree: the line naming the last run and the card under it among them.
 */
export function newestFirst(a: RunInfo, b: RunInfo): number {
  if (a.started_at !== b.started_at) return a.started_at < b.started_at ? 1 : -1;
  if (a.finished_at === b.finished_at) return 0;
  if (a.finished_at === null) return -1;
  if (b.finished_at === null) return 1;
  return a.finished_at < b.finished_at ? 1 : -1;
}

/** A run kept on a list it has left, with the ids of the runs listed after it then. */
export interface HeldRun {
  run: RunInfo;
  before: string[];
}

/** `run` held where `rows` list it. */
export function heldAt(rows: RunInfo[], run: RunInfo): HeldRun {
  const at = rows.findIndex((row) => row.id === run.id);
  return { run, before: at < 0 ? [] : rows.slice(at + 1).map((row) => row.id) };
}

/**
 * `runs` in `newestFirst` order with each held run back where it was listed: ahead of the
 * first run still there that was listed after it, or last. Runs handed out together start in
 * one second and tie, so a held run sorted in by its start alone would drop below all of them.
 */
export function withHeld(runs: RunInfo[], held: HeldRun[]): RunInfo[] {
  const rows = [...runs];
  for (const { run, before } of held) {
    const at = rows.findIndex((row) => before.includes(row.id));
    rows.splice(at < 0 ? rows.length : at, 0, run);
  }
  // A run of another second that came in meanwhile still goes where its start puts it.
  return rows.sort(newestFirst);
}
