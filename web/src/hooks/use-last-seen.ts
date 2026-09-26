import { useEffect, useState } from "react";
import type { Conversation } from "../api/types";

const KEY = "conversation-list.seen";

/**
 * When this viewer last had each conversation open, as the conversation's own
 * `updated_at` at that moment. `since` is when the viewer first used this, so a list that
 * predates it does not open with every row marked unread.
 */
interface Seen {
  since: string;
  seen: Record<string, string>;
}

function read(): Seen | null {
  try {
    const stored = JSON.parse(window.localStorage.getItem(KEY) ?? "null") as Seen | null;
    if (stored && typeof stored.since === "string" && stored.seen) return stored;
  } catch {
    // Unreadable or refused: the same as nothing stored.
  }
  return null;
}

/** What was stored, or a first visit's baseline: nothing before now counts as unread. */
function load(): Seen {
  return read() ?? { since: new Date().toISOString(), seen: {} };
}

function save(value: Seen): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Storage refused: the marks hold for this page and are forgotten on reload.
  }
}

/** Compared as instants: the server writes `+00:00`, the browser `Z`, so strings would not order. */
function after(a: string, b: string): boolean {
  const left = Date.parse(a);
  const right = Date.parse(b);
  return !Number.isNaN(left) && !Number.isNaN(right) && left > right;
}

function later(a: string | undefined, b: string | undefined): string | undefined {
  return a && b && after(b, a) ? b : (a ?? b);
}

/**
 * Which conversations changed since this viewer last opened them.
 *
 * The open conversation is marked seen at every change it goes through while open, so
 * leaving it records the last thing on screen; a reply that lands after that makes the
 * row unread until it is opened again. Kept per browser, since "seen" is about the person
 * looking at this screen, not about the conversation.
 */
export function useLastSeen(conversations: Conversation[], activeId: string | null) {
  const [state, setState] = useState(load);
  const stamp = conversations.find((c) => c.id === activeId)?.updated_at;

  useEffect(() => {
    if (!activeId || !stamp) return;
    setState((previous) => {
      if (previous.seen[activeId] === stamp) return previous;
      // Another tab of this browser may have written since this one loaded. Its marks are
      // merged in, the later stamp winning, so what was read there is not unread again here.
      const stored = read();
      // Rows that left the list were deleted; dropping them keeps the stored map the
      // size of the list rather than of every conversation ever opened.
      const seen: Record<string, string> = {};
      for (const c of conversations) {
        const mark = later(previous.seen[c.id], stored?.seen[c.id]);
        if (mark) seen[c.id] = mark;
      }
      seen[activeId] = later(seen[activeId], stamp) ?? stamp;
      const next = { since: stored?.since ?? previous.since, seen };
      save(next);
      return next;
    });
    // `conversations` is read for pruning only; a list refresh alone changes nothing seen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, stamp]);

  // Written once so a first visit's baseline survives a reload; never over another tab's map.
  useEffect(() => {
    if (read() === null) save(state);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (c: Conversation): boolean =>
    c.id !== activeId && after(c.updated_at, state.seen[c.id] ?? state.since);
}
