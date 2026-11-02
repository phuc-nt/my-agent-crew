import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { EmptyState } from "./empty-state";
import { InboxReport } from "./inbox-report";

interface Props {
  results: RunInfo[];
  /** What each result's run sent to the chat, by run id. */
  reports: Map<string, string>;
  fresh: Set<string>;
  agentName: (id: string) => string;
  /** Opens the run's conversation, where the report is answered. */
  onOpen: (run: RunInfo) => void;
}

/**
 * What the jobs reported, newest first, each read whole where it is listed: the feed the
 * chat app gives, on a page the phone already has open.
 */
export function InboxResults({ results, reports, fresh, agentName, onOpen }: Props) {
  return (
    <section className="inbox-results" aria-label={vi.inbox.results}>
      <h3>{vi.inbox.results}</h3>
      {results.length === 0 ? (
        <EmptyState icon="clock" says={vi.inbox.noResults} />
      ) : (
        <ul>
          {results.map((run) => (
            <li key={run.id}>
              <InboxReport
                run={run}
                text={reports.get(run.id) ?? run.summary}
                agent={agentName(run.agent_id)}
                fresh={fresh.has(run.id)}
                onOpen={onOpen}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
