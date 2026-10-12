import { type RefObject, useEffect, useState } from "react";

/**
 * Where the keyboard goes when the row it was on leaves a list of tick boxes.
 *
 * A row that only exists while it is ticked is gone the moment a person unticks it, and a
 * keyboard that was on its box is then on nothing: the next Tab starts from the top of the
 * page. Tell the function this returns where the row stood among the list's boxes, and once
 * the row is out of the page the keyboard is put on the box that took its place, else on
 * the last box, else on what `otherwise` finds: the list may be empty, switched off, or gone
 * from the page altogether.
 *
 * A person whose keyboard was not on the row keeps it where it is: a tap unticks without
 * taking the keyboard out of the field being typed in.
 */
export function useFocusAfterRowLeft(
  list: RefObject<HTMLElement | null>,
  otherwise: () => HTMLElement | null | undefined,
): (at: number) => void {
  const [left, setLeft] = useState<{ at: number } | null>(null);
  useEffect(() => {
    if (left === null || document.activeElement !== document.body) return;
    const boxes = list.current?.querySelectorAll<HTMLInputElement>("input") ?? [];
    const next = boxes[Math.min(left.at, boxes.length - 1)];
    (next && !next.disabled ? next : otherwise())?.focus();
    // Run for a row that left, once: a later render's `otherwise` is no reason to run again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left]);
  return (at) => setLeft({ at });
}
