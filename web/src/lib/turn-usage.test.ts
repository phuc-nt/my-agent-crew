import { describe, expect, it } from "vitest";
import { addStep, cachedPercent, compactTokens } from "./turn-usage";

describe("a turn's usage", () => {
  it("adds each model call and says how much the cache served", () => {
    const first = addStep(null, { prompt_tokens: 20000, cached_tokens: 0, cost_usd: 0.06 });
    const both = addStep(first, { prompt_tokens: 20000, cached_tokens: 19000, cost_usd: 0.005 });

    expect(both).toEqual({ steps: 2, promptTokens: 40000, cachedTokens: 19000, costUsd: 0.065, unpriced: false });
    expect(cachedPercent(both)).toBe(48);
  });

  it("keeps a call without a price or tokens from hiding the rest", () => {
    const usage = addStep(addStep(null, { cost_usd: null }), { prompt_tokens: 900, cost_usd: 0.001 });
    expect(usage.unpriced).toBe(true);
    expect(usage.costUsd).toBe(0.001);
    expect(cachedPercent(addStep(null, { cost_usd: 0 }))).toBe(0);
  });

  it("writes tokens compactly", () => {
    expect([compactTokens(950), compactTokens(2430), compactTokens(24310)]).toEqual(["950", "2.4k", "24k"]);
  });
});
