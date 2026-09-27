// The parts of the costs page that answer "is the prompt cache working?": the share of
// each prompt the provider served from its cache, today, over the week, per model and per
// agent. The crew runs on a route where that share decides the bill, so a persona edit
// that breaks caching shows here as a share that falls.
import type { AgentCacheTotals, DayUsage, UsageTotals } from "../api/types";
import { vi } from "../i18n/vi";
import { cacheShare, compactNumber, dayWindows } from "../lib/format-usage";
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

interface AgentCacheProps {
  /** The server's totals per agent id. */
  cache: Record<string, AgentCacheTotals>;
  /** Calls on the same runs that reported a prompt but no cache figure. */
  uncounted: number;
  /** The runs they are counted over, which are the spend by agent's. */
  covers: string;
  agentName: (id: string) => string;
}

/**
 * Prompt tokens and the cached part per agent, biggest prompt first, over the same recent
 * runs as the spend by agent beside it.
 *
 * The server adds them up from the runs' model steps along with the rest of the stats.
 * Added up here, the page downloaded the whole window of runs, steps and all, on every
 * visit, for two sums per agent.
 */
export function AgentCacheTable({ cache, uncounted, covers, agentName }: AgentCacheProps) {
  const rows = Object.entries(cache).sort(([, a], [, b]) => b.prompt_tokens - a.prompt_tokens);
  return (
    <section className="metric-card">
      <CardTitle title={vi.costCacheByAgent} covers={covers} />
      {rows.length === 0 ? (
        // Calls that reported their tokens but not the cached part leave no row either, and
        // "no call reported its tokens" would contradict the tokens on the rest of the page.
        <p className="muted">{uncounted > 0 ? vi.costNoCacheFigure : vi.costNoTokens}</p>
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
            {rows.map(([agentId, totals]) => (
              <tr key={agentId}>
                <td>{agentName(agentId)}</td>
                <td>{compactNumber(totals.prompt_tokens)}</td>
                <td>
                  <CacheCell cached={totals.cached_tokens} prompt={totals.prompt_tokens} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
