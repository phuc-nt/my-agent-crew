import type { DayUsage, ModelUsage, StatsInfo } from "../api/types";
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
    <section className="metric-card">
      <h3 className="metric-card-title">{title}</h3>
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

/** The last days side by side: a cost bar plus the calls and tokens behind it. */
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
            <span className="stat-detail muted">
              {vi.costCalls(d.calls)} · {vi.tokens(d.prompt_tokens, d.completion_tokens)}
              {d.unknown_cost_calls > 0 && ` · ? ${d.unknown_cost_calls}`}
            </span>
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
      <h3 className="metric-card-title">{vi.costModels}</h3>
      <table className="stat-table" data-testid="stat-models">
        <thead>
          <tr>
            <th>{vi.costByModel}</th>
            <th>{vi.costModelCalls}</th>
            <th>{vi.tokensHeader}</th>
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
              <td>{vi.tokens(m.prompt_tokens, m.completion_tokens)}</td>
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

/** Honest cost dashboard: totals, spend by agent, the recent days with tokens, and each model. */
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
      <RecentDays days={stats.days} />
      <ModelTable models={stats.models} />
    </div>
  );
}
