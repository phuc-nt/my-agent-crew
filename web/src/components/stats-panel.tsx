import type { StatsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";

interface Props {
  stats: StatsInfo | null;
  agentName: (id: string) => string;
}

function Breakdown({ title, rows, name }: { title: string; rows: Record<string, number>; name?: (k: string) => string }) {
  const entries = Object.entries(rows).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  const max = Math.max(...entries.map(([, v]) => v), 0.000001);
  return (
    <>
      <h3>{title}</h3>
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
    </>
  );
}

/** Honest cost dashboard: totals plus spend by agent, model and day. */
export function StatsPanel({ stats, agentName }: Props) {
  if (stats === null) return <p className="muted">{vi.loadFailed}</p>;
  if (stats.runs === 0) return <p className="muted">{vi.costEmpty}</p>;
  return (
    <div className="stats" data-testid="stats">
      <dl className="stat-totals">
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
      <Breakdown title={vi.costByAgent} rows={stats.by_agent} name={agentName} />
      <Breakdown title={vi.costByModel} rows={stats.by_model} />
      <Breakdown title={vi.costByDay} rows={stats.by_day} />
    </div>
  );
}
