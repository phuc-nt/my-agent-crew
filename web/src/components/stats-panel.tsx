import type { ReactNode } from "react";
import type { DayUsage, PurposeUsage, StatsInfo, UsageTotals } from "../api/types";
import { vi } from "../i18n/vi";
import { cacheShare, compactNumber } from "../lib/format-usage";
import { EmptyState } from "./empty-state";
import { formatUsd } from "./budget-indicator";
import { AgentCacheTable, CacheCell, CardTitle, PeriodTiles } from "./stats-usage";

interface Props {
  stats: StatsInfo | null;
  agentName: (id: string) => string;
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

interface LedgerProps<T extends UsageTotals> {
  title: string;
  /** The first column's header: what each row is. */
  header: string;
  testId: string;
  rows: T[];
  rowKey: (row: T) => string;
  label: (row: T) => ReactNode;
}

/** The whole ledger split one way (by model, by purpose), a row per value, biggest first. */
function LedgerTable<T extends UsageTotals>({ title, header, testId, rows, rowKey, label }: LedgerProps<T>) {
  if (rows.length === 0) return null;
  return (
    <section className="metric-card">
      <CardTitle title={title} covers={vi.costWindowAll} />
      <table className="stat-table" data-testid={testId}>
        <thead>
          <tr>
            <th>{header}</th>
            <th>{vi.costModelCalls}</th>
            <th>{vi.tokensHeader}</th>
            <th>{vi.cacheHeader}</th>
            <th>{vi.costTotal}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              <td>{label(row)}</td>
              <td>{row.calls}</td>
              <td>{tokens(row)}</td>
              <td>
                <CacheCell cached={row.cached_tokens} prompt={row.prompt_tokens} />
              </td>
              <td>
                {formatUsd(row.cost_usd)}
                {row.unknown_cost_calls > 0 && <span className="badge warn"> ? {row.unknown_cost_calls}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** A purpose the page has no name for yet is shown as the server wrote it. */
function purposeLabel(row: PurposeUsage): ReactNode {
  return vi.costPurpose[row.purpose] ?? <code>{row.purpose}</code>;
}

/**
 * Honest cost dashboard: today and the week, the recent runs' totals and spend by agent,
 * the cache per agent, the recent days with tokens, what the calls were for and each
 * model — each labelled with what it is counted over, since the run window and the usage
 * ledger are not the same.
 */
export function StatsPanel({ stats, agentName }: Props) {
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
      {stats.cache_by_agent && (
        <AgentCacheTable
          cache={stats.cache_by_agent}
          uncounted={stats.unknown_cache_calls ?? 0}
          covers={recent}
          agentName={agentName}
        />
      )}
      <RecentDays days={stats.days} />
      <LedgerTable
        title={vi.costPurposes}
        header={vi.costPurposeHeader}
        testId="stat-purposes"
        rows={stats.purposes ?? []}
        rowKey={(p) => p.purpose}
        label={purposeLabel}
      />
      <LedgerTable
        title={vi.costModels}
        header={vi.costByModel}
        testId="stat-models"
        rows={stats.models}
        rowKey={(m) => m.model}
        label={(m) => <code>{m.model}</code>}
      />
    </div>
  );
}
