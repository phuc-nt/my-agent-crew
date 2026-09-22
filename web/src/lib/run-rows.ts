// Turns a run's steps into the rows a timeline draws.
//
// Two things happen here that a plain `steps.map()` cannot do.
//
// First, repeats collapse. An agent that retries a search six times writes six
// identical steps; drawn one per row they bury the one step that matters. A run
// of adjacent identical rows becomes a single row carrying `repeat`.
//
// Second, every row arrives already knowing its state, its kind and its label,
// so a component only has to decide how to paint it — and so a compact
// placement and the full timeline cannot disagree about what is happening.
import { stepState, type StepState } from "./run-progress";
import type { RunInfo, RunStep } from "../api/types";

/** The visual family of a row, which decides its colour and glyph. */
export type RowKind = "model" | "tool" | "delegate" | "fallback";

export interface RunRow {
  /** Stable within one run: the index of the first step this row covers. */
  key: number;
  kind: RowKind;
  state: StepState;
  /** The short name shown on the row — a tool name, a model name. */
  label: string;
  /** How many identical steps this row stands for. 1 means no collapsing. */
  repeat: number;
  /** Summed over every step the row covers, so a collapsed row still totals. */
  durationMs: number | null;
  step: RunStep;
}

/**
 * Delegation arrives as a tool call, but handing work to another agent reads as
 * a different kind of event than reading a file. Must match the tool name the
 * backend registers (`DELEGATE_TOOL_NAME` in the agent roster).
 */
const DELEGATE_TOOL = "delegate";

function rowKind(step: RunStep): RowKind {
  if (step.kind === "model") return "model";
  if (step.kind === "fallback") return "fallback";
  return step.name === DELEGATE_TOOL ? "delegate" : "tool";
}

function rowLabel(step: RunStep): string {
  if (step.kind === "model") return step.model ?? "?";
  if (step.kind === "fallback") return `${step.provider}:${step.model}`;
  return step.name;
}

/**
 * Whether two adjacent rows may merge.
 *
 * Deliberately strict. A running row never merges — it is the row someone is
 * watching, and folding it into a count would hide the only live thing on
 * screen. A row with output never merges either: the output is what
 * distinguishes it, so collapsing would lose information rather than
 * duplication.
 */
function mergeable(prev: RunRow, next: RunRow): boolean {
  if (prev.kind !== next.kind || prev.label !== next.label) return false;
  if (prev.state !== next.state) return false;
  if (prev.state === "running" || next.state === "running") return false;
  if (hasBody(prev.step) || hasBody(next.step)) return false;
  return true;
}

function hasBody(step: RunStep): boolean {
  if (step.kind === "tool") return step.output !== null && step.output !== "";
  if (step.kind === "model") return step.preview !== "";
  return true; // A fallback carries its error text, which is always worth its own row.
}

export function runRows(run: RunInfo): RunRow[] {
  const rows: RunRow[] = [];
  run.steps.forEach((step, index) => {
    const row: RunRow = {
      key: index,
      kind: rowKind(step),
      state: stepState(step, run.status),
      label: rowLabel(step),
      repeat: 1,
      durationMs: step.duration_ms,
      step,
    };
    const prev = rows[rows.length - 1];
    if (prev !== undefined && mergeable(prev, row)) {
      prev.repeat += 1;
      prev.durationMs = sumDurations(prev.durationMs, row.durationMs);
      return;
    }
    rows.push(row);
  });
  return rows;
}

/** Null means "not measured"; two unmeasured steps still total to unmeasured. */
function sumDurations(a: number | null, b: number | null): number | null {
  if (a === null) return b;
  if (b === null) return a;
  return a + b;
}
