/**
 * Three-way merge of a canvas: the person's text and the server's, from the version both started at.
 *
 * Changes that do not touch merge; anything else is a conflict for the person to settle, because
 * a wrong merge is worse than none. Two changes touch when their line ranges in the starting
 * version overlap or meet, so two insertions at the same place, or an edit and an insertion right
 * after it, conflict: nothing tells which should come first. A side whose changes are too large
 * to compare is a conflict too.
 */

import { DIFF_CELLS, type Hunk, diffLines } from "./diff-lines";
import { type LineEdit, applyEdits } from "./line-edits";

export type Merge = { ok: true; text: string; edits: LineEdit[] } | { ok: false };

type Side = "mine" | "theirs";

/**
 * `mine` and `theirs` merged from `base`. `edits` are the server's changes in the line numbers of
 * `mine`, for keeping the person's caret on the characters it was on.
 */
export function merge3(base: string, mine: string, theirs: string, cap = DIFF_CELLS): Merge {
  const baseLines = base.split("\n");
  const mineLines = mine.split("\n");
  const theirLines = theirs.split("\n");
  const ours = diffLines(baseLines, mineLines, cap);
  const their = diffLines(baseLines, theirLines, cap);
  if (ours === null || their === null) return { ok: false };
  const hunks: (Hunk & { side: Side })[] = [
    ...ours.map((hunk) => ({ ...hunk, side: "mine" as const })),
    ...their.map((hunk) => ({ ...hunk, side: "theirs" as const })),
  ].sort((x, y) => x.a - y.a);
  const edits: LineEdit[] = [];
  // How many lines each side has gained over the base before the group being looked at.
  const shift = { mine: 0, theirs: 0 };
  let next = 0;
  while (next < hunks.length) {
    // A group is every hunk whose base range meets another in it; sorted by start, a hunk joins
    // when it starts no later than the furthest end so far.
    const group = [hunks[next++]];
    let end = group[0].aEnd;
    while (next < hunks.length && hunks[next].a <= end) {
      end = Math.max(end, hunks[next].aEnd);
      group.push(hunks[next++]);
    }
    const start = group[0].a;
    const grow = { mine: 0, theirs: 0 };
    for (const hunk of group) grow[hunk.side] += hunk.bEnd - hunk.b - (hunk.aEnd - hunk.a);
    const mineStart = start + shift.mine;
    const theirRegion = theirLines.slice(start + shift.theirs, end + shift.theirs + grow.theirs);
    const sides = new Set(group.map((hunk) => hunk.side));
    if (!sides.has("mine")) {
      edits.push({ start: mineStart, end: mineStart + (end - start), lines: theirRegion });
    } else if (sides.has("theirs")) {
      const mineRegion = mineLines.slice(mineStart, end + shift.mine + grow.mine);
      if (!sameLines(mineRegion, theirRegion)) return { ok: false };
    }
    shift.mine += grow.mine;
    shift.theirs += grow.theirs;
  }
  return { ok: true, text: applyEdits(mineLines, edits).join("\n"), edits };
}

function sameLines(x: readonly string[], y: readonly string[]): boolean {
  return x.length === y.length && x.every((line, k) => line === y[k]);
}
