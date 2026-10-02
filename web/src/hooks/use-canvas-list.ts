/**
 * The canvases of the open conversation, newest first, for the picker and the count on the Canvas
 * button.
 *
 * Any canvas change from the stream reads the list again, not only one naming this conversation:
 * a new canvas is announced before it is linked, so its announcement names none. Changes come in
 * bursts while an agent writes, so they are gathered into one read half a second after the first.
 * The list is also read again as the stream comes back and as the tab shows, either of which may
 * have missed changes. A reply for a conversation no longer open, or older than the last read
 * asked for, is dropped.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import type { ArtifactSummary } from "../api/artifact-types";
import { onArtifactEvent } from "../lib/artifact-events";
import { useReloadOnReconnect } from "./use-reload-on-reconnect";

/** How long after a canvas change the list is read again. */
export const LIST_RELOAD_MS = 500;

export type CanvasList = {
  /** Null until the first read lands. */
  items: ArtifactSummary[] | null;
  /** The last read failed; `items` still holds what an earlier one found. */
  failed: boolean;
  retry(): void;
};

type Loaded = { conversationId: string | null; items: ArtifactSummary[] | null; failed: boolean };

export function useCanvasList(conversationId: string | null, connected: boolean): CanvasList {
  const [loaded, setLoaded] = useState<Loaded>({ conversationId, items: null, failed: false });
  const asked = useRef(0);

  const load = useCallback(() => {
    const ticket = ++asked.current;
    if (conversationId === null) return;
    artifactApi.list(conversationId).then(
      (items) => {
        if (ticket === asked.current) setLoaded({ conversationId, items, failed: false });
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
  }, [conversationId]);

  useEffect(() => {
    load();
    if (conversationId === null) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = onArtifactEvent(() => {
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
    };
  }, [conversationId, load]);

  useReloadOnReconnect(connected, load);
  const current = loaded.conversationId === conversationId ? loaded : null;
  return { items: current?.items ?? null, failed: current?.failed ?? false, retry: load };
}
