import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { DayUsage, StatsInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FakeBackend } from "../test/fake-backend";
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
    purposes: [],
    pending_proposals: 0,
    ...overrides,
  };
}

// The suite runs at UTC+7, the owner's zone. 17:30Z on the 19th is 00:30 on the 20th
// there: the UTC date says the 19th, the owner's calendar has already turned.
let backend: FakeBackend;
beforeEach(() => {
  vitest.useFakeTimers({ toFake: ["Date"] });
  vitest.setSystemTime(new Date("2026-09-19T17:30:00Z"));
  // Every figure arrives with the stats, so the panel has nothing to fetch; a request it
  // made anyway is recorded here rather than sent.
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

  // The day rows below flag calls with no known price; a tile that left them out would
  // pass for the whole of the day's spend.
  it("flags the tiles' calls whose price is unknown, as the day rows do", () => {
    const days = [
      day("2026-09-19", { unknown_cost_calls: 2 }),
      day("2026-09-20", { calls: 4, unknown_cost_calls: 3 }),
    ];
    render(<StatsPanel stats={stats({ days })} agentName={name} />);

    const [today, week] = Array.from(screen.getByTestId("stat-periods").children);
    expect(today).toHaveTextContent("? 3");
    expect(week).toHaveTextContent("? 5");
    expect(screen.getByTestId("stat-days")).toHaveTextContent("? 3");
  });

  it("adds no unknown-price flag to a tile whose calls were all priced", () => {
    render(<StatsPanel stats={stats({ days: [day("2026-09-20", { unknown_cost_calls: 0 })] })} agentName={name} />);

    expect(screen.getByTestId("stat-periods")).not.toHaveTextContent("?");
  });

  it("says what each figure is counted over", () => {
    render(<StatsPanel stats={stats({ models: [{ model: "openrouter:deepseek", ...day("x") }] })} agentName={name} />);

    expect(screen.getByText(vi.costWindowRecent(500))).toBeInTheDocument();
    const byAgent = screen.getByRole("heading", { name: new RegExp(`^${vi.costByAgent}`) });
    expect(byAgent).toHaveTextContent(vi.costWindowRecent(500));
    const byModel = screen.getByRole("heading", { name: new RegExp(`^${vi.costModels}`) });
    expect(byModel).toHaveTextContent(vi.costWindowAll);
  });

  it("splits the whole ledger by what each call was for, named in words", () => {
    const purposes = [
      { purpose: "chat", ...day("x", { calls: 40, cost_usd: 1.2 }) },
      { purpose: "session_summary", ...day("x", { calls: 3, cost_usd: 0.05 }) },
      { purpose: "image", ...day("x", { calls: 2, cost_usd: 0, unknown_cost_calls: 2 }) },
      { purpose: "rerank", ...day("x", { calls: 1, cost_usd: 0.01 }) },
    ];
    render(<StatsPanel stats={stats({ purposes })} agentName={name} />);

    const title = screen.getByRole("heading", { name: new RegExp(`^${vi.costPurposes}`) });
    expect(title).toHaveTextContent(vi.costWindowAll);
    const [, chat, recap, picture, unnamed] = within(screen.getByTestId("stat-purposes")).getAllByRole("row");
    expect(chat).toHaveTextContent(vi.costPurpose.chat);
    expect(chat).toHaveTextContent("$1.20");
    expect(recap).toHaveTextContent(vi.costPurpose.session_summary);
    // Paid for, only unpriced: flagged as a model row flags it, never passed off as free.
    expect(picture).toHaveTextContent(vi.costPurpose.image);
    expect(picture).toHaveTextContent("? 2");
    // A purpose the page has no name for yet is shown as the server wrote it.
    expect(unnamed).toHaveTextContent("rerank");
  });

  it("names a voice note transcription row by its own purpose", () => {
    const purposes = [{ purpose: "transcribe", ...day("x", { calls: 1, cost_usd: 0.00002 }) }];
    render(<StatsPanel stats={stats({ purposes })} agentName={name} />);

    const [, row] = within(screen.getByTestId("stat-purposes")).getAllByRole("row");
    expect(row).toHaveTextContent(vi.costPurpose.transcribe);
  });

  it("leaves the purpose card out while the ledger is empty or the server has none", () => {
    const { rerender } = render(<StatsPanel stats={stats()} agentName={name} />);
    expect(screen.queryByTestId("stat-purposes")).not.toBeInTheDocument();

    rerender(<StatsPanel stats={stats({ purposes: undefined })} agentName={name} />);
    expect(screen.getByTestId("stats")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: new RegExp(`^${vi.costPurposes}`) })).not.toBeInTheDocument();
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

  it("shows each agent's cache from the server's totals, biggest prompt first", () => {
    const cache_by_agent = {
      coach: { prompt_tokens: 12_000, cached_tokens: 10_000 },
      default: { prompt_tokens: 30_000, cached_tokens: 0 },
    };
    render(<StatsPanel stats={stats({ cache_by_agent })} agentName={name} />);

    const [, first, second] = within(screen.getByTestId("stat-agent-cache")).getAllByRole("row");
    expect(first).toHaveTextContent("Trợ lý");
    expect(first).toHaveTextContent("30k");
    // A cache that served nothing is shown as such: that is what a broken cache looks like.
    expect(first).toHaveTextContent("0 · 0%");
    expect(second).toHaveTextContent("HLV");
    expect(second).toHaveTextContent("12k");
    expect(second).toHaveTextContent("10k · 83%");
  });

  it("says so when no call in the window reported its tokens", () => {
    render(<StatsPanel stats={stats({ cache_by_agent: {} })} agentName={name} />);

    expect(screen.getByText(vi.costNoTokens)).toBeInTheDocument();
    expect(screen.queryByTestId("stat-agent-cache")).not.toBeInTheDocument();
  });

  // A provider that reports the prompt but not the part it cached leaves no row either,
  // while the days and models on the same page show those tokens.
  it("says the cache went unreported when the calls did report their tokens", () => {
    render(<StatsPanel stats={stats({ cache_by_agent: {}, unknown_cache_calls: 3 })} agentName={name} />);

    expect(screen.getByText(vi.costNoCacheFigure)).toBeInTheDocument();
    expect(screen.queryByText(vi.costNoTokens)).not.toBeInTheDocument();
    expect(screen.queryByTestId("stat-agent-cache")).not.toBeInTheDocument();
  });

  // The page's live runs are fifty of whoever was busiest, while the spend by agent beside
  // this card counts five hundred. Fetching those five hundred, steps and all, on every
  // visit to add up two figures per agent was the heaviest request the page made.
  it("counts each agent's cache over the same runs as its spend, without fetching them", () => {
    const cache_by_agent = { coach: { prompt_tokens: 10_000, cached_tokens: 8_000 } };
    render(<StatsPanel stats={stats({ cache_by_agent })} agentName={name} />);

    expect(screen.getByTestId("stat-agent-cache")).toHaveTextContent("8k · 80%");
    const title = screen.getByRole("heading", { name: new RegExp(`^${vi.costCacheByAgent}`) });
    expect(title).toHaveTextContent(vi.costWindowRecent(500));
    const byAgent = screen.getByRole("heading", { name: new RegExp(`^${vi.costByAgent}`) });
    expect(byAgent).toHaveTextContent(vi.costWindowRecent(500));
    expect(backend.requests).toEqual([]);
  });

  it("leaves the card out when the server does not total the cache per agent", () => {
    render(<StatsPanel stats={stats()} agentName={name} />);

    expect(screen.queryByRole("heading", { name: new RegExp(`^${vi.costCacheByAgent}`) })).not.toBeInTheDocument();
    expect(screen.queryByText(vi.costNoTokens)).not.toBeInTheDocument();
  });
});
