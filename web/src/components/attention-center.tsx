import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatClock } from "./run-timeline";

interface Props {
  runs: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
}

function label(run: RunInfo, agent: string): string {
  if (run.status === "awaiting_approval") return vi.attentionAwaiting(agent);
  if (run.status === "error") return vi.attentionFailed(agent);
  return vi.attentionHalted(agent);
}

/** Approvals waiting anywhere plus runs that ended badly, one click from their conversation. */
export function AttentionCenter({ runs, agentName, onOpenConversation }: Props) {
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
