/**
 * Where two texts differ, line by line: the core of merging a canvas and of showing its history.
 *
 * `lineDiff` serves memory review and drops blank lines and trailing spaces. A canvas keeps every
 * line, the final newline included, because a merge that ignored them would write them away. The
 * common head and tail are cut before the quadratic table, so two edits far apart in a long
 * document cost only the lines between them, and the table has a cap: a middle too large to
 * compare gives null, which callers treat as "cannot tell", never as "nothing changed".
 */

/** Lines `a..aEnd` of the first text became lines `b..bEnd` of the second, counted from each start. */
export type Hunk = { a: number; aEnd: number; b: number; bEnd: number };

/** The most table cells one comparison may fill: the line counts of the two middles multiplied. */
export const DIFF_CELLS = 4_000_000;

/**
 * The changes from `a` to `b` in reading order, any two separated by at least one common line, or
 * null when the middles left after cutting the common head and tail would fill more than `cap`
 * cells. A common run never exceeds the shorter middle, which a cap under 2^32 keeps below 65,536
 * lines, so the table holds 16-bit counts.
 */
export function diffLines(a: readonly string[], b: readonly string[], cap = DIFF_CELLS): Hunk[] | null {
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--;
    endB--;
  }
  const n = endA - start;
  const m = endB - start;
  if (n === 0 && m === 0) return [];
  if (n === 0 || m === 0) return [{ a: start, aEnd: endA, b: start, bEnd: endB }];
  if (n * m > cap) return null;
  // run[i * width + j] is the longest common run of the middles from a[start + i] and b[start + j],
  // filled from the end so the walk below can go forwards.
  const width = m + 1;
  const run = new Uint16Array((n + 1) * width);
  for (let i = n - 1; i >= 0; i--) {
    const line = a[start + i];
    for (let j = m - 1; j >= 0; j--) {
      const at = i * width + j;
      run[at] = line === b[start + j] ? run[at + width + 1] + 1 : Math.max(run[at + width], run[at + 1]);
    }
  }
  const hunks: Hunk[] = [];
  let open: Hunk | null = null;
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[start + i] === b[start + j]) {
      open = null;
      i++;
      j++;
      continue;
    }
    if (open === null) {
      open = { a: start + i, aEnd: start + i, b: start + j, bEnd: start + j };
      hunks.push(open);
    }
    if (j < m && (i === n || run[i * width + j + 1] >= run[(i + 1) * width + j])) {
      j++;
      open.bEnd++;
    } else {
      i++;
      open.aEnd++;
    }
  }
  return hunks;
}
