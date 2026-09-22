import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
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
 * looked up in what happens to be in memory. When the run is one of those already on
 * screen that copy wins: it is the one the live stream keeps writing to, so a run still
 * working goes on ticking instead of freezing at whatever the fetch returned.
 */
export function RunReplay({ runId, known, agentName, onBack, onOpenConversation }: Props) {
  const live = known.find((r) => r.id === runId) ?? null;
  const [fetched, setFetched] = useState<RunInfo | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Already on screen means already current; fetching would only race the stream.
    if (live) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .getRun(runId)
      .then((run) => {
        if (!cancelled) setFetched(run);
      })
      .catch(() => {
        if (!cancelled) setError(vi.replay.notFound(runId));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, live]);

  const run = live ?? fetched;
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
