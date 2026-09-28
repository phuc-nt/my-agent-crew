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
