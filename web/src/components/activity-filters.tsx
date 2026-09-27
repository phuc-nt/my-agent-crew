import { useState } from "react";
import type { AgentInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FILTER_STATUSES, type RunFilters } from "../lib/run-filters";
import { Icon } from "./ui/icon";

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
 * and changing it is one tap, not a picker.
 *
 * On a phone the groups stack a third of the screen tall and pushed every run below the
 * fold, so there they fold behind one toggle that names the narrowing in force. Wider
 * screens have room for both and never show it (run-log.css).
 */
export function ActivityFilters({ filters, agents, sources, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const picked = [
    agents.find((a) => a.id === filters.agent)?.name,
    filters.status && vi.runFilters.statuses[filters.status],
    filters.source && (vi.runFilters.sources[filters.source] ?? filters.source),
  ].filter((label): label is string => Boolean(label));
  return (
    <div
      className={`run-filters${open ? " open" : ""}`}
      role="group"
      aria-label={vi.runFilters.label}
      data-testid="run-filters"
    >
      <button
        type="button"
        className={`chip run-filters-fold${picked.length > 0 ? " narrowed" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {[vi.runFilters.fold, ...picked].join(" · ")}
        <Icon name="chevron-down" />
      </button>
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
        options={FILTER_STATUSES.map((s) => ({ value: s, label: vi.runFilters.statuses[s] }))}
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
