/**
 * Whether a canvas the agent is still writing is shown while it fills in: a choice of this device,
 * on until the person turns it off.
 *
 * The browser stores the one word "off" and nothing else, least of all anything of a canvas. One
 * that refuses to store it still gets the choice: the tab keeps it until the page reloads, and the
 * hook says so, for the person would otherwise find it undone the next time they came.
 */

import { useSyncExternalStore } from "react";
import { readText, writeText } from "../lib/local-store";

const KEY = "canvas.livePreview";

const listeners = new Set<() => void>();
/** The choice the browser would not store; null while the stored one is the one that counts. */
let held: boolean | null = null;

const enabledNow = () => held ?? readText(KEY) !== "off";
const tabOnlyNow = () => held !== null;

/** This tab's choices, and another tab's, which arrive as the browser's `storage` event. */
function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function set(enabled: boolean): void {
  held = writeText(KEY, enabled ? null : "off") ? null : enabled;
  for (const listener of listeners) listener();
}

export type LivePreview = {
  enabled: boolean;
  /** The browser refused to store the choice, so it lasts only as long as this tab does. */
  tabOnly: boolean;
  set(enabled: boolean): void;
};

export function useLivePreview(): LivePreview {
  const enabled = useSyncExternalStore(subscribe, enabledNow);
  const tabOnly = useSyncExternalStore(subscribe, tabOnlyNow);
  return { enabled, tabOnly, set };
}
