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

/** What a step looks like now, as opposed to when it was written.
 *
 * "waiting" is its own state and not a kind of "running": nothing is being computed and
 * no time is being bought, the run is stopped until a person types. Painting it as
 * running would show effort where there is none, and as stalled would suggest a fault. */
export type StepState = "running" | "done" | "failed" | "stalled" | "waiting";

/**
 * The statuses that mean nothing more will happen in this run.
 *
 * Named as a type so anything that has to say something per settled status — how the
 * run ended, say — is checked against the whole set rather than falling back to one of
 * them for a status added later.
 */
export type SettledStatus = "done" | "halted" | "error";

const SETTLED: readonly RunStatus[] = ["done", "halted", "error"] satisfies SettledStatus[];

/** A run status that means nothing more will happen in this run. */
export function isSettled(status: RunStatus): status is SettledStatus {
  return SETTLED.includes(status);
}

type ModelStep = Extract<RunStep, { kind: "model" }>;

/** Whether a model call has its answer. The answer, its price and its tool calls land
 *  together, so a run read mid-call carries the step open with none of them. */
export function isAnswered(step: ModelStep): step is ModelStep & { tool_calls: string[] } {
  return step.tool_calls !== undefined;
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
  if (step.kind === "model" && isAnswered(step)) return "done";
  if (step.kind === "model") return isSettled(runStatus) ? "stalled" : "running";
  // A note is finished the instant it is written, and it can neither run nor fail.
  if (step.kind === "note") return "done";
  // A question never closes on this run: the answer resumes the turn as a new one. So it
  // is "waiting" whatever the run went on to do, rather than stalling once the run ends.
  if (step.kind === "question") return "waiting";
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

/**
 * The step the run is stopped on, waiting for a person.
 *
 * Kept apart from `activeStep` because the two answer different questions. A waiting
 * step is not work in progress, so counting it as active would put it in the running
 * total and show a spinner; leaving it out of both would let the header claim the agent
 * is thinking while it is in fact blocked on an unanswered question.
 */
export function waitingStep(run: RunInfo): RunStep | null {
  const waiting = run.steps.filter((step) => stepState(step, run.status) === "waiting");
  return waiting.length > 0 ? waiting[waiting.length - 1] : null;
}

/** Progress as finished-of-total, for a compact "3/7" counter. */
export interface StepProgress {
  done: number;
  total: number;
}

/** The states that mean the step is no longer waiting on anything. */
const OPEN_STATES: readonly StepState[] = ["running", "waiting"];

export function stepProgress(run: RunInfo): StepProgress {
  // A note is commentary on the work, not a piece of it. Counted, it would land on both
  // sides of the fraction and quietly deflate it: an agent that says what it is doing
  // before each of three tool calls would read "6/8" where a silent one reads "3/4",
  // making the more talkative agent look further behind for having explained itself.
  const counted = run.steps.filter((step) => step.kind !== "note");
  const total = counted.length;
  // A waiting step is not finished any more than a running one is. Counting it as done
  // would fill the bar on a run that is stopped, which is the one moment the bar is
  // being read to find out whether anything is still happening.
  const done = counted.filter((step) => !OPEN_STATES.includes(stepState(step, run.status))).length;
  return { done, total };
}

/**
 * How long the run has been going, in ms.
 *
 * Uses `finished_at` once it exists so a settled run shows a fixed duration
 * rather than a number that keeps climbing. `now` is injected so the caller
 * can drive the ticking, and so tests are not at the mercy of the clock.
 *
 * A settled run with no `finished_at` reports the time its steps took instead
 * of counting on to now. The two are stamped by different things — the status
 * by the run's own last event, `finished_at` by the hub that was watching — so
 * a run recorded outside the hub arrives settled with the timestamp missing,
 * and measuring that against the current clock turns an old run into hours.
 */
export function runElapsedMs(run: RunInfo, now: number): number {
  const started = Date.parse(run.started_at);
  if (Number.isNaN(started)) return 0;
  const end = run.finished_at === null ? now : Date.parse(run.finished_at);
  if (Number.isNaN(end)) return 0;
  if (run.finished_at === null && isSettled(run.status)) return measuredDurationMs(run);
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
