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
 *
 * A run the server said it ended on this tab's Stop is not asked about. The server answers
 * the Stop at once, and the turn is there to join a while longer — it has a script to kill,
 * a call to close — so asking then would put a turn on its way out back on screen as going.
 */
export function useTurnWatch(
  conversationId: string | null,
  thread: ThreadController,
  activity: ActivityController,
  externalRun: RunInfo | null,
): void {
  // The run the server had nothing to read of when last asked.
  const nothing = useRef<string | null>(null);
  const { watch, stops } = thread;
  const stopsSeen = useRef(stops);
  const busy = thread.state.busy;
  const { synced } = activity;
  const run = externalRun?.id ?? null;

  useEffect(() => {
    nothing.current = null;
  }, [conversationId, synced]);

  // Declared before the effect that asks, so the run this Stop ended is put aside first.
  useEffect(() => {
    if (stopsSeen.current === stops) return;
    stopsSeen.current = stops;
    nothing.current = run;
  }, [stops, run]);

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
