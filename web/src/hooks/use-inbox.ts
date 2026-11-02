import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { inboxReadAt, markInboxRead, subscribeInboxRead } from "../lib/inbox-read";
import { jobResults, mergeRuns, unreadResults } from "../state/inbox";

/** Enough runs to reach back past a few days of chat turns to the jobs among them. */
const INBOX_LIMIT = 200;
/** The reports read whole; an older result shows the start its run kept. */
const REPORT_LIMIT = 50;

/** When the inbox was last read on this device, kept current across tabs. */
export function useInboxReadAt(): string | null {
  return useSyncExternalStore(subscribeInboxRead, inboxReadAt);
}

/** How many job results came in since the inbox was last read, for the badge that opens it. */
export function useUnreadResults(runs: RunInfo[]): number {
  const readAt = useInboxReadAt();
  return unreadResults(jobResults(runs), readAt).length;
}

export interface Inbox {
  results: RunInfo[];
  /** What each result's run sent to the chat, whole, by run id; read after the list. */
  reports: Map<string, string>;
  /** The ids that were new when the inbox opened, or have come in since. */
  fresh: Set<string>;
  /** The older runs could not be read; the list holds what the activity stream had. */
  loadFailed: boolean;
}

/**
 * The open inbox's job results: the activity stream's runs, which stay current, over a
 * longer list read once as it opens — the stream holds the last fifty runs, and a busy
 * day of chat pushes the morning's report out of them.
 *
 * Opening the inbox reads it, and so does leaving it: what came in while it was open was
 * on screen. What was new at opening stays marked as such until the screen closes.
 */
export function useInbox(runs: RunInfo[]): Inbox {
  const [older, setOlder] = useState<RunInfo[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [openedAfter] = useState(inboxReadAt);

  useEffect(() => {
    let alive = true;
    api.listRuns({ limit: INBOX_LIMIT }).then(
      (list) => alive && setOlder(list),
      () => alive && setLoadFailed(true),
    );
    markInboxRead(new Date().toISOString());
    return () => {
      alive = false;
      markInboxRead(new Date().toISOString());
    };
  }, []);

  const results = jobResults(mergeRuns(older, runs));
  const fresh = new Set(unreadResults(results, openedAfter).map((r) => r.id));
  const reports = useReports(results);
  return { results, reports, fresh, loadFailed };
}

/**
 * The words of each result, read again whenever a result is listed that they lack: as the
 * inbox opens, when the longer list arrives, and when a job reports while it is open. A
 * result the server has no words for (older than its page) is asked about once, not on
 * every render.
 */
function useReports(results: RunInfo[]): Map<string, string> {
  const [reports, setReports] = useState<Map<string, string>>(() => new Map());
  const asked = useRef("");
  const missing = results
    .filter((r) => !reports.has(r.id))
    .map((r) => r.id)
    .join(",");

  useEffect(() => {
    if (!missing || asked.current === missing) return;
    // Asked once per set of missing ids, so the answer is kept even when the effect is run
    // again before it comes (as development mode does): nothing would ask a second time.
    asked.current = missing;
    api.listReports(REPORT_LIMIT).then(
      (list) => setReports(new Map(list.map((r) => [r.run_id, r.text]))),
      () => undefined,
    );
  }, [missing]);

  return reports;
}
