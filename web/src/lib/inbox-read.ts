/**
 * When the person last read the inbox on this device: a job's result that finished after
 * it is new to them.
 *
 * One moment rather than a list of ids: the inbox is read the way a mailbox is, top down,
 * and opening it is reading what it holds. Kept per device for the reason `seen-runs`
 * gives — "I have read this" is about one screen — and through the same refusal-proof
 * store, so a private window still counts down while the tab is open.
 */
import { readText, writeText } from "./local-store";

const KEY = "inbox.readAt";

const listeners = new Set<() => void>();
/** Undefined until first read, and again when another tab wrote a newer moment. */
let readAt: string | null | undefined;

/** The ISO time the inbox was last read here, or null when it never was. */
export function inboxReadAt(): string | null {
  readAt ??= readText(KEY);
  return readAt;
}

/** Records the inbox as read up to `at`; an earlier moment than the stored one is ignored. */
export function markInboxRead(at: string): void {
  const known = inboxReadAt();
  if (known !== null && Date.parse(known) >= Date.parse(at)) return;
  readAt = at;
  writeText(KEY, at);
  for (const listener of listeners) listener();
}

/** For useSyncExternalStore: this tab's reading, and another tab's through `storage`. */
export function subscribeInboxRead(listener: () => void): () => void {
  const fromOtherTab = (event: StorageEvent) => {
    if (event.key !== KEY && event.key !== null) return;
    readAt = undefined;
    listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", fromOtherTab);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", fromOtherTab);
  };
}

/** Forgets the tab's copy, for tests that clear storage between cases. */
export function resetInboxRead(): void {
  readAt = undefined;
}
