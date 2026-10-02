/**
 * A canvas version beside an earlier one, for the history view: every changed line, the three
 * unchanged lines on each side of a change, and a count in place of a longer unchanged run.
 *
 * Unlike `lineDiff` it keeps blank lines and spacing, because in a canvas they are the text: a
 * version that only re-indented a block has to show that it did.
 */

import { DIFF_CELLS, diffLines } from "./diff-lines";

export type CanvasDiffLine = { op: "same" | "add" | "remove"; text: string } | { op: "skip"; count: number };

/** Unchanged lines kept next to a change. */
const CONTEXT = 3;

/** The lines from `before` to `after`, or null when they are too large to compare under `cap`. */
export function canvasDiff(before: string, after: string, cap = DIFF_CELLS): CanvasDiffLine[] | null {
  const a = before.split("\n");
  const b = after.split("\n");
  const hunks = diffLines(a, b, cap);
  if (hunks === null) return null;
  const out: CanvasDiffLine[] = [];
  if (hunks.length === 0) return out;
  let at = 0;
  for (const [index, hunk] of hunks.entries()) {
    pushSame(out, a.slice(at, hunk.a), index === 0 ? 0 : CONTEXT, CONTEXT);
    for (let k = hunk.a; k < hunk.aEnd; k++) out.push({ op: "remove", text: a[k] });
    for (let k = hunk.b; k < hunk.bEnd; k++) out.push({ op: "add", text: b[k] });
    at = hunk.aEnd;
  }
  pushSame(out, a.slice(at), CONTEXT, 0);
  return out;
}

/** An unchanged run: `head` lines from its start, `tail` from its end, and a count between. */
function pushSame(out: CanvasDiffLine[], run: readonly string[], head: number, tail: number) {
  if (run.length <= head + tail) {
    for (const text of run) out.push({ op: "same", text });
    return;
  }
  for (let k = 0; k < head; k++) out.push({ op: "same", text: run[k] });
  out.push({ op: "skip", count: run.length - head - tail });
  for (let k = run.length - tail; k < run.length; k++) out.push({ op: "same", text: run[k] });
}
