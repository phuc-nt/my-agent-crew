import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

// What the model providers have cost this month, kept in the header on a desk and a phone.
const spend = {
  day: "2026-11-02",
  month: "2026-11",
  providers: [
    { provider: "anthropic", today_usd: 0.25, month_usd: 1.5, calls: 4, unknown_cost_calls: 0 },
    { provider: "openrouter", today_usd: 0.01, month_usd: 0.5, calls: 2, unknown_cost_calls: 0 },
  ],
  openrouter: {
    usage: 30, usage_daily: 0.4, usage_weekly: 2, usage_monthly: 6.25,
    limit: 20, limit_remaining: 13.75, limit_reset: "monthly",
  },
};
const conversation = {
  id: "c1", agent_id: "default", channel: "", title: "Chung", summary: "", created_at: "", updated_at: "",
  autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0.2, unknown_cost_calls: 0,
  status: "idle", over_budget: false, parent_call_id: "", messages: [], pending_approval: null,
};

test("the desk header names each provider's month and opens the detail", async ({ page }) => {
  await mockApi(page, { spend, conversations: [conversation] });
  await page.goto("/#/chat/c1");
  const pill = page.getByTestId("spend");
  await expect(pill).toHaveText(/Claude \$1\.50 · OpenRouter \$6\.25/);
  await pill.click();
  const card = page.getByRole("dialog", { name: "Chi phí model" });
  await expect(card).toContainText("Hôm nay $0.25");
  await expect(card).toContainText("Còn $13.75 / hạn mức $20.00");
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the month's total stays on the folded title row without a sideways scroll", async ({ page }) => {
    await mockApi(page, { spend, conversations: [conversation] });
    await page.goto("/#/chat/c1");
    const pill = page.locator(".header-title").getByTestId("spend");
    await expect(pill).toHaveText(/\$7\.75/);
    await expect(pill).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await pill.click();
    await expect(page.getByRole("dialog", { name: "Chi phí model" })).toBeInViewport();
  });

  test("with no conversation open the pill sits beside the crew", async ({ page }) => {
    await mockApi(page, { spend });
    await page.goto("/");
    await expect(page.getByTestId("spend")).toHaveText(/Claude \$1\.50/);
  });
});
