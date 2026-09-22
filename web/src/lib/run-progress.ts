// Turns a run's raw step list into what the timeline should actually show.
//
// The API reports each step as it was recorded, which is not the same as what
// is true now. A tool step keeps `ok: null` for as long as it was running when
// the row was written — including when the run has since died, been halted, or
// finished without ever closing that step. Rendering `ok: null` as "running"
// spins a spinner forever on work that stopped minutes ago.
//
// So the presented state of a step is its own state *intersected with* the
// state of the run that owns it.
import type { RunInfo, RunStatus, RunStep } from "../api/types";

/** What a step looks like now, as opposed to when it was written. */
export type StepState = "running" | "done" | "failed" | "stalled";

/** A run status that means nothing more will happen in this run. */
export function isSettled(status: RunStatus): boolean {
  return status === "done" || status === "halted" || status === "error";
}

/**
 * The state to paint for one step.
 *
 * A tool step that never closed is only "running" while its run still is.
 * Once the run settles, an unclosed step becomes "stalled" — it did not
 * succeed and it did not report a failure, and saying so is more honest than
 * picking one of the two.
 */
export function stepState(step: RunStep, runStatus: RunStatus): StepState {
  if (step.kind === "fallback") return "failed";
  if (step.kind === "model") return "done";
  if (step.ok === null) return isSettled(runStatus) ? "stalled" : "running";
  return step.ok ? "done" : "failed";
}

/** Steps whose state is still open, newest last. */
export function runningSteps(run: RunInfo): RunStep[] {
  return run.steps.filter((step) => stepState(step, run.status) === "running");
}

/**
 * The step to name when something asks "what is it doing right now".
 *
 * The newest running step wins: a model step that spawned three tool calls is
 * less interesting than the tool call currently blocking the turn.
 */
export function activeStep(run: RunInfo): RunStep | null {
  const open = runningSteps(run);
  return open.length > 0 ? open[open.length - 1] : null;
}

/** Progress as finished-of-total, for a compact "3/7" counter. */
export interface StepProgress {
  done: number;
  total: number;
}

export function stepProgress(run: RunInfo): StepProgress {
  const total = run.steps.length;
  const done = run.steps.filter((step) => stepState(step, run.status) !== "running").length;
  return { done, total };
}

/**
 * How long the run has been going, in ms.
 *
 * Uses `finished_at` once it exists so a settled run shows a fixed duration
 * rather than a number that keeps climbing. `now` is injected so the caller
 * can drive the ticking, and so tests are not at the mercy of the clock.
 */
export function runElapsedMs(run: RunInfo, now: number): number {
  const started = Date.parse(run.started_at);
  if (Number.isNaN(started)) return 0;
  const end = run.finished_at === null ? now : Date.parse(run.finished_at);
  if (Number.isNaN(end)) return 0;
  return Math.max(0, end - started);
}

/** A tool step's own duration, falling back to nothing when it never closed. */
export function stepDurationMs(step: RunStep): number | null {
  return step.duration_ms;
}

/**
 * The sum of everything the run actually spent time in, for the proportion
 * bar. Steps without a recorded duration contribute nothing rather than being
 * guessed at — a bar that invents widths is worse than a shorter bar.
 */
export function measuredDurationMs(run: RunInfo): number {
  return run.steps.reduce((total, step) => total + (step.duration_ms ?? 0), 0);
}
