import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatClock } from "./run-timeline";

interface Props {
  runs: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Names the run that handed out this work, when it is a delegated one. */
  parentTitle?: (run: RunInfo) => string | null;
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

/** Says a run is work another conversation handed out, so the pause has a context. */
function childNote(run: RunInfo, parentTitle?: (run: RunInfo) => string | null): string | null {
  const parent = parentTitle?.(run);
  return parent ? vi.delegateChildOf.replace("{parent}", parent) : null;
}

/** Approvals waiting anywhere plus runs that ended badly, one click from their conversation. */
export function AttentionCenter({ runs, agentName, onOpenConversation, parentTitle }: Props) {
  return (
    <section className="attention" aria-label={vi.attention} data-testid="attention">
      <h3>{vi.attention}</h3>
      {runs.length === 0 ? (
        <p className="muted">{vi.attentionEmpty}</p>
      ) : (
        <ul className="attention-list">
          {runs.map((run) => (
            <li key={run.id} className={run.status}>
              <span className="attention-text">
                {label(run, agentName(run.agent_id))}
                <span className="muted"> · {formatClock(run.started_at)}</span>
                {childNote(run, parentTitle) && (
                  <span className="muted" data-testid="attention-child">
                    {" · "}
                    {childNote(run, parentTitle)}
                  </span>
                )}
                {run.summary && <span className="run-preview muted">{run.summary}</span>}
              </span>
              {run.conversation_id && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => onOpenConversation(run.conversation_id as string)}
                >
                  {vi.openConversation}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
