import { useEffect, useRef, useState } from "react";
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
  // Judged by the page on show, not the step just asked for: the button stays put while
  // the next page loads, so the focus of whoever pressed it has somewhere to stay.
  const ceiling = HISTORY_STEPS[HISTORY_STEPS.length - 1];
  const more =
    history.pageLimit > 0 && history.pageLimit < ceiling && history.runs.length >= history.pageLimit;
  const groups = runGroups(shown);
  // The step asked for is on its way until its page is the one on show, or has failed.
  const waiting = history.loading || (history.pageLimit < limit && !history.failed);

  // Where the runs a pressed "Xem thêm" asked for start, until that page settles.
  const firstNew = useRef<number | null>(null);
  const log = useRef<HTMLDivElement>(null);
  // The last page takes the button with it, and a failed one swaps it for a retry: the
  // focus of whoever pressed it would fall to the top of the page. It goes to the first
  // run that page brought instead, where reading carries on, or to the retry.
  useEffect(() => {
    const from = firstNew.current;
    if (from === null || waiting) return;
    firstNew.current = null;
    if (document.activeElement && document.activeElement !== document.body) return;
    const cards = log.current?.querySelectorAll<HTMLElement>(":scope > .run-group > .run-card > .run-summary");
    const card = history.failed ? undefined : cards?.[Math.min(from, cards.length - 1)];
    (card ?? log.current?.querySelector<HTMLElement>(":scope > .empty > button"))?.focus();
  });

  const change = (next: RunFilters) => {
    // Another agent is another history, read again from its newest page.
    if (next.agent !== filters.agent) setStep(0);
    setFilters(next);
  };

  return (
    <div className="run-log" data-testid="run-log" ref={log}>
      {(loaded.length > 0 || narrowed) && (
        <ActivityFilters
          filters={filters}
          agents={agents}
          sources={sourceKinds(loaded, filters.source)}
          onChange={change}
        />
      )}
      {groups.map((group) => (
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
          action={{ label: vi.retry, onClick: history.reload }}
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
        // aria-disabled rather than disabled: a browser moves the focus off a control
        // that becomes disabled, and that is the focus this button is here to keep.
        <button
          type="button"
          className="run-log-more"
          aria-disabled={history.loading}
          onClick={() => {
            if (history.loading) return;
            firstNew.current = groups.length;
            setStep((s) => Math.min(s + 1, HISTORY_STEPS.length - 1));
          }}
        >
          {history.loading ? vi.runFilters.loadingMore : vi.showMore}
        </button>
      )}
    </div>
  );
}
