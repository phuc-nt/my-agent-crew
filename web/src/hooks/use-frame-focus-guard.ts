/**
 * Keeps the keyboard with the person while a canvas page runs beside the app. A page in a frame may
 * focus itself whenever it likes, and no sandbox flag or policy a browser ships stops it: the keys
 * typed next would go to the page, which hears them, and not to the message being written.
 *
 * The page has the keyboard only while the person offers it. Two things make the offer. One is a
 * pointer pressed inside the page: the page's own reporter tells of it over a port the app was
 * handed before any of the page's code ran (`use-frame-messages.ts`), and a page cannot make that
 * press up. The other is Tab, while it is the last key pressed in the app. A key that is not Tab
 * pressed in the app, a pointer pressed in the app outside the frame's box, and the focus arriving
 * on one of the app's elements each take the offer back. Moving the pointer or scrolling says
 * nothing either way, over the page or off it: a page can make the browser do both.
 *
 * The app learns that the frame has the focus from its own window's `blur`. With an offer standing
 * it leaves the focus there. Without one it waits `ATTEST_GRACE_MS` for the press to be told: the
 * press and the blur come by different roads, and either may be first. Told in time, the offer
 * stands and nothing is held against the page. Otherwise the page took the keyboard: the frame has
 * one more grab against it, the fifth stops the page, and the keyboard goes back to the element it
 * was taken from, or off the frame when nothing held it. Keys pressed during the wait go to the
 * page. A wait that ends much later than it was due means the app was held up while the page had
 * the keyboard, and stops the page at once.
 *
 * A window that is not in front is told nothing when a page in it takes the focus. So the element
 * that had the keyboard when the window lost the focus to anything but the frame is remembered, and
 * the frame is looked at again when the person is back: a task after the window's `focus`, when the
 * tab is shown again, and at a pointer moved or pressed in the app before the window has said it is
 * in front. A frame that has the keyboard then with no offer is waited on like any other, and the
 * keyboard goes back to the remembered element.
 */

import { type RefObject, useCallback, useEffect, useRef } from "react";

/** How often one frame may take the keyboard unasked before its page is stopped. */
export const GRABS_MAX = 5;
/** How long a frame that has the focus with no offer is given for its page to tell of a press. */
export const ATTEST_GRACE_MS = 50;
/** How far past its time that wait may end before the page is stopped for it. */
export const LATE_MS = 100;

const POINTER_EVENTS = ["pointermove", "pointerdown"] as const;

type Timer = ReturnType<typeof setTimeout> | undefined;

export type FrameFocusGuard = {
  /** The box to put the frame in. */
  box: RefObject<HTMLDivElement | null>;
  /** The reporter of the page on show told of a pointer a person pressed inside it. */
  attest(): void;
};

/**
 * Guards the keyboard against the page in `frame`. `onGrabbing` is called when the frame on show
 * has taken the keyboard `GRABS_MAX` times or held the app up while it had it, and each time it
 * takes it after that while it is left up; a frame that replaces it starts with no grab against it.
 */
export function useFrameFocusGuard(frame: RefObject<HTMLIFrameElement | null>, onGrabbing: () => void): FrameFocusGuard {
  const box = useRef<HTMLDivElement>(null);
  const stop = useRef(onGrabbing);
  stop.current = onGrabbing;
  const told = useRef<() => void>(undefined);
  const attest = useCallback(() => told.current?.(), []);

  useEffect(() => {
    const grabsOf = new WeakMap<HTMLIFrameElement, number>();
    let offered = false;
    // The element focus left in this very task: a frame that has the focus now took it from there.
    let left: HTMLElement | null = null;
    let forgetting: Timer;
    // The window is not in front, and the element that had the keyboard when it stopped being.
    let away = false;
    let kept: HTMLElement | null = null;
    let returning: Timer;
    let waiting: Timer;

    const settle = (taker: HTMLIFrameElement, from: HTMLElement | null, since: number) => {
      waiting = undefined;
      // A frame replaced or stopped while its page was waited on has nothing left to answer for.
      if (frame.current !== taker) return;
      const grabs = (grabsOf.get(taker) ?? 0) + 1;
      grabsOf.set(taker, grabs);
      // Where the person moved the focus on during the wait, it stays where they put it.
      if (document.activeElement === taker) {
        from?.focus({ preventScroll: true });
        // Nothing held the focus, or what held it cannot have it again: off the frame, the app has
        // the keyboard anyway. A frame that no longer has the focus is not touched by this.
        taker.blur();
      }
      if (grabs >= GRABS_MAX || performance.now() - since > ATTEST_GRACE_MS + LATE_MS) stop.current();
    };
    /** Starts the wait on the frame, if it has the keyboard with no offer and is not waited on yet. */
    const suspect = (from: HTMLElement | null) => {
      const taker = frame.current;
      if (taker === null || document.activeElement !== taker || offered || waiting !== undefined) return;
      const since = performance.now();
      waiting = setTimeout(() => settle(taker, from, since), ATTEST_GRACE_MS);
    };
    told.current = () => {
      offered = true;
      clearTimeout(waiting);
      waiting = undefined;
    };

    const pointed = (event: Event) => {
      if (away) suspect(kept);
      if (event.type === "pointerdown" && box.current?.contains(event.target as Node) !== true) offered = false;
    };
    const pressed = (event: KeyboardEvent) => {
      offered = event.key === "Tab";
    };
    const arrived = (event: FocusEvent) => {
      if (event.target !== frame.current) offered = false;
    };
    const leaving = (event: FocusEvent) => {
      if (event.target === frame.current) return;
      left = event.target as HTMLElement;
      clearTimeout(forgetting);
      forgetting = setTimeout(() => {
        left = null;
      }, 0);
    };
    const blurred = () => {
      const active = document.activeElement;
      if (active === frame.current) {
        suspect(left ?? kept);
        return;
      }
      // Lost to another window or to the browser's own controls, not to the page.
      away = true;
      kept = active as HTMLElement | null;
    };
    const returned = () => {
      clearTimeout(returning);
      // A task later: a browser may put the focus back where it was only after it told of the window's.
      returning = setTimeout(() => {
        suspect(kept);
        away = false;
        kept = null;
      }, 0);
    };
    const shown = () => {
      // Not while the tab is hidden: its timers run late, and a wait that ends late stops the page.
      if (document.visibilityState === "visible") suspect(kept);
    };

    for (const type of POINTER_EVENTS) document.addEventListener(type, pointed, { capture: true, passive: true });
    document.addEventListener("keydown", pressed, true);
    document.addEventListener("focusin", arrived, true);
    document.addEventListener("focusout", leaving, true);
    document.addEventListener("visibilitychange", shown);
    window.addEventListener("blur", blurred);
    window.addEventListener("focus", returned);
    return () => {
      for (const type of POINTER_EVENTS) document.removeEventListener(type, pointed, true);
      document.removeEventListener("keydown", pressed, true);
      document.removeEventListener("focusin", arrived, true);
      document.removeEventListener("focusout", leaving, true);
      document.removeEventListener("visibilitychange", shown);
      window.removeEventListener("blur", blurred);
      window.removeEventListener("focus", returned);
      told.current = undefined;
      for (const timer of [forgetting, returning, waiting]) clearTimeout(timer);
    };
  }, [frame]);

  return { box, attest };
}
