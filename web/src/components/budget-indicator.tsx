import { useRef, useState } from "react";
import { vi } from "../i18n/vi";
import { CapEditor } from "./cap-editor";
import { Icon } from "./ui/icon";
import { MetricBar, MetricRow } from "./ui/metric-card";
import { PopoverChip } from "./ui/popover-chip";

interface Props {
  spentUsd: number;
  capUsd: number;
  unknownCostCalls: number;
  /** Conversations this one delegated: their spend is already inside `spentUsd`. */
  childCount?: number;
  /** Stores a new cap for this conversation; absent, the card only reports. */
  onSetCap?: (capUsd: number) => Promise<void>;
}

export function formatUsd(value: number): string {
  return `$${value.toFixed(value < 0.01 && value > 0 ? 4 : 2)}`;
}

/**
 * The conversation's spend as a header pill: the figure against the cap on the pill, and
 * the breakdown — what is left, what the delegated work is, which calls had no price —
 * in the card it opens. The pill turns amber near the cap and red at it, so the warning
 * is visible without opening anything. The card ends on the cap's editor, so a spent
 * budget is raised where it is read rather than by starting the conversation over.
 */
export function BudgetIndicator({ spentUsd, capUsd, unknownCostCalls, childCount = 0, onSetCap }: Props) {
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
          <Icon name="coins" />
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
        icon="coins"
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
          icon="handoff"
          label={vi.budgetCard.delegated}
          hint={vi.budgetCard.delegatedHint}
          value={vi.budgetCard.delegatedValue(childCount)}
        />
      )}
      {unknownCostCalls > 0 && (
        <MetricRow
          icon="help"
          label={vi.budgetCard.unknown}
          hint={vi.budgetCard.unknownHint}
          value={vi.budgetCard.unknownValue(unknownCostCalls)}
          sub={vi.unknownCost(unknownCostCalls)}
          subTone="warn"
        />
      )}
      {onSetCap && <CapEditor capUsd={capUsd} onSave={onSetCap} />}
    </PopoverChip>
  );
}

/** The budget notices' way out: the same editor behind one button, folded once it saved.
 *  Folding removes the control the keyboard was on, so it goes back to the button. */
export function RaiseCapButton({ capUsd, onSave }: { capUsd: number; onSave: (capUsd: number) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const saveAndFold = async (cap: number) => {
    await onSave(cap);
    setOpen(false);
    toggle.current?.focus();
  };
  return (
    <>
      <button ref={toggle} type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {vi.budgetCard.raise}
      </button>
      {open && <CapEditor capUsd={capUsd} onSave={saveAndFold} />}
    </>
  );
}
