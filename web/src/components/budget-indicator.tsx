import { vi } from "../i18n/vi";

interface Props {
  spentUsd: number;
  capUsd: number;
  unknownCostCalls: number;
  /** Conversations this one delegated: their spend is already inside `spentUsd`. */
  childCount?: number;
}

export function formatUsd(value: number): string {
  return `$${value.toFixed(value < 0.01 && value > 0 ? 4 : 2)}`;
}

export function BudgetIndicator({ spentUsd, capUsd, unknownCostCalls, childCount = 0 }: Props) {
  const unlimited = capUsd <= 0;
  const ratio = unlimited ? 0 : Math.min(1, spentUsd / capUsd);
  const over = !unlimited && spentUsd >= capUsd;
  return (
    <div
      className={`budget ${over ? "over" : ""}`}
      title={
        childCount > 0
          ? `${vi.budget} · ${vi.delegateIncludesChildren.replace("{n}", String(childCount))}`
          : vi.budget
      }
      data-testid="budget"
    >
      <span className="budget-label">
        {vi.budget}: {vi.spent(formatUsd(spentUsd), unlimited ? vi.unlimited : formatUsd(capUsd))}
      </span>
      {!unlimited && (
        <progress value={ratio} max={1} aria-label={vi.budget} />
      )}
      {unknownCostCalls > 0 && (
        <span className="badge warn" title={vi.unknownCost(unknownCostCalls)}>
          ? {unknownCostCalls}
        </span>
      )}
    </div>
  );
}
