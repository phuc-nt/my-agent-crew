import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { DayUsage, RunStep, StatsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeRun } from "../test/fake-backend";
import { StatsPanel } from "./stats-panel";

const name = (id: string) => (id === "coach" ? "HLV" : "Trợ lý");

const day = (date: string, overrides: Partial<DayUsage> = {}): DayUsage => ({
  day: date,
  calls: 1,
  cost_usd: 0.1,
  prompt_tokens: 1_000,
  completion_tokens: 100,
  cached_tokens: 0,
  unknown_cost_calls: 0,
  ...overrides,
});

function stats(overrides: Partial<StatsInfo> = {}): StatsInfo {
  return {
    runs: 500,
    model_calls: 900,
    spent_usd: 1.5,
    unknown_cost_calls: 0,
    by_agent: { coach: 1, default: 0.5 },
    by_model: {},
    by_day: {},
    days: [],
    models: [],
    pending_proposals: 0,
    ...overrides,
  };
}

const call = (prompt: number, cached: number | null): RunStep => ({
  kind: "model",
  chars: 10,
  provider: "openrouter",
  model: "deepseek",
  cost_usd: 0.001,
  tool_calls: [],
  prompt_tokens: prompt,
  cached_tokens: cached,
  duration_ms: 1000,
});

// The suite runs at UTC+7, the owner's zone. 17:30Z on the 19th is 00:30 on the 20th
// there: the UTC date says the 19th, the owner's calendar has already turned.
let backend: FakeBackend;
beforeEach(() => {
  vitest.useFakeTimers({ toFake: ["Date"] });
  vitest.setSystemTime(new Date("2026-09-19T17:30:00Z"));
  // The per-agent cache reads its own window of stored runs.
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});
afterEach(() => {
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
});

