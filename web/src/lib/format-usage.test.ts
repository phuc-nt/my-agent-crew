import { describe, expect, it } from "vitest";
import type { DayUsage, RunStep } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { cacheByAgent, cacheShare, compactNumber, dayWindows, modelUsageParts } from "./format-usage";

type ModelStep = Extract<RunStep, { kind: "model" }>;
const step = (overrides: Partial<ModelStep> = {}): ModelStep => ({
  kind: "model",
  chars: 10,
  provider: "openrouter",
  model: "deepseek",
  cost_usd: 0.001,
  duration_ms: 2000,
  ...overrides,
});

const day = (date: string, overrides: Partial<DayUsage> = {}): DayUsage => ({
  day: date,
  calls: 1,
  cost_usd: 0.01,
  prompt_tokens: 1000,
  completion_tokens: 100,
  cached_tokens: 500,
  unknown_cost_calls: 0,
  ...overrides,
});

describe("compact numbers", () => {
  it("keeps small counts whole and shortens the rest to one meaningful decimal", () => {
    expect(compactNumber(950)).toBe("950");
    expect(compactNumber(8_100)).toBe("8.1k");
    expect(compactNumber(12_000)).toBe("12k");
    expect(compactNumber(12_345)).toBe("12.3k");
    expect(compactNumber(123_456)).toBe("123k");
    // Rounds into the next unit instead of reading "1000k".
    expect(compactNumber(999_600)).toBe("1M");
    expect(compactNumber(1_234_567)).toBe("1.2M");
  });

  it("gives no share when the prompt size is unknown", () => {
    expect(cacheShare(8_100, 12_300)).toBe(66);
    expect(cacheShare(0, 12_300)).toBe(0);
    expect(cacheShare(null, 12_300)).toBeNull();
    expect(cacheShare(undefined, 12_300)).toBeNull();
    expect(cacheShare(10, 0)).toBeNull();
  });
});

describe("a model step's usage line", () => {
  it("reads model, time to first token, tokens with the cached part, and thinking", () => {
    const parts = modelUsageParts(
      step({ first_token_ms: 1_234, prompt_tokens: 12_300, cached_tokens: 8_100, thinking: true }),
    );
    expect(parts).toEqual(["openrouter:deepseek", "TTFT 1.2s", "12.3k tok (8.1k cache)", "suy nghĩ"]);
  });

  it("leaves out each part the call did not report", () => {
    expect(modelUsageParts(step())).toEqual(["openrouter:deepseek"]);
    expect(modelUsageParts(step({ provider: null, first_token_ms: 850 }))).toEqual(["deepseek", "TTFT 850ms"]);
    // A prompt size without a cache figure: the provider does not report its cache.
    expect(modelUsageParts(step({ prompt_tokens: 950, cached_tokens: null }))).toEqual([
      "openrouter:deepseek",
      "950 tok",
    ]);
  });

  // Zero prompt tokens is how a provider that reports no usage arrives.
  it("omits the tokens when the prompt count is zero, but shows a cache that served nothing", () => {
    expect(modelUsageParts(step({ prompt_tokens: 0, cached_tokens: 0 }))).toEqual(["openrouter:deepseek"]);
    expect(modelUsageParts(step({ prompt_tokens: 4_000, cached_tokens: 0 }))).toContain("4k tok (0 cache)");
  });
});

describe("today and the last seven days", () => {
  // The suite runs at UTC+7: 17:30Z on the 19th is 00:30 on the 20th where the owner is.
  const now = new Date("2026-09-19T17:30:00Z");

  it("counts today by the viewer's date, not the UTC one", () => {
    const days = [day("2026-09-19", { cost_usd: 0.4 }), day("2026-09-20", { cost_usd: 0.05, calls: 2 })];

    const { today, week } = dayWindows(days, now);

    expect(today.cost_usd).toBeCloseTo(0.05);
    expect(today.calls).toBe(2);
    expect(week.cost_usd).toBeCloseTo(0.45);
  });

  it("keeps the week to the seven days ending today", () => {
    const days = ["2026-09-13", "2026-09-14", "2026-09-20"].map((d) => day(d));

    const { today, week } = dayWindows(days, now);

    expect(week.calls).toBe(2);
    expect(week.cached_tokens).toBe(1000);
    expect(today.prompt_tokens).toBe(1000);
  });

  // An answer computed before midnight has no bucket for the new day yet.
  it("reads nothing today when the server has not yet opened the day", () => {
    const { today, week } = dayWindows([day("2026-09-19")], now);
    expect(today.calls).toBe(0);
    expect(week.calls).toBe(1);
  });

  it("copes with a server that does not count the cache", () => {
    const older = { ...day("2026-09-20"), cached_tokens: undefined } as unknown as DayUsage;
    expect(dayWindows([older], now).today.cached_tokens).toBe(0);
  });
});

describe("cache by agent", () => {
  it("adds up the calls that reported both figures, biggest prompt first", () => {
    const runs = [
      fakeRun({ id: "a", agent_id: "coach", steps: [step({ prompt_tokens: 1_000, cached_tokens: 900 })] }),
      fakeRun({
        id: "b",
        agent_id: "default",
        steps: [
          step({ prompt_tokens: 3_000, cached_tokens: 0 }),
          step({ prompt_tokens: 2_000, cached_tokens: 1_000 }),
          // No cache figure: left out, or the share would sink for a quiet provider.
          step({ prompt_tokens: 9_000, cached_tokens: null }),
          { kind: "tool", name: "read", ok: true, output: "x", duration_ms: 1 },
        ],
      }),
      fakeRun({ id: "c", agent_id: "coach", steps: [step({ prompt_tokens: 500, cached_tokens: 500 })] }),
    ];

    expect(cacheByAgent(runs)).toEqual([
      { agentId: "default", promptTokens: 5_000, cachedTokens: 1_000 },
      { agentId: "coach", promptTokens: 1_500, cachedTokens: 1_400 },
    ]);
  });
});
