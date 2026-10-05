/**
 * Every canvas there is, newest first, for the library on the manage screen, with what all the
 * versions of each one hold and a search by name.
 *
 * The list and the sizes are two reads sent together, and each shows as it arrives: sizes that
 * cannot be read leave the canvases listed without them. A name is searched for a quarter of a
 * second after the last key. Any canvas change from the stream reads both again, gathered into one
 * read half a second after the first of a burst, as do the stream coming back and the tab showing.
 * An answer older than the last read asked for is dropped.
 *
 * A delete drops the canvas as the server answers, without waiting for the stream to say so, and
 * tells whatever else shows that canvas. A canvas the server no longer has was deleted already.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import type { ArtifactSummary, ArtifactUsage } from "../api/artifact-types";
import { ApiError } from "../api/client";
import { announceDeletion, onArtifactEvent } from "../lib/artifact-events";
import { LIST_RELOAD_MS } from "./use-canvas-list";
import { useReloadOnReconnect } from "./use-reload-on-reconnect";

/** How long after the last key a name is searched for. */
export const SEARCH_WAIT_MS = 250;
/** The most canvases the server lists at once. */
export const LIBRARY_LIMIT = 200;

export type CanvasLibrary = {
  /** The search box as typed. */
  query: string;
  setQuery(query: string): void;
  /** The words `items` was read with: "" for every canvas. */
  searched: string;
  /** Null until the first read lands. */
  items: ArtifactSummary[] | null;
  /** Null until read, and when the last read of the sizes failed. */
  usage: ArtifactUsage | null;
  /** The last read of the list failed; `items` still holds what an earlier one found. */
  failed: boolean;
  retry(): void;
  /** Resolves once the server has answered: whether the canvas is gone, now or already. */
  remove(id: string): Promise<boolean>;
  /** The canvases whose last delete did not go through. */
  refused: ReadonlySet<string>;
};

type Listed = Pick<CanvasLibrary, "items" | "searched" | "failed">;

/** `usage` without canvas `id`; unchanged for a canvas made since the sizes were read. */
function without(usage: ArtifactUsage, id: string): ArtifactUsage {
  const { [id]: size, ...rest } = usage.by_artifact;
  if (size === undefined) return usage;
  return { ...usage, count: usage.count - 1, bytes: usage.bytes - size, by_artifact: rest };
}

export function useCanvasLibrary(connected: boolean): CanvasLibrary {
  const [query, setQuery] = useState("");
  const [listed, setListed] = useState<Listed>({ items: null, searched: "", failed: false });
  const [usage, setUsage] = useState<ArtifactUsage | null>(null);
  const [refused, setRefused] = useState<ReadonlySet<string>>(new Set());
  const asked = useRef(0);
  // The words the next read goes with: the box, trimmed, once the wait after the last key is over.
  const words = useRef("");

  const load = useCallback(() => {
    const ticket = ++asked.current;
    const searched = words.current;
    const newest = () => ticket === asked.current;
    artifactApi.list(undefined, searched, LIBRARY_LIMIT).then(
      (items) => newest() && setListed({ items, searched, failed: false }),
      () => newest() && setListed((was) => ({ ...was, failed: true })),
    );
    artifactApi.usage().then(
      (read) => newest() && setUsage(read),
      () => newest() && setUsage(null),
    );
  }, []);

  useEffect(() => {
    load();
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
  }, [load]);

  useEffect(() => {
    const next = query.trim();
    if (next === words.current) return;
    const timer = setTimeout(() => {
      words.current = next;
      load();
    }, SEARCH_WAIT_MS);
    return () => clearTimeout(timer);
  }, [query, load]);

  useReloadOnReconnect(connected, load);

  const remove = useCallback(async (id: string) => {
    setRefused((was) => (was.has(id) ? new Set([...was].filter((other) => other !== id)) : was));
    try {
      await artifactApi.remove(id);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) {
        setRefused((was) => new Set(was).add(id));
        return false;
      }
    }
    setListed((was) => ({ ...was, items: was.items?.filter((item) => item.id !== id) ?? null }));
    setUsage((was) => was && without(was, id));
    announceDeletion(id);
    return true;
  }, []);

  return { query, setQuery, ...listed, usage, retry: load, remove, refused };
}
