// The parts of the costs page that answer "is the prompt cache working?": the share of
// each prompt the provider served from its cache, today, over the week, per model and per
// agent. The crew runs on a route where that share decides the bill, so a persona edit
// that breaks caching shows here as a share that falls.
import type { DayUsage, RunInfo, UsageTotals } from "../api/types";
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
  const share = cacheShare(usage.cached_tokens, usage.prompt_tokens);
  const calls = vi.costCalls(usage.calls);
  return share === null ? calls : `${calls} · ${vi.cacheShare(share)}`;
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

/**
 * Prompt tokens and the cached part per agent, over the runs this page holds.
 *
 * The server's totals are per model and per day, not per agent, so this one is added up
 * here from the runs' own model steps, and its title says how many runs that is.
 */
export function AgentCacheTable({ runs, agentName }: { runs: RunInfo[]; agentName: (id: string) => string }) {
  const rows = cacheByAgent(runs);
  return (
    <section className="metric-card">
      <CardTitle title={vi.costCacheByAgent} covers={vi.costWindowRecent(runs.length)} />
      {rows.length === 0 ? (
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
