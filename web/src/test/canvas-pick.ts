import { act, fireEvent } from "@testing-library/react";

/**
 * Selecting text in a canvas, as a person's drag would leave it: for a canvas that is being read,
 * the text nodes and ranges of the page itself, with nothing of the app in between; for one that is
 * being edited, the selection of its text field.
 */

/** The first text node under `root` holding `needle`, and where the needle lies in it. */
export function find(root: Node, needle: string) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const at = (node as Text).data.indexOf(needle);
    if (at >= 0) return { node: node as Text, from: at, to: at + needle.length };
  }
  throw new Error(`no text holds ${needle}`);
}

/** Makes the page's selection run from `start` to `end`, and returns it. */
export function select(start: [Node, number], end: [Node, number]): Selection {
  const range = document.createRange();
  range.setStart(...start);
  range.setEnd(...end);
  const selection = document.getSelection() as Selection;
  selection.removeAllRanges();
  selection.addRange(range);
  return selection;
}

/** From the first character of `from` to the last of `to`. */
export function between(root: Node, from: string, to: string): Selection {
  const a = find(root, from);
  const b = find(root, to);
  return select([a.node, a.from], [b.node, b.to]);
}

/** Lets the page say its selection changed, as a browser does after each drag and key. */
export function announceSelection(): void {
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

/** The person selects `needle` within `root` and the page says so. */
export function pick(root: Node, needle: string): void {
  const { node, from, to } = find(root, needle);
  select([node, from], [node, to]);
  announceSelection();
}

/** The person selects `needle` in the text field of an editor, which tells the page as a key would. */
export function pickIn(field: HTMLTextAreaElement, needle: string): void {
  const at = field.value.indexOf(needle);
  if (at < 0) throw new Error(`the field does not hold ${needle}`);
  field.setSelectionRange(at, at + needle.length);
  fireEvent.select(field);
}
