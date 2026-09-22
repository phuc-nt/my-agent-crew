import { useEffect, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import type { SettledStatus } from "../lib/run-progress";
import { activeStep, isSettled, stepProgress, runElapsedMs, waitingStep } from "../lib/run-progress";
import { runRows } from "../lib/run-rows";

/**
 * One line answering "what is it doing right now", above the timeline.
 *
 * It is deliberately a sentence and a count rather than a percentage. Nothing
 * in the run data says how many steps are still to come, so a percentage would
 * be invented; `3/7 bước` is the honest version of the same reassurance.
 */
export function RunProgressHeader({ run }: { run: RunInfo }) {
  const live = !isSettled(run.status);
  const elapsed = useElapsed(run, live);
  const { done, total } = stepProgress(run);
  const active = activeStep(run);
  // A question outranks anything still open: it is the only thing that will move the run
  // on, and reporting a half-finished tool call instead would hide the ask.
  const waiting = waitingStep(run);

  // A settled run has no "right now" to report, so it says how it ended instead.
  // Saying "Đang suy nghĩ" on a run that finished minutes ago reads as a hang.
  const label = !isSettled(run.status)
    ? waiting !== null
      ? vi.runWaitingAnswer
      : active === null
        ? vi.runThinking
        : vi.runDoing(labelFor(run, active))
    : endedLabel(run.status);
  // The bar is a proportion of the steps that exist, not of a total it cannot
  // know, so a run that is still producing steps shows the bar creeping and
  // occasionally sliding back — which is the truth about the work.
  const filled = total === 0 ? 0 : Math.round((done / total) * 100);

  return (
    <div className="run-progress-wrap" data-testid="run-progress">
      {/* A waiting run is live but not moving. The shimmer means work is under way, so
          leaving it on would tell the person to sit and wait for the very thing that
          only starts once they answer. */}
      <div className={`run-progress${live && waiting === null ? " live" : ""}${waiting !== null ? " waiting" : ""}`}>
        <span className="run-progress-label">{label}</span>
        <span className="run-progress-count tabular">
          {vi.runStepCount(done, total)} · {vi.runElapsed(elapsed)}
        </span>
      </div>
      <div
        className="run-progress-bar"
        role="progressbar"
        aria-valuenow={filled}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={vi.runStepCount(done, total)}
      >
        <div className="run-progress-fill" style={{ width: `${filled}%` }} />
      </div>
    </div>
  );
}

/**
 * How a run that is over ended, for the line that would otherwise say what it is doing.
 *
 * Written as a mapping over every settled status rather than as a default, so a status
 * that becomes settled later has to be given its own wording here instead of quietly
 * arriving on screen as "Đã xong".
 */
const ENDED_LABELS: Record<SettledStatus, string> = {
  done: vi.runEndedDone,
  halted: vi.runEndedHalted,
  error: vi.runEndedError,
};

function endedLabel(status: SettledStatus): string {
  return ENDED_LABELS[status];
}

/** The name of the work in progress, as the timeline would have labelled it. */
function labelFor(run: RunInfo, step: ReturnType<typeof activeStep>): string {
  if (step === null) return vi.runThinking;
  const row = runRows(run).find((r) => r.step === step);
  return row?.label ?? vi.runThinking;
}

/**
 * The run's elapsed time, ticking once a second while it is live.
 *
 * The interval only exists for a running run, so a panel showing twenty
 * finished runs schedules nothing at all. A settled run keeps the last tick
 * rather than reading the clock again: a run that ended without ever writing
 * `finished_at` would otherwise keep counting up on every unrelated re-render.
 */
function useElapsed(run: RunInfo, live: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [live]);
  return runElapsedMs(run, now);
}
