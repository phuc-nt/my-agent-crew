import { useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { framePaths } from "../lib/desktop-frame";
import { isSettled, stepProgress } from "../lib/run-progress";
import { runRows } from "../lib/run-rows";
import { runSummaryText } from "../lib/run-summary";
import type { RunGroup } from "../state/activity-reducer";
import { formatUsd } from "./budget-indicator";
import { RunProgressHeader } from "./run-progress-header";
import { StepRow } from "./run-step-row";

export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

interface Props {
  run: RunInfo;
  agentName: string;
  expanded?: boolean;
  onOpenConversation?: (conversationId: string) => void;
  /** Opens this run on its own page; absent means the link is hidden, as it is there. */
  onOpenRun?: (runId: string) => void;
}

/** One run as a card: who, what, status, cost, then the step timeline when expanded. */
export function RunCard({ run, agentName, expanded = false, onOpenConversation, onOpenRun }: Props) {
  const [open, setOpen] = useState(expanded);
  const live = !isSettled(run.status);
  // The desktop pictures the run's screenshots saved, for a step that says the screen is unchanged.
  const frames = framePaths(run.steps.flatMap((step) => (step.kind === "tool" && step.ok === true ? [step] : [])));
  return (
    <article className={`run-card ${run.status}`} data-testid="run-card" data-status={run.status}>
      <button type="button" className="run-summary" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`status-dot ${run.status}`} aria-hidden="true" />
        <span className="run-main">
          <span className="run-title">
            <strong>{agentName}</strong> · {run.title || vi.runSource(run.source)}
          </span>
          <span className="run-meta muted">
            {/* The same total the progress header counts. Using the raw step count here
                would let the card say "3 bước" while the bar under it reads "2/2", since
                notes are commentary and not steps of the work. */}
            {vi.runStatus[run.status]} · {formatClock(run.started_at)} · {vi.runSteps(stepProgress(run).total)} ·{" "}
            {formatUsd(run.spent_usd)}
            {run.unknown_cost_calls > 0 && ` · ? ${run.unknown_cost_calls}`}
            {/* Unsettled is not the same as working: a run waiting on the person says
                "chờ duyệt" just before this, and a pill saying it runs would contradict it. */}
            {run.status === "running" && <span className="badge live"> {vi.liveNow}</span>}
          </span>
          {run.summary && <span className="run-preview muted">{runSummaryText(run)}</span>}
        </span>
      </button>
      {open && (
        <div className="run-body">
          {/* The live header sits above the steps, so the answer to "what is it
              doing" is in one fixed place rather than at the bottom of a list
              that grows while you read it. */}
          {(live || run.steps.length > 0) && <RunProgressHeader run={run} />}
          {run.steps.length === 0 ? (
            <p className="muted">{vi.thinking}</p>
          ) : (
            <ol className="run-steps">
              {runRows(run).map((row) => (
                <StepRow key={row.key} row={row} agentId={run.agent_id} frames={frames} onOpenConversation={onOpenConversation} />
              ))}
            </ol>
          )}
          <div className="run-links">
            {run.conversation_id && onOpenConversation && (
              <button
                type="button"
                className="link-button"
                onClick={() => onOpenConversation(run.conversation_id as string)}
              >
                {vi.openConversation}
              </button>
            )}
            {onOpenRun && (
              <button type="button" className="link-button" onClick={() => onOpenRun(run.id)}>
                {vi.replay.openLink}
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

/**
 * A run with the work it handed out shown underneath it.
 *
 * One level only: a delegated agent cannot delegate on, so a child never has children.
 * The children stay visible after the parent finishes, since that is usually the moment
 * someone wants to see what each of them actually did.
 */
export function RunGroupCard({
  group,
  agentName,
  expanded = false,
  onOpenConversation,
  onOpenRun,
}: {
  group: RunGroup;
  agentName: (id: string) => string;
  expanded?: boolean;
  onOpenConversation?: (conversationId: string) => void;
  onOpenRun?: (runId: string) => void;
}) {
  return (
    <div className="run-group" data-testid="run-group">
      <RunCard
        run={group.run}
        agentName={agentName(group.run.agent_id)}
        expanded={expanded}
        onOpenConversation={onOpenConversation}
        onOpenRun={onOpenRun}
      />
      {group.children.length > 0 && (
        <div className="run-children" data-testid="run-children">
          {group.children.map((child) => (
            <RunCard
              key={child.id}
              run={child}
              agentName={agentName(child.agent_id)}
              onOpenConversation={onOpenConversation}
              onOpenRun={onOpenRun}
            />
          ))}
        </div>
      )}
    </div>
  );
}
