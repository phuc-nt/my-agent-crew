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
 *
 * Only moving up lets go. The browser reports a scroll a frame after it happened, so the jump
 * this hook makes to follow a reply is read against whatever has arrived since: a reply that
 * lands in a burst makes that reading look far from the bottom although nobody scrolled, and
 * judging by the gap alone would drop the following the moment the answer appears.
 */
export function useAutoScroll<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  // Read by the observer, which must not re-subscribe every time the flag flips.
  const pinned = useRef(true);
  // Where the element was last left, by a scroll event or by this hook's own jump; unknown
  // until one of them has happened, and then the first event is judged by the gap alone.
  const lastTop = useRef<number | null>(null);

  const follow = useCallback((el: T) => {
    el.scrollTop = el.scrollHeight;
    // Read back rather than assumed: the browser stops at the real last line.
    lastTop.current = el.scrollTop;
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    follow(el);
    pinned.current = true;
    setAtBottom(true);
  }, [follow]);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const movedDown = lastTop.current !== null && el.scrollTop >= lastTop.current;
    lastTop.current = el.scrollTop;
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX;
    const next = bottom || (pinned.current && movedDown);
    pinned.current = next;
    setAtBottom(next);
  }, []);

  useEffect(() => {
    const el = ref.current;
    // jsdom has no ResizeObserver and a test that only renders never scrolls anything,
    // so the absence of one is a no-op rather than a crash.
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (pinned.current) follow(el);
    });
    observer.observe(el);
    // The content grows inside the element, which does not resize the element itself;
    // observing the children is what reports a taller reply.
    for (const child of Array.from(el.children)) observer.observe(child);
    return () => observer.disconnect();
  });

  return { ref, atBottom, scrollToBottom, onScroll };
}
