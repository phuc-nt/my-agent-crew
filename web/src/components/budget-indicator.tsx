import { vi } from "../i18n/vi";
import { MetricBar, MetricRow } from "./ui/metric-card";
import { PopoverChip } from "./ui/popover-chip";

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

/**
 * The conversation's spend as a header pill: the figure against the cap on the pill, and
 * the breakdown — what is left, what the delegated work is, which calls had no price —
 * in the card it opens. The pill turns amber near the cap and red at it, so the warning
 * is visible without opening anything.
 */
export function BudgetIndicator({ spentUsd, capUsd, unknownCostCalls, childCount = 0 }: Props) {
  const unlimited = capUsd <= 0;
  const ratio = unlimited ? 0 : Math.min(1, spentUsd / capUsd);
  const over = !unlimited && spentUsd >= capUsd;
  const percent = Math.round(ratio * 100);
  const tone = over ? "danger" : ratio >= 0.8 ? "warn" : undefined;
  const figure = vi.spent(formatUsd(spentUsd), unlimited ? vi.unlimited : formatUsd(capUsd));

  return (
    <PopoverChip
      className={`budget${over ? " over" : ""}`}
      testId="budget"
      tone={tone}
      popoverLabel={vi.budgetCard.title}
      title={
        childCount > 0
          ? `${vi.budget} · ${vi.delegateIncludesChildren.replace("{n}", String(childCount))}`
          : vi.budget
      }
      label={
        <>
          <span aria-hidden="true">💰</span>
          <span className="tabular">
            {figure}
            {!unlimited && ` (${percent}%)`}
          </span>
          {unknownCostCalls > 0 && (
            <span className="badge warn" title={vi.unknownCost(unknownCostCalls)}>
              ? {unknownCostCalls}
            </span>
          )}
        </>
      }
    >
      <MetricRow
        icon="💰"
        label={vi.budgetCard.spent}
        hint={vi.budgetCard.spentHint}
        value={figure}
        sub={
          unlimited
            ? vi.unlimited
            : over
              ? vi.budgetCard.reached
              : vi.budgetCard.left(formatUsd(Math.max(0, capUsd - spentUsd)))
        }
        subTone={over ? "danger" : ratio >= 0.8 ? "warn" : "ok"}
      >
        {!unlimited && <MetricBar ratio={ratio} label={vi.budget} />}
      </MetricRow>
      {childCount > 0 && (
        <MetricRow
          icon="🧩"
          label={vi.budgetCard.delegated}
          hint={vi.budgetCard.delegatedHint}
          value={vi.budgetCard.delegatedValue(childCount)}
        />
      )}
      {unknownCostCalls > 0 && (
        <MetricRow
          icon="❓"
          label={vi.budgetCard.unknown}
          hint={vi.budgetCard.unknownHint}
          value={vi.budgetCard.unknownValue(unknownCostCalls)}
          sub={vi.unknownCost(unknownCostCalls)}
          subTone="warn"
        />
      )}
    </PopoverChip>
  );
}
