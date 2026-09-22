import { useEffect, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { parentConversationId, runGroups } from "../state/activity-reducer";
import { isSettled } from "../lib/run-progress";
import { ApprovalHistory } from "./approval-history";
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
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Bumped from outside to collapse the strip, which is what Escape does. A counter
   * rather than a boolean: the same request has to work twice in a row. */
  collapseSignal?: number;
}

/**
 * The activity strip inside the chat frame: what this conversation is doing, and nothing
 * about any other one.
 *
 * Collapsed it is a single progress line, and a conversation that has never run shows
 * nothing at all — an empty panel next to an empty thread is just furniture.
 */
export function ConversationActivity({
  runs,
  conversationId,
  spentUsd,
  agentName,
  onOpenConversation,
  collapseSignal = 0,
}: Props) {
  const [expanded, setExpanded] = useState(readExpanded);

  // Skipped on the first render: the strip opens in whatever state was remembered, and
  // an effect that ran on mount would slam it shut before the person touched anything.
  const firstSignal = useRef(collapseSignal);
  useEffect(() => {
    if (collapseSignal !== firstSignal.current) setExpanded(false);
  }, [collapseSignal]);

  useEffect(() => {
    try {
      window.localStorage.setItem(EXPANDED_KEY, expanded ? "1" : "0");
    } catch {
      // A browser that refuses storage still gets the strip; it just forgets the choice.
    }
  }, [expanded]);

  if (runs.length === 0) return null;

  const live = runs.filter((r) => !isSettled(r.status));
  const recent = runs.filter((r) => isSettled(r.status));
  // The newest live run is the turn being waited on; an older one left open is not
  // what the person is watching.
  const current = live[0] ?? null;

  return (
    <section
      className={`conversation-activity${expanded ? " expanded" : ""}`}
      aria-label={vi.conversationActivity.label}
      data-testid="conversation-activity"
    >
      <div className="conversation-activity-bar">
        {current ? (
          <RunProgressHeader run={current} />
        ) : (
          // Collapsed with nothing live, the bar still has to answer "what happened
          // last?" — a bare label with no run behind it reads like a missing feature.
          <span className="muted">
            {vi.conversationActivity.lastRun}: {vi.runStatus[recent[0].status]} ·{" "}
            {formatClock(recent[0].started_at)} · {vi.runSteps(recent[0].steps.length)}
          </span>
        )}
        <button
          type="button"
          className="ghost"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? vi.conversationActivity.collapse : vi.conversationActivity.expand}
        </button>
      </div>
      {expanded && (
        <div className="conversation-activity-body">
          {runGroups(live).map((group) => (
            <RunGroupCard
              key={group.run.id}
              group={group}
              agentName={agentName}
              expanded
              onOpenConversation={onOpenConversation}
            />
          ))}
          {runGroups(recent).map((group) => (
            <RunGroupCard
              key={group.run.id}
              group={group}
              agentName={agentName}
              onOpenConversation={onOpenConversation}
            />
          ))}
          <CostRow runs={runs} conversationId={conversationId} spent={spentUsd} />
          <h4>{vi.conversationActivity.approvals}</h4>
          <ApprovalHistory
            agentName={agentName}
            onOpenConversation={onOpenConversation}
            refreshKey={recent.length}
            conversationId={conversationId}
          />
        </div>
      )}
    </section>
  );
}

/**
 * What this conversation has cost so far: the spend, the work done and the models behind it.
 *
 * The spend comes from the conversation itself, never from adding up its runs. A run's
 * `spent_usd` arrives as the conversation's running total, not that run's own cost, and a
 * delegated child's spend is already folded into the parent — so summing would count the
 * same money two ways over. Steps and models really are per-run, so those are summed.
 * Every figure is already in hand, so the row costs no request.
 */
function CostRow({
  runs,
  conversationId,
  spent,
}: {
  runs: RunInfo[];
  conversationId: string;
  spent: number;
}) {
  const steps = runs.reduce((total, r) => total + r.steps.length, 0);
  const delegated = runs.filter((r) => parentConversationId(r) === conversationId).length;
  const models = [
    ...new Set(
      runs.flatMap((r) =>
        r.steps.flatMap((s) => (s.kind === "model" && s.model ? [s.model] : [])),
      ),
    ),
  ];

  return (
    <dl className="conversation-cost" data-testid="conversation-cost">
      <div>
        <dt>{vi.costs}</dt>
        <dd>{vi.conversationActivity.spent(spent)}</dd>
      </div>
      <div>
        <dt>{vi.activity}</dt>
        <dd>
          {vi.conversationActivity.steps(steps)}
          {delegated > 0 && ` · ${vi.conversationActivity.delegated(delegated)}`}
        </dd>
      </div>
      {models.length > 0 && (
        <div>
          <dt>{vi.costByModel}</dt>
          <dd>{models.join(", ")}</dd>
        </div>
      )}
    </dl>
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