describe("the costs page's usage figures", () => {
  it("counts today and the week by the owner's calendar day, with the cache share", () => {
    const days = [
      day("2026-09-13", { cost_usd: 5 }),
      day("2026-09-19", { cost_usd: 0.4, calls: 3 }),
      day("2026-09-20", { cost_usd: 0.05, calls: 2, prompt_tokens: 10_000, cached_tokens: 6_600 }),
    ];
    render(<StatsPanel stats={stats({ days })} agentName={name} />);

    const [today, week] = Array.from(screen.getByTestId("stat-periods").children);
    expect(today).toHaveTextContent(vi.costToday);
    expect(today).toHaveTextContent("$0.05");
    expect(today).toHaveTextContent(`${vi.costCalls(2)} · ${vi.cacheShare(66)}`);
    // The 13th is eight days back on the owner's calendar, so it falls out of the week.
    expect(week).toHaveTextContent(vi.costWeek);
    expect(week).toHaveTextContent("$0.45");
    expect(week).toHaveTextContent(`${vi.costCalls(5)} · ${vi.cacheShare(60)}`);
  });

  // A bare "lượt" is how the page counts runs ("500 lượt gần nhất"); a tile's model
  // calls written that way read as more runs today than the whole window holds.
  it("names the tiles' model calls as calls, not runs", () => {
    render(<StatsPanel stats={stats({ days: [day("2026-09-20", { calls: 1234 })] })} agentName={name} />);

    const [today] = Array.from(screen.getByTestId("stat-periods").children);
    expect(today).toHaveTextContent("1234 lượt gọi");
  });

  it("says what each figure is counted over", () => {
    render(<StatsPanel stats={stats({ models: [{ model: "openrouter:deepseek", ...day("x") }] })} agentName={name} />);

    expect(screen.getByText(vi.costWindowRecent(500))).toBeInTheDocument();
    const byAgent = screen.getByRole("heading", { name: new RegExp(`^${vi.costByAgent}`) });
    expect(byAgent).toHaveTextContent(vi.costWindowRecent(500));
    const byModel = screen.getByRole("heading", { name: new RegExp(`^${vi.costModels}`) });
    expect(byModel).toHaveTextContent(vi.costWindowAll);
  });

  it("shows each model's cached tokens and their share of the prompt", () => {
    const models = [
      { model: "openrouter:deepseek", ...day("x", { prompt_tokens: 120_000, cached_tokens: 81_000 }) },
      { model: "openai:gpt", ...day("x", { prompt_tokens: 4_000, cached_tokens: 0 }) },
    ];
    render(<StatsPanel stats={stats({ models })} agentName={name} />);

    const table = screen.getByTestId("stat-models");
    expect(within(table).getByRole("columnheader", { name: vi.cacheHeader })).toBeInTheDocument();
    const [, deepseek, gpt] = within(table).getAllByRole("row");
    expect(deepseek).toHaveTextContent("81k · 68%");
    // A cache that served nothing is shown as such: that is what a broken cache looks like.
    expect(gpt).toHaveTextContent("0 · 0%");
  });

  // The cache is compared with the prompt on the same row; one in raw digits beside the
  // other in "k" and "M" means converting in one's head.
  it("writes the tokens as short as the cache beside them", () => {
    const big = { prompt_tokens: 123_456_789, completion_tokens: 9_876_543, cached_tokens: 98_765_432 };
    const days = [day("2026-09-20", big)];
    render(<StatsPanel stats={stats({ days, models: [{ model: "openrouter:deepseek", ...day("x", big) }] })} agentName={name} />);

    const [, model] = within(screen.getByTestId("stat-models")).getAllByRole("row");
    expect(model).toHaveTextContent("123M vào / 9.9M ra");
    expect(model).toHaveTextContent("98.8M · 80%");
    expect(screen.getByTestId("stat-days")).toHaveTextContent("123M vào / 9.9M ra");
  });

  it("adds up each agent's cache from the model calls on the page's runs", async () => {
    const runs = [
      fakeRun({ id: "a", agent_id: "coach", steps: [call(10_000, 9_000), call(2_000, 1_000)] }),
      fakeRun({ id: "b", agent_id: "default", steps: [call(3_000, 0)] }),
      // No cache figure from this provider: left out rather than counted as a miss.
      fakeRun({ id: "c", agent_id: "default", steps: [call(50_000, null)] }),
    ];
    render(<StatsPanel stats={stats()} agentName={name} runs={runs} />);

    const table = await screen.findByTestId("stat-agent-cache");
    const [, coach, other] = within(table).getAllByRole("row");
    expect(coach).toHaveTextContent("HLV");
    expect(coach).toHaveTextContent("12k");
    expect(coach).toHaveTextContent("10k · 83%");
    expect(other).toHaveTextContent("Trợ lý");
    expect(other).toHaveTextContent("0 · 0%");
    const title = screen.getByRole("heading", { name: new RegExp(`^${vi.costCacheByAgent}`) });
    expect(title).toHaveTextContent(vi.costWindowRecent(3));
  });

  it("says so when no call on the page reported its tokens", async () => {
    render(<StatsPanel stats={stats()} agentName={name} runs={[fakeRun({ steps: [call(0, null)] })]} />);

    expect(await screen.findByText(vi.costNoTokens)).toBeInTheDocument();
    expect(screen.queryByTestId("stat-agent-cache")).not.toBeInTheDocument();
  });

  // The page's live runs are fifty of whoever was busiest, while the spend by agent beside
  // this card counts five hundred: a quiet agent had spend and no cache row.
  it("counts each agent's cache over the same window as its spend", async () => {
    backend.runs = [fakeRun({ id: "quiet", agent_id: "coach", steps: [call(10_000, 8_000)] })];
    const streamed = [fakeRun({ id: "busy", agent_id: "default", steps: [call(3_000, 3_000)] })];
    render(<StatsPanel stats={stats()} agentName={name} runs={streamed} />);

    const table = await screen.findByTestId("stat-agent-cache");
    const [, coach, other] = within(table).getAllByRole("row");
    expect(coach).toHaveTextContent("HLV");
    expect(coach).toHaveTextContent("8k · 80%");
    expect(other).toHaveTextContent("Trợ lý");
    expect(backend.requests.map((r) => r.path)).toContain("/activity/runs?limit=500");
    const title = screen.getByRole("heading", { name: new RegExp(`^${vi.costCacheByAgent}`) });
    expect(title).toHaveTextContent(vi.costWindowRecent(2));
  });

  it("says when the runs behind the cache cannot be read, and asks again on request", async () => {
    backend.runs = [fakeRun({ id: "quiet", agent_id: "coach", steps: [call(10_000, 8_000)] })];
    let down = true;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      down ? Promise.reject(new Error("offline")) : backend.fetch(input, init),
    );
    render(<StatsPanel stats={stats()} agentName={name} runs={[]} />);

    const retry = await screen.findByRole("button", { name: vi.runFilters.retry });
    expect(screen.getByText(new RegExp(vi.runFilters.failed))).toBeInTheDocument();
    down = false;
    await userEvent.click(retry);

    expect(await screen.findByTestId("stat-agent-cache")).toHaveTextContent("8k · 80%");
  });
});
