import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { parentConversationId } from "../state/activity-reducer";
import { stepProgress } from "../lib/run-progress";
import { formatUsd } from "./budget-indicator";
import { MetricBar, MetricCard, MetricRow } from "./ui/metric-card";

/**
 * What this conversation has cost so far: the spend, the work done and the models behind it.
 *
 * The spend comes from the conversation itself, never from adding up its runs. A run's
 * `spent_usd` arrives as the conversation's running total, not that run's own cost, and a
 * delegated child's spend is already folded into the parent — so summing would count the
 * same money two ways over. Steps and models really are per-run, so those are summed.
 * Every figure is already in hand, so the card costs no request.
 *
 * "Steps" means steps of the work, the same total the progress bars count. An agent that
 * says what it is doing before each call would otherwise report twice the work of a silent
 * one that did exactly the same thing.
 */
export function ConversationActivitySummary({
  runs,
  conversationId,
  spent,
  cap,
}: {
  runs: RunInfo[];
  conversationId: string;
  spent: number;
  /** The conversation's cap; zero or absent means no cap, so no bar. */
  cap?: number;
}) {
  const steps = runs.reduce((total, r) => total + stepProgress(r).total, 0);
  const delegated = runs.filter((r) => parentConversationId(r) === conversationId).length;
  const models = [
    ...new Set(
      runs.flatMap((r) =>
        r.steps.flatMap((s) => (s.kind === "model" && s.model ? [s.model] : [])),
      ),
    ),
  ];
  const capped = cap !== undefined && cap > 0;
  const ratio = capped ? spent / cap : 0;
  const t = vi.conversationActivity;

  return (
    <MetricCard title={t.summary} testId="conversation-cost">
      <MetricRow
        icon="coins"
        label={vi.costs}
        hint={t.costHint}
        value={t.spent(spent)}
        sub={capped ? t.capShare(formatUsd(cap), Math.round(Math.min(1, ratio) * 100)) : undefined}
        subTone={ratio >= 1 ? "danger" : ratio >= 0.8 ? "warn" : "ok"}
      >
        {capped && <MetricBar ratio={ratio} label={vi.budget} />}
      </MetricRow>
      <MetricRow
        icon="steps"
        label={vi.activity}
        hint={t.stepsHint}
        value={t.steps(steps)}
        sub={delegated > 0 ? t.delegated(delegated) : undefined}
        subTone="accent"
      />
      {models.length > 0 && (
        <MetricRow
          icon="chip"
          label={t.models}
          value={t.modelsValue(models.length)}
          sub={models.join(", ")}
        />
      )}
    </MetricCard>
  );
}
