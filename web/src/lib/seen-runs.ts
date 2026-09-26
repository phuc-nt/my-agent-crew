/**
 * The failed and halted runs the person has marked as read, so they stop asking for
 * attention on this device.
 *
 * Kept per device in localStorage rather than on the server: "I have seen this" is about
 * one screen, not about the run. Storage can be refused outright (a private window, a
 * browser that blocks site data), so the tab's own copy is the one it reads — storage only
 * seeds it and keeps it past a reload when it is allowed to.
 */
const KEY = "attention.seen";
/** Enough to cover every failure a busy week lists; older ids have long left the list. */
const LIMIT = 100;

const listeners = new Set<() => void>();
/** Null until first read, and again when another tab wrote a newer list. */
let seen: string[] | null = null;

function load(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string").slice(-LIMIT) : [];
  } catch {
    // Refused or unreadable storage starts the tab with nothing dismissed.
    return [];
  }
}

/** The ids marked as seen, oldest first. The same array until something changes. */
export function seenRuns(): string[] {
  seen ??= load();
  return seen;
}

export function markSeen(runId: string): void {
  const known = seenRuns();
  if (known.includes(runId)) return;
  seen = [...known, runId].slice(-LIMIT);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(seen));
  } catch {
    // Refused storage: the tab's copy still hides the row until the page reloads.
  }
  for (const listener of listeners) listener();
}

/** For useSyncExternalStore: this tab's dismissals, and another tab's through `storage`. */
export function subscribeSeen(listener: () => void): () => void {
  const fromOtherTab = (event: StorageEvent) => {
    if (event.key !== KEY && event.key !== null) return;
    seen = null;
    listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", fromOtherTab);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", fromOtherTab);
  };
}
