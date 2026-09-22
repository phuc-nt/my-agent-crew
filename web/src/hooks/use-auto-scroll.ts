import { useCallback, useEffect, useRef, useState } from "react";

/** How far off the bottom still counts as "at the bottom". One line of prose, roughly:
 *  small enough that a deliberate scroll up registers, large enough to survive the
 *  sub-pixel rounding a zoomed-in browser reports. */
const SLACK_PX = 48;

/**
 * Keeps a scrolling element pinned to its last line while content arrives, and stops
 * the moment the person scrolls up to read something.
 *
 * A reply streams in token by token, so the element grows on frames where nothing about
 * the React tree changed — no new message, no new text prop at this level. Watching the
 * scroll height directly is what catches that; an effect keyed on the message list only
 * fires once per message and leaves the tail hidden for everything in between.
 *
 * Scrolling up is treated as intent: it is the only reason to be anywhere but the bottom
 * of a live conversation, and yanking someone back mid-sentence is worse than a stale
 * view they can fix with one click. `atBottom` is false exactly when that has happened,
 * which is what a "jump to newest" button keys off.
 */
export function useAutoScroll<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  // Read by the observer, which must not re-subscribe every time the flag flips.
  const pinned = useRef(true);

  const scrollToBottom = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    pinned.current = true;
    setAtBottom(true);
  }, []);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX;
    pinned.current = bottom;
    setAtBottom(bottom);
  }, []);

  useEffect(() => {
    const el = ref.current;
    // jsdom has no ResizeObserver and a test that only renders never scrolls anything,
    // so the absence of one is a no-op rather than a crash.
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinned.current) el.scrollTop = el.scrollHeight;
    });
    observer.observe(el);
    // The content grows inside the element, which does not resize the element itself;
    // observing the children is what reports a taller reply.
    for (const child of Array.from(el.children)) observer.observe(child);
    return () => observer.disconnect();
  });

  return { ref, atBottom, scrollToBottom, onScroll };
}
