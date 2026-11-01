import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { dayClock } from "../lib/relative-time";
import { EmptyState } from "./empty-state";
import { AgentAvatar } from "./ui/agent-avatar";

interface Props {
  results: RunInfo[];
  fresh: Set<string>;
  agentName: (id: string) => string;
  /** Opens the run where it can be read whole: its conversation, or its own page. */
  onOpen: (run: RunInfo) => void;
}

/**
 * What the jobs reported, one card each, newest first: the job, who ran it, when, and the
 * start of what it said. The card is one button, as a mail in a list is — a thumb opens
 * the result, and the result is read in its conversation, where it can be answered.
 */
export function InboxResults({ results, fresh, agentName, onOpen }: Props) {
  return (
    <section className="inbox-results" aria-label={vi.inbox.results}>
      <h3>{vi.inbox.results}</h3>
      {results.length === 0 ? (
        <EmptyState icon="clock" says={vi.inbox.noResults} />
      ) : (
        <ul>
          {results.map((run) => {
            const agent = agentName(run.agent_id);
            const at = dayClock(run.finished_at ?? run.started_at);
            const isFresh = fresh.has(run.id);
            return (
              <li key={run.id}>
                <button
                  type="button"
                  className={`inbox-result${isFresh ? " fresh" : ""}`}
                  aria-label={vi.inbox.resultLabel(run.title || agent, agent, at)}
                  onClick={() => onOpen(run)}
                >
                  <AgentAvatar id={run.agent_id} name={agent} size="sm" />
                  <span className="inbox-result-text">
                    <span className="inbox-result-head">
                      <span className="inbox-result-title">{run.title || agent}</span>
                      {isFresh && <span className="badge live inbox-unread">{vi.inbox.unread}</span>}
                      <span className="muted tabular inbox-result-at">{at}</span>
                    </span>
                    <span className="muted inbox-result-agent">{agent}</span>
                    <span className="inbox-result-summary">{run.summary}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
