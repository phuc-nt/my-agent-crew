/**
 * The passage of a canvas a person selected, as a message about it carries it: the text, the
 * lines it lies on, and how much the person had selected, which a passage cut to fit is shorter
 * than. The server places a passage by its lines only when those lines hold it, so the lines
 * count from the first line the passage has text on to the last, never a line end beyond it.
 */

/** As long as the longest message the chat takes, in characters as the server counts them:
 *  a pair of code units is one. */
export const SELECTION_MAX = 20000;

export type Passage = { text: string; line_start: number; line_end: number };
export type CanvasSelection = Passage & {
  /** Characters the person had selected. */
  shown: number;
};

/** Characters of `text` as the server counts them, a pair of code units being one. */
export const charCount = (text: string): number => Array.from(text).length;

/**
 * `text` as lines `lineStart` to `lineEnd`, kept whole when it fits a message. A longer passage
 * is cut at its last line end within the limit, and ends on the line before, so no line is
 * quoted in part; a first line that alone passes the limit is cut by characters, never between
 * the two units of one. Null for a passage that is only blank.
 */
export function clipSelection(text: string, lineStart: number, lineEnd: number): Passage | null {
  let kept = text;
  let end = lineEnd;
  const chars = text.length > SELECTION_MAX ? Array.from(text) : null;
  if (chars && chars.length > SELECTION_MAX) {
    const head = chars.slice(0, SELECTION_MAX);
    const lastBreak = head.lastIndexOf("\n");
    const atLineEnd = chars[SELECTION_MAX] === "\n";
    kept = (atLineEnd || lastBreak < 0 ? head : head.slice(0, lastBreak)).join("").replace(/\n+$/, "");
    end = lineStart + kept.split("\n").length - 1;
  }
  return kept.trim() === "" ? null : { text: kept, line_start: lineStart, line_end: end };
}

const breaks = (text: string, from: number, to: number): number => {
  let count = 0;
  for (let at = text.indexOf("\n", from); at !== -1 && at < to; at = text.indexOf("\n", at + 1)) count += 1;
  return count;
};

/**
 * What is selected in the editor, which holds `text`. Line ends at either end are left out, as
 * a line chosen by triple click brings its own, and the lines are those the rest lies on.
 */
export function fromTextarea(field: HTMLTextAreaElement, text: string): CanvasSelection | null {
  let start = field.selectionStart;
  let end = field.selectionEnd;
  while (start < end && text[start] === "\n") start += 1;
  while (end > start && text[end - 1] === "\n") end -= 1;
  const picked = text.slice(start, end);
  if (picked.trim() === "") return null;
  const lineStart = breaks(text, 0, start) + 1;
  const clipped = clipSelection(picked, lineStart, lineStart + breaks(text, start, end));
  return clipped && { ...clipped, shown: charCount(picked) };
}

/** What lies between the ends of `range` and the contents of `root`, on the side of each end
 *  that lies outside it. */
function outsideText(range: Range, root: Element): string {
  const inside = document.createRange();
  inside.selectNodeContents(root);
  let text = "";
  if (range.compareBoundaryPoints(Range.START_TO_START, inside) < 0) {
    const lead = range.cloneRange();
    lead.setEnd(inside.startContainer, inside.startOffset);
    text += lead.toString();
  }
  if (range.compareBoundaryPoints(Range.END_TO_END, inside) > 0) {
    const tail = range.cloneRange();
    tail.setStart(inside.endContainer, inside.endOffset);
    text += tail.toString();
  }
  return text;
}

const LINED = "[data-line-start][data-line-end]";

/**
 * The lines from the earliest to the latest that the blocks at the two ends of what `range` takes
 * of `root` name, judged by the text it takes: an end that stands at the very start of a block, as
 * a triple click leaves it at the start of the next one, takes nothing of that block. Text under no
 * block that names its lines, such as the label of a copy button, counts for nothing.
 */
function linesTaken(range: Range, root: Element): [number, number] | null {
  let first: Element | null = null;
  let last: Element | null = null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
    if (!range.intersectsNode(node)) continue;
    const from = node === range.startContainer ? range.startOffset : 0;
    const to = node === range.endContainer ? range.endOffset : node.data.length;
    if (node.data.slice(from, to).trim() === "") continue;
    const block = node.parentElement?.closest(LINED);
    if (!block || !root.contains(block)) continue;
    first ??= block;
    last = block;
  }
  if (!first || !last) return null;
  const named = (block: Element, name: string) => Number(block.getAttribute(name));
  const start = Math.min(named(first, "data-line-start"), named(last, "data-line-start"));
  const end = Math.max(named(first, "data-line-end"), named(last, "data-line-end"));
  return Number.isInteger(start) && Number.isInteger(end) && start >= 1 && end >= start ? [start, end] : null;
}

/**
 * What is selected in `root`, a canvas being read that `source` is drawn from: the whole lines
 * of `source` the selected text came from, since a rendered passage cannot be told from the
 * text that drew it any closer than the block it is in. Null for a selection that is not made
 * of text in `root` alone.
 */
export function fromRendered(selection: Selection, root: Element, source: string): CanvasSelection | null {
  if (selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (outsideText(range, root).trim() !== "") return null;
  const taken = linesTaken(range, root);
  const lines = source.split("\n");
  if (!taken || taken[1] > lines.length) return null;
  const [start, end] = taken;
  const clipped = clipSelection(lines.slice(start - 1, end).join("\n"), start, end);
  return clipped && { ...clipped, shown: charCount(selection.toString()) };
}
