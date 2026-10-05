import { useEffect, useRef } from "react";
import type { RunInfo } from "../api/types";
import type { ActivityController } from "./use-activity";
import type { ThreadController } from "./use-thread";

/**
 * Has the open thread read along with a turn this tab did not start: one going when the
 * conversation was opened, one a bot or a job or a waiting message began, or this tab's own
 * after it lost its stream. The server keeps every turn to its end whoever reads it, so the
 * thread joins it where it stands and follows it from there.
 *
 * `externalRun` is the run found going here that this tab does not read. The server is
 * asked about a run once: it may have ended a moment before the activity stream said so,
 * and then there is nothing to read. It is asked again when the run is seen going after it
 * was not — a pause someone answered — when a watch that did join has ended with the run
 * still going, and when the activity stream comes back, which a restarted server brings.
 */
export function useTurnWatch(
  conversationId: string | null,
  thread: ThreadController,
  activity: ActivityController,
  externalRun: RunInfo | null,
): void {
  // The run the server had nothing to read of when last asked.
  const nothing = useRef<string | null>(null);
  const { watch } = thread;
  const busy = thread.state.busy;
  const { synced } = activity;
  const run = externalRun?.id ?? null;

  useEffect(() => {
    nothing.current = null;
  }, [conversationId, synced]);

  useEffect(() => {
    if (run === null) {
      nothing.current = null;
      return;
    }
    if (busy || nothing.current === run) return;
    let current = true;
    void watch().then((found) => {
      if (!found && current) nothing.current = run;
    });
    return () => {
      current = false;
    };
  }, [conversationId, run, busy, synced, watch]);
}
