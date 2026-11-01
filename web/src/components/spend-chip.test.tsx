import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { OpenRouterReport, SpendInfo } from "../api/types";
import { SPEND_POLL_MS } from "../hooks/use-spend";
import { vi } from "../i18n/vi";
import { FakeBackend } from "../test/fake-backend";
import { SpendChip, SpendPill, monthUsd, spendTone } from "./spend-chip";

const router = (over: Partial<OpenRouterReport> = {}): OpenRouterReport => ({
  usage: 30,
  usage_daily: 0.4,
  usage_weekly: 2,
  usage_monthly: 6.25,
  limit: null,
  limit_remaining: null,
  limit_reset: null,
  ...over,
});

const spend = (over: Partial<SpendInfo> = {}): SpendInfo => ({
  day: "2026-11-02",
  month: "2026-11",
  providers: [
    { provider: "anthropic", today_usd: 0.25, month_usd: 1.5, calls: 4, unknown_cost_calls: 0 },
    { provider: "openrouter", today_usd: 0.01, month_usd: 0.5, calls: 2, unknown_cost_calls: 1 },
  ],
  openrouter: router(),
  ...over,
});

describe("spend figures", () => {
  it("takes OpenRouter's own month when it gave one, the ledger otherwise", () => {
    const row = spend().providers[1];
    expect(monthUsd(row, router())).toBe(6.25);
    expect(monthUsd(row, null)).toBe(0.5);
    expect(monthUsd(spend().providers[0], router())).toBe(1.5);
  });

  it("turns amber under a tenth of the limit left and red at none", () => {
    expect(spendTone(router())).toBeUndefined();
    expect(spendTone(router({ limit: 20, limit_remaining: 5 }))).toBeUndefined();
    expect(spendTone(router({ limit: 20, limit_remaining: 1.5 }))).toBe("warn");
    expect(spendTone(router({ limit: 20, limit_remaining: 0 }))).toBe("danger");
  });
});

describe("SpendPill", () => {
  it("names each provider's month on the pill and the detail in the card", async () => {
    render(<SpendPill spend={spend()} compact={false} />);
    const pill = screen.getByTestId("spend");
    expect(pill).toHaveTextContent("Claude $1.50 · OpenRouter $6.25");
    await userEvent.click(pill);
    const card = screen.getByRole("dialog", { name: vi.spend.title });
    expect(card).toHaveTextContent(vi.spend.month("2026-11"));
    expect(card).toHaveTextContent(vi.spend.today("$0.25"));
    expect(card).toHaveTextContent(vi.spend.unpriced(1));
    expect(card).toHaveTextContent(vi.spend.routerReported);
    expect(card).toHaveTextContent(vi.spend.routerNoLimit);
    expect(card).toHaveTextContent(vi.spend.claudeNote);
  });

  it("shows the total alone on a phone and the limit left in the card", async () => {
    const tight = spend({ openrouter: router({ limit: 20, limit_remaining: 1 }) });
    render(<SpendPill spend={tight} compact />);
    const pill = screen.getByTestId("spend");
    expect(pill).toHaveTextContent("$7.75");
    expect(pill).toHaveClass("warn");
    await userEvent.click(pill);
    expect(screen.getByRole("dialog")).toHaveTextContent(vi.spend.routerLeft("$1.00", "$20.00"));
  });

  it("says so when OpenRouter's report could not be read", async () => {
    render(<SpendPill spend={spend({ openrouter: null })} compact={false} />);
    expect(screen.getByTestId("spend")).toHaveTextContent("OpenRouter $0.50");
    await userEvent.click(screen.getByTestId("spend"));
    expect(screen.getByRole("dialog")).toHaveTextContent(vi.spend.routerUnread);
  });
});

describe("SpendChip", () => {
  let backend: FakeBackend;
  beforeEach(() => {
    backend = new FakeBackend();
    vitest.stubGlobal("fetch", backend.fetch);
  });
  afterEach(() => vitest.useRealTimers());

  it("stays hidden with nothing to report and asks again on its interval", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    render(<SpendChip />);
    await act(async () => {});
    expect(screen.queryByTestId("spend")).toBeNull();
    backend.spend = spend();
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(SPEND_POLL_MS);
    });
    expect(screen.getByTestId("spend")).toHaveTextContent("Claude $1.50");
    expect(backend.requests.filter((r) => r.path === "/spend")).toHaveLength(2);
  });
});
