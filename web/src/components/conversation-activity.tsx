import { useEffect, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runGroups } from "../state/activity-reducer";
import { isSettled, stepProgress } from "../lib/run-progress";
import { ApprovalHistory } from "./approval-history";
import { ConversationActivitySummary } from "./conversation-activity-summary";
import { RunProgressHeader } from "./run-progress-header";
import { RunGroupCard, formatClock } from "./run-timeline";

// Namespaced to this strip: a bare "activity.expanded" would collide with anything else
// that later wants to remember an activity view's open state.
const EXPANDED_KEY = "conversation-activity.expanded";

interface Props {
  /** This conversation's runs and those of the work it delegated, newest first. */
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
  runs,
  conversationId,
  spentUsd,
  capUsd,
  agentName,
  onOpenConversation,
  collapseSignal = 0,
  docked = false,
}: Props) {
  const [expanded, setExpanded] = useState(readExpanded);

  // Skipped on the first render: the strip opens in whatever state was remembered, and
  // an effect that ran on mount would slam it shut before the person touched anything.
  const firstSignal = useRef(collapseSignal);
  useEffect(() => {
    if (collapseSignal !== firstSignal.current) setExpanded(false);
  }, [collapseSignal]);

  useEffect(() => {
    // The column is open by design, not by choice; it must not overwrite the strip's memory.
    if (docked) return;
    try {
      window.localStorage.setItem(EXPANDED_KEY, expanded ? "1" : "0");
    } catch {
      // A browser that refuses storage still gets the strip; it just forgets the choice.
    }
  }, [expanded, docked]);

  if (runs.length === 0 && !docked) return null;

  const live = runs.filter((r) => !isSettled(r.status));
  const recent = runs.filter((r) => isSettled(r.status));
  // The newest live run is the turn being waited on; an older one left open is not
  // what the person is watching.
  const current = live[0] ?? null;

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
    <span className="muted">{vi.noRuns}</span>
  );

  const body = (
    <div className="conversation-activity-body">
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
        refreshKey={recent.length}
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
        <button
          type="button"
          className="ghost"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? vi.conversationActivity.collapse : vi.conversationActivity.expand}
        </button>
      </div>
      {expanded && body}
    </section>
  );
}

/** Remembering the choice is a convenience; a browser that refuses storage collapses. */
function readExpanded(): boolean {
  try {
    return window.localStorage.getItem(EXPANDED_KEY) === "1";
  } catch {
    return false;
  }
}
