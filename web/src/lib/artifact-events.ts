/**
 * Canvas changes from the activity stream, for whatever shows a canvas. `useActivity` owns the
 * one `EventSource` and hands each `artifact` payload here, so a panel or a list listens without
 * opening a second stream.
 *
 * Events are hints: a tab hears each at most once, and none while the stream is down. Listeners
 * read the canvas back after a reconnect rather than wait for a missed event.
 */

import type { ArtifactEvent } from "../api/artifact-types";

type Subscription = { listener: (event: ArtifactEvent) => void };

// One object per subscription, so subscribing a function twice and removing it once keeps it.
const subscriptions = new Set<Subscription>();

/** Hears every canvas change until the returned function is called. */
export function onArtifactEvent(listener: (event: ArtifactEvent) => void): () => void {
  const subscription = { listener };
  subscriptions.add(subscription);
  return () => {
    subscriptions.delete(subscription);
  };
}

/** Like a DOM event: a listener removed during delivery is skipped, one added waits for the next. */
export function emitArtifactEvent(event: ArtifactEvent): void {
  for (const subscription of [...subscriptions]) {
    if (subscriptions.has(subscription)) subscription.listener(event);
  }
}
