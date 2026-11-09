import { useLayoutEffect, type RefObject } from "react";

/** The box grows with what is typed up to this many pixels, then scrolls. */
const MAX_HEIGHT = 240;

/**
 * One line when empty, as tall as the message while it is written: a fixed two-row box
 * either wastes a line on every short message or hides the start of a long one. Empty, the
 * box keeps its one row: measuring then would size it to the placeholder, which wraps on a
 * phone and would leave a second, blank line once a short name replaces it.
 */
export function useAutosize(box: RefObject<HTMLTextAreaElement | null>, text: string) {
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "";
    if (text) el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [box, text]);
}
