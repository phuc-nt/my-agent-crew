import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";

/**
 * A run this screen started, shown beside the button that started it until it settles.
 *
 * The label stays the "where to watch it" sentence the button always answered with; the
 * badge adds the live status once the activity stream has the run, so the person can see
 * it is still going without leaving for the Activity tab.
 */
export function RunChip({ label, run }: { label: string; run: RunInfo | null }) {
  return (
    <p className="run-chip">
      <span className="run-chip-dot" aria-hidden="true" />
      <span>{label}</span>
      {run && <span className="badge">{vi.runStatus[run.status] ?? run.status}</span>}
    </p>
  );
}

interface RunStatusProps {
  label: string;
  run: RunInfo | null;
  tracking: boolean;
  /** How the run ended, or why it never started; empty when there is nothing to say. */
  message: string;
}

/**
 * The one live region for a run started here: the chip while it runs, then how it went.
 *
 * It stays mounted across that swap because a screen reader announces changes inside a
 * live region it already knows, and often misses a region that appears with its text.
 */
export function RunStatus({ label, run, tracking, message }: RunStatusProps) {
  return (
    <div role="status">
      {tracking ? <RunChip label={label} run={run} /> : message && <p className="muted">{message}</p>}
    </div>
  );
}

/** What to say once the run is over: how it ended, and its own summary when it left one. */
export function runOutcome(run: RunInfo): string {
  const status = vi.runStatus[run.status] ?? run.status;
  return run.summary ? `${vi.memory.runFinished(status)} ${run.summary}` : vi.memory.runFinished(status);
}
