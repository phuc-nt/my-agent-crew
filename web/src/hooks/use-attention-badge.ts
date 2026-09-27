import { useEffect, useSyncExternalStore } from "react";
import type { RunInfo } from "../api/types";
import { seenKey, seenRuns, subscribeSeen } from "../lib/seen-runs";

const COUNT_PREFIX = /^\(\d+\) /;

/** The installed app's icon badge, where the browser has one. Chromium and Safari refuse
 *  it for reasons of their own (no permission, not installed); the title still counts. */
function setAppBadge(count: number) {
  const nav = navigator as Navigator & {
    setAppBadge?: (contents?: number) => Promise<void>;
    clearAppBadge?: () => Promise<void>;
  };
  try {
    const done = count > 0 ? nav.setAppBadge?.(count) : nav.clearAppBadge?.();
    done?.catch(() => undefined);
  } catch {
    // Thrown synchronously by some builds instead of rejecting; nothing to recover.
  }
}

/**
 * The runs still asking for the person, and the count of those waiting on a decision
 * carried outside the page: in the tab title and on the installed app's icon.
 *
 * A failure the person marked as read stops asking; a request waiting on a decision
 * is settled instead, and can be marked read only once it turns out to be closed already.
 * Only waiting requests are counted outside, because they are the ones with a deadline —
 * a failure keeps until it is read.
 */
export function useAttention(runs: RunInfo[]): RunInfo[] {
  const seen = useSyncExternalStore(subscribeSeen, seenRuns);
  const asking = runs.filter((run) => !seen.includes(seenKey(run)));
  const waiting = asking.filter((run) => run.status === "awaiting_approval").length;

  useEffect(() => {
    const title = document.title.replace(COUNT_PREFIX, "");
    document.title = waiting > 0 ? `(${waiting}) ${title}` : title;
    setAppBadge(waiting);
  }, [waiting]);

  return asking;
}
