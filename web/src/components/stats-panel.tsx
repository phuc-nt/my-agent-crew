import type { DayUsage, ModelUsage, RunInfo, StatsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { cacheShare, compactNumber } from "../lib/format-usage";
import { EmptyState } from "./empty-state";
import { formatUsd } from "./budget-indicator";
import { AgentCacheTable, CacheCell, CardTitle, PeriodTiles } from "./stats-usage";

interface Props {
  stats: StatsInfo | null;
  agentName: (id: string) => string;
  /** The runs the page holds, for the per-agent cache the server does not total. */
  runs?: RunInfo[];
}

interface BreakdownProps {
  title: string;
  covers: string;
  rows: Record<string, number>;
  name?: (k: string) => string;
}

function Breakdown({ title, covers, rows, name }: BreakdownProps) {
  const entries = Object.entries(rows).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const max = Math.max(...entries.map(([, v]) => v), 0.000001);
  return (
    <section className="metric-card">
      <CardTitle title={title} covers={covers} />
      <ul className="stat-bars">
        {entries.map(([key, value]) => (
          <li key={key}>
            <span className="stat-key">{name ? name(key) : key}</span>
            <span className="stat-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(2, (value / max) * 100)}%` }} />
            </span>
            <span className="stat-value">{formatUsd(value)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "1.2M vào / 80k ra", written as short as the cache figure it is read against. */
function tokens(u: { prompt_tokens: number; completion_tokens: number }): string {
  return vi.tokens(compactNumber(u.prompt_tokens), compactNumber(u.completion_tokens));
}

function dayDetail(d: DayUsage): string {
  const parts = [vi.costCalls(d.calls), tokens(d)];
  const share = cacheShare(d.cached_tokens, d.prompt_tokens);
  if (share !== null) parts.push(vi.cacheShare(share));
  if (d.unknown_cost_calls > 0) parts.push(`? ${d.unknown_cost_calls}`);
  return parts.join(" · ");
}

/** The last days side by side: a cost bar plus the calls, tokens and cache behind it. */
function RecentDays({ days }: { days: DayUsage[] }) {
  if (days.length === 0) return null;
  const max = Math.max(...days.map((d) => d.cost_usd), 0.000001);
  return (
    <section className="metric-card">
      <h3 className="metric-card-title">{vi.costLastDays}</h3>
      <ul className="stat-bars stat-days" data-testid="stat-days">
        {days.map((d) => (
          <li key={d.day}>
            <span className="stat-key">{d.day}</span>
            <span className="stat-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(2, (d.cost_usd / max) * 100)}%` }} />
            </span>
            <span className="stat-value">{formatUsd(d.cost_usd)}</span>
            <span className="stat-detail muted">{dayDetail(d)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ModelTable({ models }: { models: ModelUsage[] }) {
  if (models.length === 0) return null;
  return (
    <section className="metric-card">
      <CardTitle title={vi.costModels} covers={vi.costWindowAll} />
      <table className="stat-table" data-testid="stat-models">
        <thead>
          <tr>
            <th>{vi.costByModel}</th>
            <th>{vi.costModelCalls}</th>
            <th>{vi.tokensHeader}</th>
            <th>{vi.cacheHeader}</th>
            <th>{vi.costTotal}</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.model}>
              <td>
                <code>{m.model}</code>
              </td>
              <td>{m.calls}</td>
              <td>{tokens(m)}</td>
              <td>
                <CacheCell cached={m.cached_tokens} prompt={m.prompt_tokens} />
              </td>
              <td>
                {formatUsd(m.cost_usd)}
                {m.unknown_cost_calls > 0 && <span className="badge warn"> ? {m.unknown_cost_calls}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/**
 * Honest cost dashboard: today and the week, the recent runs' totals and spend by agent,
 * the cache per agent, the recent days with tokens, and each model — each labelled with
 * what it is counted over, since the run window and the message log are not the same.
 */
export function StatsPanel({ stats, agentName, runs }: Props) {
  if (stats === null) return <p className="muted">{vi.loadFailed}</p>;
  if (stats.runs === 0) return <EmptyState icon="coins" says={vi.costEmpty} />;
  const recent = vi.costWindowRecent(stats.runs);
  return (
    <div className="stats" data-testid="stats">
      <PeriodTiles days={stats.days} />
      <p className="stat-caption">{recent}</p>
      <dl className="stat-totals" data-testid="stat-totals">
        <div>
          <dt>{vi.costTotal}</dt>
          <dd>{formatUsd(stats.spent_usd)}</dd>
        </div>
        <div>
          <dt>{vi.costRuns}</dt>
          <dd>{stats.runs}</dd>
        </div>
        <div>
          <dt>{vi.costModelCalls}</dt>
          <dd>{stats.model_calls}</dd>
        </div>
        {stats.unknown_cost_calls > 0 && (
          <div>
            <dt>{vi.stepCostUnknown}</dt>
            <dd className="badge warn">? {stats.unknown_cost_calls}</dd>
          </div>
        )}
      </dl>
      <Breakdown title={vi.costByAgent} covers={recent} rows={stats.by_agent} name={agentName} />
      {runs && <AgentCacheTable runs={runs} agentName={agentName} />}
      <RecentDays days={stats.days} />
      <ModelTable models={stats.models} />
    </div>
  );
}
