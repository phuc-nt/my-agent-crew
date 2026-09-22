import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { isSettled } from "../lib/run-progress";
import { RunCard } from "./run-timeline";

interface Props {
  runId: string;
  /** The runs already on screen, so a run being watched keeps updating while it is open. */
  known: RunInfo[];
  agentName: (id: string) => string;
  onBack: () => void;
  onOpenConversation: (conversationId: string) => void;
}

/**
 * One past run on its own, opened by id from the URL.
 *
 * The activity list only reaches back as far as it was asked to load, so a run linked to
 * from elsewhere — or found after scrolling away — has to be fetched by id rather than
 * looked up in what happens to be in memory.
 *
 * A run still working is read from that list instead: it is the copy the live stream
 * keeps writing to, so it goes on ticking rather than freezing at whatever the fetch
 * returned. Once it settles the preference reverses. The stream's last word about a run
 * carries its final status but not its finish time — that is stamped separately, after
 * the event goes out — and a settled run is never refreshed from the list again, so the
 * copy in memory keeps a finish time that never arrives. The fetch has the real one.
 */
export function RunReplay({ runId, known, agentName, onBack, onOpenConversation }: Props) {
  const inList = known.find((r) => r.id === runId) ?? null;
  const live = inList && !isSettled(inList.status) ? inList : null;
  // The effect turns on these two facts, not on the run objects themselves: the stream
  // hands us a new object for the same run on every frame, and depending on one would
  // re-fetch the run each time it ticked.
  const isLive = live !== null;
  const held = inList !== null;
  const [fetched, setFetched] = useState<RunInfo | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // A run still working is already current in memory; fetching would race the stream.
    if (isLive) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .getRun(runId)
      .then((run) => {
        if (!cancelled) setFetched(run);
      })
      .catch((reason) => {
        // Only a 404 means the run is gone. A server error or a dropped
        // connection told the same story, which sent people looking for a
        // deletion that had never happened.
        //
        // A run we already hold needs no error at all: the fetch was only after a
        // better copy, and saying "not found" over a run plainly on screen is worse
        // than quietly showing the copy we have.
        if (cancelled || held) return;
        const missing = reason instanceof ApiError && reason.status === 404;
        setError(missing ? vi.replay.notFound(runId) : vi.replay.failed);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, isLive, held]);

  // The fetched copy is the better one, but the list copy is already here: showing it
  // while the fetch is in flight keeps the run on screen instead of blanking the card.
  const run = fetched ?? inList;
  return (
    <section className="run-replay" data-testid="run-replay">
      <button type="button" className="link-button" onClick={onBack}>
        {vi.replay.back}
      </button>
      {loading && <p className="muted">{vi.replay.loading}</p>}
      {error && (
        <p className="notice error" role="status">
          {error}
        </p>
      )}
      {run && (
        <RunCard
          run={run}
          agentName={agentName(run.agent_id)}
          expanded
          onOpenConversation={onOpenConversation}
        />
      )}
    </section>
  );
}
