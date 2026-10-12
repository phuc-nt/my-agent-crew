import type { ReactNode } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runGroups } from "../state/activity-reducer";
import { readText } from "../lib/local-store";
import { stepProgress, waitingKey } from "../lib/run-progress";
import type { RunHistory } from "../hooks/use-run-history";
import { ApprovalHistory } from "./approval-history";
import { ConversationActivitySummary } from "./conversation-activity-summary";
import { RunProgressHeader } from "./run-progress-header";
import { RunGroupCard, formatClock } from "./run-timeline";

// Namespaced to this strip: a bare "activity.expanded" would collide with anything else
// that later wants to remember an activity view's open state.
export const EXPANDED_KEY = "conversation-activity.expanded";

/** Remembering the choice is a convenience; a browser that refuses storage collapses. */
export function readExpanded(): boolean {
  return readText(EXPANDED_KEY) === "1";
}

export function activityStatus({
  current,
  recent,
  trouble,
  history,
}: {
  current: RunInfo | null;
  recent: RunInfo[];
  trouble: ReactNode;
  history: RunHistory;
}) {
  return current ? (
    <RunProgressHeader run={current} />
  ) : recent.length > 0 ? (
    // With nothing live the bar still has to answer "what happened last?" — a bare
    // label with no run behind it reads like a missing feature.
    <span className="muted">
      {vi.conversationActivity.lastRun}: {vi.runStatus[recent[0].status]} ·{" "}
      {formatClock(recent[0].started_at)} · {vi.runSteps(stepProgress(recent[0]).total)}
    </span>
  ) : (
    // "Never ran" only once the store has said so; until then it cannot tell. Focusable
    // from code alone, for a retry that finds no run and has nowhere else to leave the focus.
    trouble || (
      <span className="muted" role="status" tabIndex={-1}>
        {history.loading ? vi.runFilters.loading : vi.noRuns}
      </span>
    )
  );
}

export function activityBody({
  trouble,
  runs,
  conversationId,
  spentUsd,
  capUsd,
  live,
  recent,
  agentName,
  onOpenConversation,
  settled,
  streamed,
}: {
  trouble: ReactNode;
  runs: RunInfo[];
  conversationId: string;
  spentUsd: number;
  capUsd?: number;
  live: RunInfo[];
  recent: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  settled: number;
  streamed: RunInfo[];
}) {
  return (
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
        // The streamed runs, not the merged list: the stored runs arriving is not a run
        // settling, and would ask for the approvals twice on every open. A request decided
        // while its turn goes on to wait again settles no run, so the wait is part of it.
        refreshKey={`${settled}|${waitingKey(streamed)}`}
        conversationId={conversationId}
      />
    </div>
  );
}

export function activityPill(current: RunInfo | null) {
  // The column's headline state, in the same pill shape as the chat header's.
  const waiting = current?.status === "awaiting_approval";
  return (
    <span className={`status-pill${current ? (waiting ? " warn" : " ok") : ""}`}>
      <span className="pill-dot" aria-hidden="true" />
      {current
        ? waiting
          ? vi.conversationActivity.waiting
          : vi.conversationActivity.live
        : vi.conversationActivity.idle}
    </span>
  );
}
