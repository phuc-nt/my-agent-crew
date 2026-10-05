/**
 * The canvases of the open conversation, newest first, for the picker and the count on the Canvas
 * button, and what a card in the thread needs to know of a canvas: its title, and whether it is
 * still there.
 *
 * Any canvas change from the stream reads the list again, not only one naming this conversation:
 * a new canvas is announced before it is linked, so its announcement names none. Changes come in
 * bursts while an agent writes, so they are gathered into one read half a second after the first.
 * The list is also read again as the stream comes back and as the tab shows, either of which may
 * have missed changes. A reply for a conversation no longer open, or older than the last read
 * asked for, is dropped.
 *
 * A card may name a canvas the list does not hold: one deleted since, or one past the list's limit.
 * Once the list is in, and after each later read of it, every canvas a card asked about that it does
 * not hold is read from the server once. A 200 keeps the canvas's summary for its title and a 404 is
 * a deletion, which every listener hears as it would from the stream. Any other answer settles
 * nothing, so the next read of the list asks again.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import type { ArtifactSummary } from "../api/artifact-types";
import { ApiError } from "../api/client";
import { announceDeletion, onArtifactEvent } from "../lib/artifact-events";
import { isArtifactId } from "../lib/artifact-tag";
import { summaryOf } from "../lib/canvas-state";
import { useReloadOnReconnect } from "./use-reload-on-reconnect";

/** How long after a canvas change the list is read again. */
export const LIST_RELOAD_MS = 500;

export type CanvasList = {
  /** Null until the first read lands. */
  items: ArtifactSummary[] | null;
  /** The last read failed; `items` still holds what an earlier one found. */
  failed: boolean;
  retry(): void;
  /** The title the list gives a canvas, or else the one a read of it did; null when neither has. */
  titleOf(id: string): string | null;
  /** The kind of a canvas, from the same two places as its title. */
  kindOf(id: string): string | null;
  /** The stream or a read said the canvas is deleted. */
  isGone(id: string): boolean;
  /** Asks the server about canvas `id` as soon as the list is in, and after each later read of it,
   *  while the list does not hold it and no answer has settled. An id the server does not make is
   *  never asked about. */
  verify(id: string): void;
};

type Loaded = { conversationId: string | null; items: ArtifactSummary[] | null; failed: boolean };
type Known = { read: ReadonlyMap<string, ArtifactSummary>; gone: ReadonlySet<string> };

const NOTHING_KNOWN: Known = { read: new Map(), gone: new Set() };

export function useCanvasList(conversationId: string | null, connected: boolean): CanvasList {
  const [loaded, setLoaded] = useState<Loaded>({ conversationId, items: null, failed: false });
  const [known, setKnown] = useState(NOTHING_KNOWN);
  const asked = useRef(0);
  // What the open conversation's last read found, the ids cards asked about, and which of those
  // the server has answered or is answering. An answer is a fact about the canvas, whatever
  // conversation is open, so the last two outlive one.
  const listed = useRef<ArtifactSummary[] | null>(null);
  const wanted = useRef(new Set<string>());
  const settled = useRef(new Set<string>());
  const reading = useRef(new Set<string>());

  const check = useCallback((id: string) => {
    if (listed.current === null || listed.current.some((item) => item.id === id)) return;
    if (settled.current.has(id) || reading.current.has(id)) return;
    reading.current.add(id);
    artifactApi
      .get(id)
      .then(
        (detail) => {
          settled.current.add(id);
          setKnown((was) => ({ ...was, read: new Map(was.read).set(id, summaryOf(detail)) }));
        },
        (error: unknown) => {
          // Only a 404 says the canvas is gone; a lost connection or a 5xx says nothing yet.
          if (!(error instanceof ApiError) || error.status !== 404) return;
          settled.current.add(id);
          announceDeletion(id);
        },
      )
      .finally(() => reading.current.delete(id));
  }, []);

  const verify = useCallback(
    (id: string) => {
      if (!isArtifactId(id)) return;
      wanted.current.add(id);
      check(id);
    },
    [check],
  );

  const load = useCallback(() => {
    const ticket = ++asked.current;
    if (conversationId === null) return;
    artifactApi.list(conversationId).then(
      (items) => {
        if (ticket !== asked.current) return;
        listed.current = items;
        setLoaded({ conversationId, items, failed: false });
        wanted.current.forEach(check);
      },
      () => {
        if (ticket !== asked.current) return;
        setLoaded((was) => ({
          conversationId,
          items: was.conversationId === conversationId ? was.items : null,
          failed: true,
        }));
      },
    );
  }, [conversationId, check]);

  useEffect(() => {
    load();
    if (conversationId === null) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = onArtifactEvent(({ artifact }) => {
      if ("deleted" in artifact) {
        setKnown((was) => (was.gone.has(artifact.id) ? was : { ...was, gone: new Set(was.gone).add(artifact.id) }));
      }
      if (timer !== undefined) return;
      timer = setTimeout(() => {
        timer = undefined;
        load();
      }, LIST_RELOAD_MS);
    });
    const shown = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", shown);
    return () => {
      unsubscribe();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", shown);
      // Cards that mount next register after this runs; clearing as the next effect starts would
      // wipe what they had registered, as a child's effect runs before its parent's.
      listed.current = null;
      wanted.current.clear();
    };
  }, [conversationId, load]);

  useReloadOnReconnect(connected, load);
  const current = loaded.conversationId === conversationId ? loaded : null;
  const items = current?.items ?? null;
  return {
    items,
    failed: current?.failed ?? false,
    retry: load,
    titleOf: (id) => items?.find((item) => item.id === id)?.title ?? known.read.get(id)?.title ?? null,
    kindOf: (id) => items?.find((item) => item.id === id)?.kind ?? known.read.get(id)?.kind ?? null,
    isGone: (id) => known.gone.has(id),
    verify,
  };
}
