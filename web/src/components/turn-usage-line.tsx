import { vi } from "../i18n/vi";
import { cachedPercent, compactTokens, type TurnUsage } from "../lib/turn-usage";
import { formatUsd } from "./budget-indicator";

/** Under a reply, small: how many model calls its turn took, the prompt they sent, how much
 *  of it the cache served and the price, so a costly turn is seen where it happened. */
export function TurnUsageLine({ usage }: { usage: TurnUsage }) {
  const t = vi.turnUsage;
  const parts = [t.steps(usage.steps)];
  if (usage.promptTokens > 0) parts.push(t.tokens(compactTokens(usage.promptTokens)), t.cached(cachedPercent(usage)));
  parts.push(usage.unpriced ? `≥ ${formatUsd(usage.costUsd)} (${t.unpriced})` : formatUsd(usage.costUsd));
  return (
    <div className="turn-usage muted" data-testid="turn-usage" aria-label={t.label}>
      {parts.join(" · ")}
    </div>
  );
}
