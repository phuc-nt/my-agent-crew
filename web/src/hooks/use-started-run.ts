import { useCallback, useEffect, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { isSettled } from "../lib/run-progress";

/** What a "start it now" endpoint answers with: whose run, and under which source. */
export interface RunStart {
  agent_id: string;
  run_source: string;
}

interface Tracking {
  agentId: string;
  source: string;
  /** Run ids that existed before the start, so an older run of the same kind is not it. */
  before: ReadonlySet<string>;
}

export interface StartedRun {
  /** Waiting on a run this screen started; true from the start until that run settles. */
  tracking: boolean;
  /** The agent it was started for, so a screen showing another agent can stay quiet. */
  agentId: string | null;
  /** The run once the activity stream has shown it, null before that. */
  run: RunInfo | null;
  /** Calls the start endpoint and tracks the run it launches; rethrows its failure. */
  start: (call: () => Promise<RunStart>) => Promise<void>;
}

/**
 * Follows one run that a button on this screen started, until it settles.
 *
 * The start endpoints answer 202 before the run exists, with no run id, only the agent
 * and the source it will run under. So the run is recognised as the first one with that
 * agent and source that was not already on the list when the button was pressed. The
 * list is snapshotted before the request goes out: the run can reach the activity stream
 * before the 202 reaches the page, and a snapshot taken after would count it as old.
 */
export function useStartedRun(runs: RunInfo[], onSettled: (run: RunInfo) => void): StartedRun {
  const [tracking, setTracking] = useState<Tracking | null>(null);
  // The settle callback reloads whatever the screen shows; holding it in a ref keeps a
  // new closure on every render from re-firing the effect below.
  const settled = useRef(onSettled);
  useEffect(() => {
    settled.current = onSettled;
  }, [onSettled]);

  const run = tracking
    ? (runs.find(
        (r) => r.agent_id === tracking.agentId && r.source === tracking.source && !tracking.before.has(r.id),
      ) ?? null)
    : null;

  useEffect(() => {
    if (!run || !isSettled(run.status)) return;
    setTracking(null);
    settled.current(run);
  }, [run]);

  const start = useCallback(
    async (call: () => Promise<RunStart>) => {
      const before = new Set(runs.map((r) => r.id));
      const started = await call();
      setTracking({ agentId: started.agent_id, source: started.run_source, before });
    },
    [runs],
  );

  return { tracking: tracking !== null, agentId: tracking?.agentId ?? null, run, start };
}
