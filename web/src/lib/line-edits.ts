/**
 * Line edits that turn one text into another, and where a cursor lands once they are applied.
 *
 * A merge or a reload replaces some lines of what the person is looking at. The caret and the
 * selection should stay on the characters they were on, which a raw offset would not: one line
 * added above pushes everything down. Edits use the line numbers of the text they apply to.
 */

import type { Hunk } from "./diff-lines";

/** Lines `start..end` are replaced by `lines`; `start === end` inserts before line `start`. */
export type LineEdit = { start: number; end: number; lines: string[] };

/** The edits that turn the first text of `hunks` into `theirs`, given as lines. */
export function editsFromHunks(hunks: readonly Hunk[], theirs: readonly string[]): LineEdit[] {
  return hunks.map((hunk) => ({ start: hunk.a, end: hunk.aEnd, lines: theirs.slice(hunk.b, hunk.bEnd) }));
}

/** `lines` with `edits` applied; the edits are in order and do not overlap. */
export function applyEdits(lines: readonly string[], edits: readonly LineEdit[]): string[] {
  // Pushed one by one: a spread of a few hundred thousand lines would overflow the call stack.
  const out: string[] = [];
  let at = 0;
  for (const edit of edits) {
    while (at < edit.start) out.push(lines[at++]);
    for (const line of edit.lines) out.push(line);
    at = edit.end;
  }
  while (at < lines.length) out.push(lines[at++]);
  return out;
}

/**
 * Where offset `offset` of `before` lands in `after`, the text `edits` make of it. A position
 * outside every edit keeps its line and column; one inside a removal moves to where the removed
 * lines were, one inside a replacement to the end of what replaced it. Without edits (the texts
 * were too large to compare) the offset is only kept inside `after`.
 */
export function mapOffset(
  before: string,
  after: string,
  edits: readonly LineEdit[] | null,
  offset: number,
): number {
  if (edits === null) return Math.min(offset, after.length);
  const lines = before.split("\n");
  let line = 0;
  let column = Math.min(offset, before.length);
  while (line < lines.length - 1 && column > lines[line].length) {
    column -= lines[line].length + 1;
    line++;
  }
  let shift = 0;
  for (const edit of edits) {
    if (edit.start > line) break;
    if (edit.end <= line) {
      shift += edit.lines.length - (edit.end - edit.start);
      continue;
    }
    if (edit.lines.length === 0) return offsetOf(after, edit.start + shift, 0);
    const last = edit.lines.length - 1;
    return offsetOf(after, edit.start + shift + last, edit.lines[last].length);
  }
  return offsetOf(after, line + shift, column);
}

/** The offset of `column` on line `line` of `text`, kept inside that line and the text. */
function offsetOf(text: string, line: number, column: number): number {
  let at = 0;
  for (let k = 0; k < line; k++) {
    const next = text.indexOf("\n", at);
    if (next === -1) return text.length;
    at = next + 1;
  }
  const end = text.indexOf("\n", at);
  return Math.min(at + column, end === -1 ? text.length : end);
}
