/** What a turn has cost so far: its model calls, the prompt tokens they sent, how many of
 *  those the provider read back from its cache, and their price where one is known. */
export interface TurnUsage {
  steps: number;
  promptTokens: number;
  cachedTokens: number;
  costUsd: number;
  /** A call came back without a price, so `costUsd` is a floor. */
  unpriced: boolean;
}

interface Step {
  prompt_tokens?: number | null;
  cached_tokens?: number | null;
  cost_usd: number | null;
}

/** The usage after one more model call; `null` starts a turn. */
export function addStep(usage: TurnUsage | null, step: Step): TurnUsage {
  const base = usage ?? { steps: 0, promptTokens: 0, cachedTokens: 0, costUsd: 0, unpriced: false };
  return {
    steps: base.steps + 1,
    promptTokens: base.promptTokens + (step.prompt_tokens ?? 0),
    cachedTokens: base.cachedTokens + (step.cached_tokens ?? 0),
    costUsd: base.costUsd + (step.cost_usd ?? 0),
    unpriced: base.unpriced || step.cost_usd === null,
  };
}

/** The share of prompt tokens served from the cache, as a whole percent. */
export function cachedPercent(usage: TurnUsage): number {
  return usage.promptTokens > 0 ? Math.round((100 * usage.cachedTokens) / usage.promptTokens) : 0;
}

export function compactTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
}
