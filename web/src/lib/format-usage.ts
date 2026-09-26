// Token counts and cache hits, written the way a glance reads them.
//
// The crew runs on a route where the prompt cache decides the bill, so these figures are
// how the owner tells a persona edit that kept the cache from one that broke it.
import type { DayUsage, RunInfo, RunStep, UsageTotals } from "../api/types";
import { vi } from "../i18n/vi";
import { dayOffset } from "./relative-time";

type ModelStep = Extract<RunStep, { kind: "model" }>;

/** "950", "8.1k", "12k", "123k", "1.2M": short enough to sit on a row beside others. */
export function compactNumber(n: number): string {
  if (n < 1000) return String(Math.round(n));
  // Switched a little early, so 999 600 reads "1M" rather than rounding up to "1000k".
  const [value, unit] = n < 999_500 ? [n / 1000, "k"] : [n / 1_000_000, "M"];
  // One decimal while it still says something; "123.4k" is wider and no more useful.
  return `${Number(value.toFixed(value >= 100 ? 0 : 1))}${unit}`;
}

/** The share of the prompt the provider served from its cache, as a whole percent. */
export function cacheShare(cached: number | null | undefined, prompt: number | null | undefined): number | null {
  if (cached == null || !prompt) return null;
  return Math.round((cached / prompt) * 100);
}

/**
 * What a finished model call cost in time and tokens, each part only when it is known:
 * "openrouter:deepseek · TTFT 1.2s · 12.3k tok (8.1k cache) · suy nghĩ".
 */
export function modelUsageParts(step: ModelStep): string[] {
  const parts: string[] = [];
  if (step.model) parts.push(step.provider ? `${step.provider}:${step.model}` : step.model);
  // Absent on runs from before the first word was timed, and on a live call the page
  // only heard about once it answered.
  if (step.first_token_ms != null) parts.push(vi.stepTtft(step.first_token_ms));
  // Zero means the provider did not say: every real call sends some prompt.
  if (step.prompt_tokens) {
    const tokens = vi.stepTokens(compactNumber(step.prompt_tokens));
    // A cache that served nothing is still worth showing: it is how a broken cache looks.
    parts.push(
      step.cached_tokens != null ? `${tokens} ${vi.stepCached(compactNumber(step.cached_tokens))}` : tokens,
    );
  }
  if (step.thinking) parts.push(vi.stepThinking);
  return parts;
}

const NO_USAGE: UsageTotals = {
  calls: 0,
  cost_usd: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  cached_tokens: 0,
  unknown_cost_calls: 0,
};

function add(a: UsageTotals, b: UsageTotals): UsageTotals {
  return {
    calls: a.calls + b.calls,
    cost_usd: a.cost_usd + b.cost_usd,
    prompt_tokens: a.prompt_tokens + b.prompt_tokens,
    completion_tokens: a.completion_tokens + b.completion_tokens,
    // A server from before the cache was counted leaves it out.
    cached_tokens: a.cached_tokens + (b.cached_tokens ?? 0),
    unknown_cost_calls: a.unknown_cost_calls + b.unknown_cost_calls,
  };
}

/**
 * Today and the seven days ending today, on the viewer's calendar.
 *
 * The server buckets calls by the owner's day, and those bucket names are read here as
 * local dates rather than taken by position: the last bucket is the server's today, which
 * is yesterday for a page open past midnight on an answer computed before it.
 */
export function dayWindows(days: DayUsage[], now: Date = new Date()): { today: UsageTotals; week: UsageTotals } {
  let today = NO_USAGE;
  let week = NO_USAGE;
  for (const day of days) {
    // No offset in the stamp, so it is read as the start of that day where the viewer is.
    const offset = dayOffset(`${day.day}T00:00:00`, now);
    if (offset === null || offset > 0 || offset < -6) continue;
    week = add(week, day);
    if (offset === 0) today = add(today, day);
  }
  return { today, week };
}

export interface AgentCache {
  agentId: string;
  promptTokens: number;
  cachedTokens: number;
}

/**
 * Prompt and cached tokens per agent, added up from the model calls on the given runs.
 *
 * Only calls that reported both count: a call with no cache figure would pull the share
 * down for a provider that simply does not say.
 */
export function cacheByAgent(runs: RunInfo[]): AgentCache[] {
  const totals = new Map<string, AgentCache>();
  for (const run of runs) {
    for (const step of run.steps) {
      if (step.kind !== "model" || !step.prompt_tokens || step.cached_tokens == null) continue;
      const entry = totals.get(run.agent_id) ?? { agentId: run.agent_id, promptTokens: 0, cachedTokens: 0 };
      entry.promptTokens += step.prompt_tokens;
      entry.cachedTokens += step.cached_tokens;
      totals.set(run.agent_id, entry);
    }
  }
  return [...totals.values()].sort((a, b) => b.promptTokens - a.promptTokens);
}
