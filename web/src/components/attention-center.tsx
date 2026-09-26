import { useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runSummaryText } from "../lib/run-summary";
import { markSeen } from "../lib/seen-runs";
import { AttentionRow } from "./attention-row";
import { formatClock } from "./run-timeline";
import { Icon, type IconName } from "./ui/icon";

interface Props {
  runs: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Names the run that handed out this work, when it is a delegated one. */
  parentTitle?: (run: RunInfo) => string | null;
  /** Waiting rows carry their request in place, so it is settled without leaving. */
  inline?: boolean;
  /** Reads the activity list again after a row changed something on the server. */
  onReload?: () => void;
  /** Requests waiting in another section, so this card never says there is nothing. */
  waitingElsewhere?: number;
  onOpenWaiting?: () => void;
}

/** A run pauses for two unrelated reasons, and only one of them is a permission request.
 *  The open question step is what tells them apart: a tool approval never writes one. */
function isAsking(run: RunInfo): boolean {
  return run.steps.some((step) => step.kind === "question" && step.duration_ms === null);
}

function label(run: RunInfo, agent: string): string {
  if (run.status === "awaiting_approval") {
    return isAsking(run) ? vi.attentionAsking(agent) : vi.attentionAwaiting(agent);
  }
  if (run.status === "error") return vi.attentionFailed(agent);
  return vi.attentionHalted(agent);
}

/** The shape of the ask, so a question, a permission and a failure differ before they are read. */
function icon(run: RunInfo): IconName {
  if (run.status === "awaiting_approval") return isAsking(run) ? "help" : "approvals";
  return "alert";
}

const noop = () => undefined;

/** Approvals waiting anywhere plus runs that ended badly, one click from their conversation. */
export function AttentionCenter(props: Props) {
  const { runs, agentName, onOpenConversation, parentTitle, inline = false } = props;
  const waitingElsewhere = props.waitingElsewhere ?? 0;
  // Rows settled from here leave at once, before the list is read again.
  const [settled, setSettled] = useState<string[]>([]);
  const shown = runs.filter((run) => !settled.includes(run.id));
  const calm = shown.length === 0 && waitingElsewhere === 0;

  const head = (run: RunInfo, preview: boolean) => {
    const parent = parentTitle?.(run);
    return (
      <>
        <span className="attention-icon">
          <Icon name={icon(run)} />
        </span>
        <span className="attention-text">
          <span className="attention-title">
            {label(run, agentName(run.agent_id))}
            <span className="muted tabular"> · {formatClock(run.started_at)}</span>
          </span>
          {parent && (
            <span className="attention-child" data-testid="attention-child">
              {vi.delegateChildOf.replace("{parent}", parent)}
            </span>
          )}
          {preview && run.summary && <span className="run-preview muted">{runSummaryText(run)}</span>}
        </span>
        <span className="attention-actions">
          {run.conversation_id && (
            <button
              type="button"
              className="attention-open"
              onClick={() => onOpenConversation(run.conversation_id as string)}
            >
              {vi.openConversation}
              <Icon name="arrow-right" />
            </button>
          )}
          {/* A failure is read, not decided: saying so is the only thing left to do with it. */}
          {run.status !== "awaiting_approval" && (
            <button
              type="button"
              className="ghost attention-seen"
              aria-label={vi.attentionSeenLabel(label(run, agentName(run.agent_id)))}
              onClick={() => markSeen(run.id)}
            >
              <Icon name="check" />
              {vi.attentionSeen}
            </button>
          )}
        </span>
      </>
    );
  };

  return (
    // Amber only while something is waiting on a person. A card that stays amber on an
    // empty list teaches the eye to skip it, which is the one thing it must not do.
    <section className={`attention${calm ? " calm" : ""}`} aria-label={vi.attention} data-testid="attention">
      <h3>{vi.attention}</h3>
      {calm && (
        <p className="attention-calm">
          <Icon name="check" />
          {vi.attentionEmpty}
        </p>
      )}
      {shown.length > 0 && (
        <ul className="attention-list">
          {shown.map((run) =>
            inline && run.status === "awaiting_approval" && run.conversation_id ? (
              <AttentionRow
                key={run.id}
                run={run}
                conversationId={run.conversation_id}
                onReload={props.onReload ?? noop}
                onSettled={() => setSettled((ids) => [...ids, run.id])}
              >
                {head(run, false)}
              </AttentionRow>
            ) : (
              <li key={run.id} className={run.status}>
                {head(run, true)}
              </li>
            ),
          )}
        </ul>
      )}
      {waitingElsewhere > 0 && (
        <button type="button" className="attention-elsewhere" onClick={props.onOpenWaiting}>
          {vi.attentionWaitingElsewhere(waitingElsewhere)}
          <Icon name="arrow-right" />
        </button>
      )}
    </section>
  );
}
