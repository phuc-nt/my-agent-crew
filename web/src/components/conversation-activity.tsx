import { useEffect, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runGroups } from "../state/activity-reducer";
import { readText, writeText } from "../lib/local-store";
import { isSettled, stepProgress } from "../lib/run-progress";
import { mergeRuns, useRunHistory } from "../hooks/use-run-history";
import { ApprovalHistory } from "./approval-history";
import { ConversationActivitySummary } from "./conversation-activity-summary";
import { RunProgressHeader } from "./run-progress-header";
import { RunGroupCard, formatClock } from "./run-timeline";
import { Icon } from "./ui/icon";

// Namespaced to this strip: a bare "activity.expanded" would collide with anything else
// that later wants to remember an activity view's open state.
const EXPANDED_KEY = "conversation-activity.expanded";
// Far more turns than one conversation usually holds, and still one small request.
const HISTORY_LIMIT = 100;

interface Props {
  /** This conversation's runs and those of the work it delegated, as the live stream knows
   * them; the stored ones from before the page opened are fetched here and merged in. */
  runs: RunInfo[];
  /** The open conversation, so the approval history can be narrowed to it. */
  conversationId: string;
  /** The conversation's own running total, which already includes what it delegated. */
  spentUsd: number;
  /** The conversation's cap, for the bar under the spend; zero means no cap. */
  capUsd?: number;
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Bumped from outside to collapse the strip, which is what Escape does. A counter
   * rather than a boolean: the same request has to work twice in a row. */
  collapseSignal?: number;
  /** Rendered as the right-hand column of a wide screen: always open, with no toggle and
   * no remembered choice, and present even before the first run so the layout holds still. */
  docked?: boolean;
}

/**
 * This conversation's activity: what it is doing, and nothing about any other one.
 *
 * On a wide screen it is a column beside the chat that is always open. Below that it is a
 * strip under the thread: collapsed to a single progress line, and absent for a
 * conversation that has never run — an empty strip under an empty thread is just furniture.
 */
export function ConversationActivity({
  runs: streamed,
  conversationId,
  spentUsd,
  capUsd,
  agentName,
  onOpenConversation,
  collapseSignal = 0,
  docked = false,
}: Props) {
  const [expanded, setExpanded] = useState(readExpanded);
  // Asked again whenever one of its runs settles, since that is when the store holds the
  // whole of it — and a finished delegate is only known to the server's family query.
  const settled = streamed.filter((r) => isSettled(r.status)).length;
  const history = useRunHistory({ conversationId, limit: HISTORY_LIMIT, refreshKey: settled });
  const runs = mergeRuns(history.runs, streamed);

  // Skipped on the first render: the strip opens in whatever state was remembered, and
  // an effect that ran on mount would slam it shut before the person touched anything.
  const firstSignal = useRef(collapseSignal);
  useEffect(() => {
    if (collapseSignal !== firstSignal.current) setExpanded(false);
  }, [collapseSignal]);

  useEffect(() => {
    // The column is open by design, not by choice; it must not overwrite the strip's memory.
    if (docked) return;
    // A browser that refuses storage still gets the strip; it just forgets the choice.
    writeText(EXPANDED_KEY, expanded ? "1" : "0");
  }, [expanded, docked]);

  // Below the column, a strip that came up for every chat while its history loads would
  // flash under each new one, so it waits for the answer. Not for a failed one: hidden
  // then, it would pass for a conversation that never ran.
  if (runs.length === 0 && !docked && !history.failed) return null;

  const live = runs.filter((r) => !isSettled(r.status));
  const recent = runs.filter((r) => isSettled(r.status));
  // The newest live run is the turn being waited on; an older one left open is not
  // what the person is watching.
  const current = live[0] ?? null;

  // Stored runs that could not be read are said so, with a way to ask again.
  const trouble = history.failed && (
    <span className="muted">
      {vi.runFilters.failed}{" "}
      <button type="button" className="link-button history-retry" onClick={history.reload}>
        {vi.runFilters.retry}
      </button>
    </span>
  );

  const status = current ? (
    <RunProgressHeader run={current} />
  ) : recent.length > 0 ? (
    // With nothing live the bar still has to answer "what happened last?" — a bare
    // label with no run behind it reads like a missing feature.
    <span className="muted">
      {vi.conversationActivity.lastRun}: {vi.runStatus[recent[0].status]} ·{" "}
      {formatClock(recent[0].started_at)} · {vi.runSteps(stepProgress(recent[0]).total)}
    </span>
  ) : (
    // "Never ran" only once the store has said so; until then it cannot tell.
    trouble || (
      <span className="muted" role="status">
        {history.loading ? vi.runFilters.loading : vi.noRuns}
      </span>
    )
  );

  const body = (
    <div className="conversation-activity-body">
      {trouble}
      <ConversationActivitySummary
        runs={runs}
        conversationId={conversationId}
        spent={spentUsd}
        cap={capUsd}
      />
      {live.length > 0 && <h4>{vi.conversationActivity.live}</h4>}
      {runGroups(live).map((group) => (
        <RunGroupCard
          key={group.run.id}
          group={group}
          agentName={agentName}
          expanded
          onOpenConversation={onOpenConversation}
        />
      ))}
      {recent.length > 0 && <h4>{vi.recentRuns}</h4>}
      {runGroups(recent).map((group) => (
        <RunGroupCard
          key={group.run.id}
          group={group}
          agentName={agentName}
          onOpenConversation={onOpenConversation}
        />
      ))}
      <h4>{vi.conversationActivity.approvals}</h4>
      <ApprovalHistory
        agentName={agentName}
        onOpenConversation={onOpenConversation}
        // The streamed count, not the merged list's: the stored runs arriving is not a run
        // settling, and would ask for the approvals twice on every open.
        refreshKey={settled}
        conversationId={conversationId}
      />
    </div>
  );

  // The column's headline state, in the same pill shape as the chat header's.
  const waiting = current?.status === "awaiting_approval";
  const pill = (
    <span className={`status-pill${current ? (waiting ? " warn" : " ok") : ""}`}>
      <span className="pill-dot" aria-hidden="true" />
      {current
        ? waiting
          ? vi.conversationActivity.waiting
          : vi.conversationActivity.live
        : vi.conversationActivity.idle}
    </span>
  );

  if (docked) {
    return (
      <aside
        className="conversation-activity docked"
        aria-label={vi.conversationActivity.label}
        data-testid="conversation-activity"
      >
        <div className="conversation-activity-bar">
          <div className="conversation-activity-title">
            <h2>{vi.conversationActivity.title}</h2>
            {pill}
          </div>
          {status}
        </div>
        {runs.length > 0 && body}
      </aside>
    );
  }

  return (
    <section
      className={`conversation-activity${expanded ? " expanded" : ""}`}
      aria-label={vi.conversationActivity.label}
      data-testid="conversation-activity"
    >
      <div className="conversation-activity-bar">
        {status}
        {/* With no run known there is nothing to open, only the failure to read them. */}
        {runs.length > 0 && (
          <button
            type="button"
            className="ghost activity-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? vi.conversationActivity.collapse : vi.conversationActivity.expand}
            <Icon name="chevron-down" />
          </button>
        )}
      </div>
      {expanded && runs.length > 0 && body}
    </section>
  );
}

/** Remembering the choice is a convenience; a browser that refuses storage collapses. */
function readExpanded(): boolean {
  return readText(EXPANDED_KEY) === "1";
}
