import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { newestFirst } from "../lib/run-order";
import { isSettled } from "../lib/run-progress";

export interface RunHistoryQuery {
  agentId?: string | null;
  /** A conversation's runs come back with those of the work it delegated. */
  conversationId?: string | null;
  limit: number;
  /** Any value that changes when the history is worth asking for again. */
  refreshKey?: unknown;
}

export interface RunHistory {
  runs: RunInfo[];
  loading: boolean;
  failed: boolean;
  /** The limit the runs on show were asked with, zero before any came back. A page as
   * long as this may have more behind it; a shorter one was everything there is. */
  pageLimit: number;
  reload: () => void;
}

interface Loaded {
  key: string;
  runs: RunInfo[];
  limit: number;
  loading: boolean;
  failed: boolean;
}

/**
 * Stored runs fetched on demand, narrowed on the server.
 *
 * The live stream only knows what happened while the page was open, and the crew-wide
 * page it starts from is fifty runs of whoever was busiest. A view about one conversation
 * or one agent asks for its own history instead, so a quiet one is not an empty one.
 */
export function useRunHistory({
  agentId,
  conversationId,
  limit,
  refreshKey,
}: RunHistoryQuery): RunHistory {
  const key = `${agentId ?? ""}|${conversationId ?? ""}`;
  const [loaded, setLoaded] = useState<Loaded>({ key, runs: [], limit: 0, loading: true, failed: false });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // A reply for a query that has since changed must not land on the new one.
    let current = true;
    setLoaded((prev) => ({ ...prev, loading: true, failed: false }));
    api
      .listRuns({ limit, agent_id: agentId ?? undefined, conversation_id: conversationId ?? undefined })
      .then((runs) => current && setLoaded({ key, runs, limit, loading: false, failed: false }))
      // Filed under this query even when the last answer was another's: left under the
      // old key, the failure would read as a load still waiting, with no way to retry.
      .catch(
        () =>
          current &&
          setLoaded((prev) =>
            prev.key === key
              ? { ...prev, loading: false, failed: true }
              : { key, runs: [], limit: 0, loading: false, failed: true },
          ),
      );
    return () => {
      current = false;
    };
  }, [key, agentId, conversationId, limit, refreshKey, attempt]);

  // The failure goes in the same render as the retry, not one later: a view that moves the
  // focus once the page it waits for settles would take the old failure for that page.
  const reload = useCallback(() => {
    setLoaded((prev) => ({ ...prev, loading: true, failed: false }));
    setAttempt((n) => n + 1);
  }, []);
  // Another conversation's or agent's history is never shown while this one's loads.
  const same = loaded.key === key;
  return {
    runs: same ? loaded.runs : [],
    loading: loaded.loading || !same,
    failed: same && loaded.failed,
    pageLimit: same ? loaded.limit : 0,
    reload,
  };
}

/**
 * Fetched history and streamed runs as one list, newest first, each run once.
 *
 * The streamed copy is usually the fresher one — it carries the step still being written.
 * Not when it is stuck open: a run that ended while the stream was down is settled in the
 * store, and the store's word wins over a copy that never heard the ending.
 */
export function mergeRuns(history: RunInfo[], streamed: RunInfo[]): RunInfo[] {
  const read = new Map(history.map((run) => [run.id, run]));
  // A run the history lacks started after it was read, so those go ahead of it: of runs
  // that tie in `newestFirst`, the one only the stream knows is the newer.
  const byId = new Map(streamed.filter((run) => !read.has(run.id)).map((run) => [run.id, run]));
  for (const run of history) byId.set(run.id, run);
  for (const run of streamed) {
    const stored = read.get(run.id);
    if (stored && isSettled(stored.status) && !isSettled(run.status)) continue;
    byId.set(run.id, run);
  }
  return [...byId.values()].sort(newestFirst);
}
