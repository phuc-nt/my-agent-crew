/**
 * What a proposed memory write would change, line by line and in order.
 *
 * A rewrite can drop lines as well as add them, and a reviewer has to see both: a
 * consolidation that quietly loses "Sếp dị ứng tôm" looks harmless in a view that only
 * shows what is new. A longest-common-subsequence walk gives the classic two-sided diff
 * without a library, and memory files are small enough that the quadratic table is
 * nothing.
 */

export type DiffOp = "same" | "add" | "remove";
export type DiffLine = { text: string; op: DiffOp };

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = splitLines(before);
  const b = splitLines(after);
  // lcs[i][j] is the longest common run of a[i..] and b[j..]; filled from the end so the
  // walk below can go forwards and emit lines in reading order.
  const lcs = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ text: a[i], op: "same" });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      // Removals before additions, so a changed line reads as "was, then is".
      out.push({ text: a[i++], op: "remove" });
    } else {
      out.push({ text: b[j++], op: "add" });
    }
  }
  while (i < a.length) out.push({ text: a[i++], op: "remove" });
  while (j < b.length) out.push({ text: b[j++], op: "add" });
  return out;
}

/**
 * Blank lines are dropped: they carry nothing to review, and matching them would stitch
 * unrelated hunks together around an empty line both sides happen to share. Trailing
 * spaces are trimmed for the same reason; leading ones are kept because they are nesting.
 */
function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim() !== "");
}
