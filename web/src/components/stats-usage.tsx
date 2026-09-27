// The parts of the costs page that answer "is the prompt cache working?": the share of
// each prompt the provider served from its cache, today, over the week, per model and per
// agent. The crew runs on a route where that share decides the bill, so a persona edit
// that breaks caching shows here as a share that falls.
import type { DayUsage, RunInfo, UsageTotals } from "../api/types";
import { mergeRuns, useRunHistory } from "../hooks/use-run-history";
import { vi } from "../i18n/vi";
import { cacheByAgent, cacheShare, compactNumber, dayWindows } from "../lib/format-usage";
import { formatUsd } from "./budget-indicator";

/**
 * A card title that says what its figures are counted over. The costs page mixes the
 * last few hundred runs with the whole message log, and a number without its window
 * invites comparing the two.
 */
export function CardTitle({ title, covers }: { title: string; covers: string }) {
  return (
    <h3 className="metric-card-title">
      {title} <span className="stat-window">· {covers}</span>
    </h3>
  );
}

/** "12k · 66%": the cached tokens and their share of the prompt; a dash where unreported. */
export function CacheCell({ cached, prompt }: { cached: number | null | undefined; prompt: number }) {
  // A server from before the cache was counted leaves the field out altogether.
  if (cached == null) return <>—</>;
  const share = cacheShare(cached, prompt);
  return (
    <>
      {compactNumber(cached)}
      {share !== null && <span className="stat-share"> · {share}%</span>}
    </>
  );
}

function periodDetail(usage: UsageTotals): string {
  const parts = [vi.costCalls(usage.calls)];
  const share = cacheShare(usage.cached_tokens, usage.prompt_tokens);
  if (share !== null) parts.push(vi.cacheShare(share));
  // Flagged as the day rows flag it: without it the tile passes for the whole spend.
  if (usage.unknown_cost_calls > 0) parts.push(`? ${usage.unknown_cost_calls}`);
  return parts.join(" · ");
}

/** Today and the week, on the viewer's calendar, from the message log's day buckets. */
export function PeriodTiles({ days }: { days: DayUsage[] }) {
  const { today, week } = dayWindows(days);
  const tiles: [string, UsageTotals][] = [
    [vi.costToday, today],
    [vi.costWeek, week],
  ];
  return (
    <dl className="stat-totals" data-testid="stat-periods">
      {tiles.map(([label, usage]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{formatUsd(usage.cost_usd)}</dd>
          <dd className="stat-tile-detail">{periodDetail(usage)}</dd>
        </div>
      ))}
    </dl>
  );
}

// The runs the server's spend by agent is counted over (`STATS_RUNS` in routes_activity.py).
const STATS_RUNS = 500;

interface AgentCacheProps {
  /** Runs streamed since the page opened, laid over the stored ones for their latest steps. */
  streamed: RunInfo[];
  agentName: (id: string) => string;
}

/**
 * Prompt tokens and the cached part per agent, over the same recent runs as the spend by
 * agent beside it.
 *
 * The server's totals are per model and per day, not per agent, so this one is added up
 * here from the runs' own model steps, and its title says how many runs that is. The
 * page's live list is fifty runs of whoever was busiest; counted over those, a quiet
 * agent had spend and no cache row, so the stored window is asked for once.
 */
export function AgentCacheTable({ streamed, agentName }: AgentCacheProps) {
  const history = useRunHistory({ limit: STATS_RUNS });
  const runs = mergeRuns(history.runs, streamed).slice(0, STATS_RUNS);
  const rows = cacheByAgent(runs);
  return (
    <section className="metric-card">
      <CardTitle title={vi.costCacheByAgent} covers={vi.costWindowRecent(runs.length)} />
      {history.failed ? (
        <p className="muted">
          {vi.runFilters.failed}{" "}
          <button type="button" className="link-button history-retry" onClick={history.reload}>
            {vi.runFilters.retry}
          </button>
        </p>
      ) : history.loading ? (
        <p className="muted" role="status">
          {vi.runFilters.loading}
        </p>
      ) : rows.length === 0 ? (
        <p className="muted">{vi.costNoTokens}</p>
      ) : (
        <table className="stat-table" data-testid="stat-agent-cache">
          <thead>
            <tr>
              <th>{vi.agent}</th>
              <th>{vi.costPromptTokens}</th>
              <th>{vi.cacheHeader}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.agentId}>
                <td>{agentName(row.agentId)}</td>
                <td>{compactNumber(row.promptTokens)}</td>
                <td>
                  <CacheCell cached={row.cachedTokens} prompt={row.promptTokens} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
