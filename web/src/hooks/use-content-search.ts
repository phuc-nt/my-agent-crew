import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ContentHit } from "../api/types";

/** Below this, a query is still someone mid-word; searching now would just churn. */
const MIN_QUERY_LENGTH = 2;
/** How long to wait after the last keystroke before actually calling the API. */
const DEBOUNCE_MS = 250;

export interface ContentSearchState {
  /** `null` before the first answer lands, or once the query drops back below the minimum. */
  hits: ContentHit[] | null;
  loading: boolean;
  /** A real failure only; a request this hook cancelled itself never sets this. */
  error: boolean;
  /** Runs the same query again, right away, skipping the debounce; for the error state's button. */
  retry: () => void;
}

/**
 * Debounced search over message content, behind the sidebar's title search box.
 *
 * `enabled` gates the feature entirely (there is no agent to search as, e.g. before the
 * active agent is known), not just whether a specific query is short enough to run.
 */
export function useContentSearch(query: string, enabled: boolean): ContentSearchState {
  const [state, setState] = useState<Omit<ContentSearchState, "retry">>({
    hits: null,
    loading: false,
    error: false,
  });
  // Bumped by `retry()` so the effect below re-runs even when `query` itself did not change.
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!enabled || trimmed.length < MIN_QUERY_LENGTH) {
      setState({ hits: null, loading: false, error: false });
      return;
    }

    setState((prev) => ({ ...prev, loading: true, error: false }));
    const controller = new AbortController();
    // A retry is a direct request, not another keystroke, so it skips the debounce wait.
    const delay = attempt > 0 ? 0 : DEBOUNCE_MS;
    const timer = setTimeout(() => {
      api.searchMessages(trimmed, controller.signal).then(
        (found) => {
          if (controller.signal.aborted) return;
          setState({ hits: found.hits, loading: false, error: false });
        },
        (err: unknown) => {
          if (controller.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
          setState({ hits: null, loading: false, error: true });
        },
      );
    }, delay);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, enabled, attempt]);

  return { ...state, retry };
}
