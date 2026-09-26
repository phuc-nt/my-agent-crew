import type { AgentInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FILTER_STATUSES, type RunFilters } from "../lib/run-filters";

interface Props {
  filters: RunFilters;
  agents: AgentInfo[];
  /** Source kinds to offer, from `sourceKinds`. */
  sources: string[];
  onChange: (filters: RunFilters) => void;
}

/**
 * Chips that narrow the recent-runs log: one choice per group, "Tất cả" to undo it.
 *
 * Toggle buttons rather than a select, so the current narrowing is visible at a glance
 * and a phone needs one tap, not a picker, to change it.
 */
export function ActivityFilters({ filters, agents, sources, onChange }: Props) {
  return (
    <div className="run-filters" role="group" aria-label={vi.runFilters.label} data-testid="run-filters">
      {/* A crew of one has nothing to choose between. */}
      {agents.length > 1 && (
        <ChipGroup
          label={vi.runFilters.agent}
          value={filters.agent}
          options={agents.map((a) => ({ value: a.id, label: a.name }))}
          onPick={(agent) => onChange({ ...filters, agent })}
        />
      )}
      <ChipGroup
        label={vi.runFilters.status}
        value={filters.status}
        options={FILTER_STATUSES.map((s) => ({ value: s, label: vi.runStatus[s] }))}
        onPick={(status) => onChange({ ...filters, status: FILTER_STATUSES.find((s) => s === status) ?? null })}
      />
      {sources.length > 0 && (
        <ChipGroup
          label={vi.runFilters.source}
          value={filters.source}
          options={sources.map((kind) => ({ value: kind, label: vi.runFilters.sources[kind] ?? kind }))}
          onPick={(source) => onChange({ ...filters, source })}
        />
      )}
    </div>
  );
}

function ChipGroup({
  label,
  value,
  options,
  onPick,
}: {
  label: string;
  value: string | null;
  options: { value: string; label: string }[];
  onPick: (value: string | null) => void;
}) {
  return (
    <div className="run-filter-group" role="group" aria-label={label}>
      <span className="run-filter-label" aria-hidden="true">
        {label}
      </span>
      <button type="button" className="chip" aria-pressed={value === null} onClick={() => onPick(null)}>
        {vi.runFilters.all}
      </button>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="chip"
          aria-pressed={value === option.value}
          onClick={() => onPick(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
