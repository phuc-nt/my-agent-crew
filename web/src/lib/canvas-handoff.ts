/**
 * Saves that outlive the moment: one sent as the page may be going away, and the last save of a
 * canvas the person left without waiting for it.
 *
 * A browser caps the bodies of the `keepalive` requests in flight at 64 KiB and refuses a new one
 * that would go over, so a save is kept alive only while the page is hidden, only up to 60 KiB and
 * only while no other kept-alive save is out. Any other save goes as a plain request, which a
 * closing page may cut; the draft written as the page hid still holds its text.
 */

import { saveBody } from "../api/artifact-client";
import type { CanvasState } from "./canvas-types";

/** The largest save body sent with `keepalive`, leaving room under the browser's 64 KiB. */
export const KEEPALIVE_MAX = 60 * 1024;

/** A canvas whose last save failed after its panel went away. */
export type HandoffFailure = { id: string; title: string | null };

/** What `saveInBackground` needs of a canvas runner. */
type Leaving = { readonly id: string; readonly state: CanvasState; flush(): Promise<number | null> };

let keepaliveOut = false;
const listeners = new Set<{ listener: (failure: HandoffFailure) => void }>();

function fitsKeepalive(content: string, baseVersion: number): boolean {
  const body = saveBody(content, baseVersion);
  // A UTF-16 unit is one to three UTF-8 bytes; measure only when the length cannot tell.
  if (body.length > KEEPALIVE_MAX) return false;
  return body.length * 3 <= KEEPALIVE_MAX || new TextEncoder().encode(body).length <= KEEPALIVE_MAX;
}

/** Runs `send`, asking it to keep the request alive when the page is `hidden`, the save's body
 *  fits and no other kept-alive save is out. */
export async function withKeepalive<T>(
  hidden: boolean,
  content: string,
  baseVersion: number,
  send: (keepalive: boolean) => Promise<T>,
): Promise<T> {
  if (!hidden || keepaliveOut || !fitsKeepalive(content, baseVersion)) return send(false);
  keepaliveOut = true;
  try {
    return await send(true);
  } finally {
    keepaliveOut = false;
  }
}

/** Hears each canvas whose last save failed after its panel went away. */
export function onHandoffFailed(listener: (failure: HandoffFailure) => void): () => void {
  const subscription = { listener };
  listeners.add(subscription);
  return () => void listeners.delete(subscription);
}

/**
 * Saves what the person left in a canvas, after the save in flight if one is. The draft written as
 * the panel went away goes once a version holds its text; when no version can, it stays on this
 * device and the listeners hear of it.
 */
export async function saveInBackground(runner: Leaving): Promise<void> {
  if ((await runner.flush()) !== null) return;
  const failure = { id: runner.id, title: runner.state.summary?.title ?? null };
  for (const { listener } of [...listeners]) listener(failure);
}
