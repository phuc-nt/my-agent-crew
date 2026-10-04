/**
 * Keeps the keyboard with the person while a canvas page runs beside the app. A page in a frame may
 * focus itself whenever it likes, and no sandbox flag or policy a browser ships stops it: the keys
 * typed next would go to the page, which hears them, and not to the message being written.
 *
 * The page has the keyboard only while the person offers it: the last thing they did that the app
 * saw was to move, press or scroll the pointer over the frame's box, or to press Tab. A key pressed
 * in the app, a pointer anywhere else and focus arriving on one of the app's controls each take the
 * offer back. Without an offer the frame takes no pointer (its box lacks `data-offered`, and the
 * style sheet does the rest), so the next pointer event over it reaches the app: that is the only
 * way the app can see the person point at a page of another origin.
 *
 * The app learns that the frame has the focus from its own window's `blur`. With an offer standing
 * it leaves the focus there. Without one the page took it: it goes back to the element it was taken
 * from, or off the frame when nothing held it, and the fifth time on one frame the page is stopped.
 * A browser ignores a focus set while it is still telling of the `blur`, so the keyboard is given
 * back in the next task, and a key pressed in between goes to the page.
 *
 * The cost, which is accepted: a tap, or a click made without moving the pointer, that follows
 * something done in the app lands on the app and makes the offer, and only the next one reaches the
 * page. A finger does not move before it taps, so on a touch screen that is every first tap on the
 * page. And a page that focuses itself while the pointer is over it is taken at its word.
 */

import { type RefObject, useEffect, useRef } from "react";

/** How often one frame may take the keyboard unasked before its page is stopped. */
export const GRABS_MAX = 5;

/** On the frame's box while the person offers the page the keyboard. */
export const OFFERED = "data-offered";

const POINTER_EVENTS = ["pointermove", "pointerdown", "wheel"] as const;

/**
 * Guards the keyboard against the page in `frame`, and returns the ref of the box to put the frame
 * in. `onGrabbing` is called when the frame on show has taken the keyboard `GRABS_MAX` times, and
 * each time it does after that while it is left up; a frame that replaces it starts with no grab
 * against it.
 */
export function useFrameFocusGuard(
  frame: RefObject<HTMLIFrameElement | null>,
  onGrabbing: () => void,
): RefObject<HTMLDivElement | null> {
  const box = useRef<HTMLDivElement>(null);
  const stop = useRef(onGrabbing);
  stop.current = onGrabbing;

  useEffect(() => {
    const grabsOf = new WeakMap<HTMLIFrameElement, number>();
    let offered = false;
    // The element focus left in this very task: a frame that has the focus now took it from there.
    let left: HTMLElement | null = null;
    let forgetting: ReturnType<typeof setTimeout> | undefined;
    let returning: ReturnType<typeof setTimeout> | undefined;

    const offer = (next: boolean) => {
      offered = next;
      box.current?.toggleAttribute(OFFERED, next);
    };
    const pointed = (event: Event) => offer(box.current?.contains(event.target as Node) === true);
    const pressed = (event: KeyboardEvent) => offer(event.key === "Tab");
    const arrived = (event: FocusEvent) => {
      if (event.target !== frame.current) offer(false);
    };
    const leaving = (event: FocusEvent) => {
      if (event.target === frame.current) return;
      left = event.target as HTMLElement;
      clearTimeout(forgetting);
      forgetting = setTimeout(() => {
        left = null;
      }, 0);
    };
    const giveBack = (to: HTMLElement | null) => {
      returning = undefined;
      to?.focus({ preventScroll: true });
      // Nothing held the focus, or what held it cannot have it again: the app has the keyboard
      // anyway. A frame that no longer has the focus is not touched by this.
      frame.current?.blur();
    };
    const blurred = () => {
      const taker = frame.current;
      if (taker === null || document.activeElement !== taker || offered) return;
      // Told twice before the keyboard is back, the page still took it once.
      if (returning !== undefined) return;
      const from = left;
      returning = setTimeout(() => giveBack(from), 0);
      const grabs = (grabsOf.get(taker) ?? 0) + 1;
      grabsOf.set(taker, grabs);
      if (grabs >= GRABS_MAX) stop.current();
    };

    for (const type of POINTER_EVENTS) document.addEventListener(type, pointed, { capture: true, passive: true });
    document.addEventListener("keydown", pressed, true);
    document.addEventListener("focusin", arrived, true);
    document.addEventListener("focusout", leaving, true);
    window.addEventListener("blur", blurred);
    return () => {
      for (const type of POINTER_EVENTS) document.removeEventListener(type, pointed, true);
      document.removeEventListener("keydown", pressed, true);
      document.removeEventListener("focusin", arrived, true);
      document.removeEventListener("focusout", leaving, true);
      window.removeEventListener("blur", blurred);
      clearTimeout(forgetting);
      clearTimeout(returning);
    };
  }, [frame]);

  return box;
}
