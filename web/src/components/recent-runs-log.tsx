import { useEffect, useState } from "react";
import type { AgentInfo, RunInfo } from "../api/types";
import { mergeRuns, useRunHistory } from "../hooks/use-run-history";
import { vi } from "../i18n/vi";
import { isSettled } from "../lib/run-progress";
import {
  NO_FILTERS,
  filterRuns,
  readFilters,
  sourceKinds,
  writeFilters,
  type RunFilters,
} from "../lib/run-filters";
import { runGroups } from "../state/activity-reducer";
import { ActivityFilters } from "./activity-filters";
import { EmptyState } from "./empty-state";
import { RunGroupCard } from "./run-timeline";

// How far back each "Xem thêm" reaches. The last is the server's own ceiling, so the
// button goes away there rather than asking for rows that will never come.
export const HISTORY_STEPS = [100, 200, 500];

interface Props {
  /** Finished runs the live stream knows, newest first. */
  streamed: RunInfo[];
  agents: AgentInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  onOpenRun: (runId: string) => void;
  onBackToChat: () => void;
}

/**
 * The crew's finished runs, newest first, with chips to narrow them and a way further back.
 *
 * The stream's page is fifty runs of whoever was busiest, so this fetches its own history
 * and lays the streamed runs over it: what finished a second ago shows without a request.
 */
export function RecentRunsLog({
  streamed,
  agents,
  agentName,
  onOpenConversation,
  onOpenRun,
  onBackToChat,
}: Props) {
  const [saved, setFilters] = useState(readFilters);
  const [step, setStep] = useState(0);
  useEffect(() => writeFilters(saved), [saved]);
  // A remembered agent that has since left the crew would hide every run behind a chip
  // that is no longer drawn.
  const gone = saved.agent !== null && agents.length > 0 && !agents.some((a) => a.id === saved.agent);
  const filters = gone ? { ...saved, agent: null } : saved;

  const limit = HISTORY_STEPS[step];
  const history = useRunHistory({ agentId: filters.agent, limit });
  const byAgent = filterRuns(streamed, { ...NO_FILTERS, agent: filters.agent });
  // Still-going runs belong to the live list above, whichever copy says so.
  const loaded = mergeRuns(history.runs, byAgent).filter((run) => isSettled(run.status));
  const shown = filterRuns(loaded, filters);
  const narrowed = filters.agent !== null || filters.status !== null || filters.source !== null;
  // A full page means there may be more behind it; a short one was everything there is.
  const more = step < HISTORY_STEPS.length - 1 && history.runs.length >= limit;

  const change = (next: RunFilters) => {
    // Another agent is another history, read again from its newest page.
    if (next.agent !== filters.agent) setStep(0);
    setFilters(next);
  };

  return (
    <div className="run-log" data-testid="run-log">
      {(loaded.length > 0 || narrowed) && (
        <ActivityFilters
          filters={filters}
          agents={agents}
          sources={sourceKinds(loaded, filters.source)}
          onChange={change}
        />
      )}
      {runGroups(shown).map((group) => (
        <RunGroupCard
          key={group.run.id}
          group={group}
          agentName={agentName}
          onOpenConversation={onOpenConversation}
          onOpenRun={onOpenRun}
        />
      ))}
      {history.failed ? (
        <EmptyState
          says={vi.runFilters.failed}
          action={{ label: vi.runFilters.retry, onClick: history.reload }}
        />
      ) : shown.length > 0 ? null : history.loading && narrowed ? (
        <p className="muted" role="status">
          {vi.runFilters.loading}
        </p>
      ) : narrowed ? (
        <EmptyState
          says={vi.runFilters.none}
          action={{ label: vi.runFilters.clear, onClick: () => change(NO_FILTERS) }}
        />
      ) : (
        // Unfiltered, the stream already holds the newest crew-wide page, so an empty one
        // is an empty history and not one still loading. Nothing has run because nothing
        // has been asked yet, so the way out of this screen is the answer.
        <EmptyState
          icon="steps"
          says={vi.noRuns}
          action={{ label: vi.noRunsAction, onClick: onBackToChat }}
        />
      )}
      {more && !history.failed && (
        <button
          type="button"
          className="run-log-more"
          disabled={history.loading}
          onClick={() => setStep((s) => Math.min(s + 1, HISTORY_STEPS.length - 1))}
        >
          {vi.runFilters.more}
        </button>
      )}
    </div>
  );
}
