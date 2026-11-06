import { expect, test } from "@playwright/test";
import { type Conversation, defaultAgent, coachAgent, mockApi, run } from "./mock-api";

test.use({ viewport: { width: 1280, height: 800 } });

function conversation(id: string, title: string, agent = "default"): Conversation {
  return {
    id, agent_id: agent, channel: "", title, summary: "", created_at: "", updated_at: "", autonomous: false,
    cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle",
    over_budget: false, parent_call_id: "", messages: [], pending_approval: null,
  };
}

const morning = run({
  id: "morning", agent_id: "coach", source: "job:morning", conversation_id: "j1",
  title: "[lịch] Bản tin sáng · 2026-11-02 07:00",
  finished_at: new Date(Date.now() - 60 * 60_000).toISOString(),
  summary: "Hôm qua ngủ 7 giờ 10 phút.",
});

// A wide screen reaches the same inbox from the sidebar's foot, over the manage button, and
// the badge drops what was read once the person comes back.
test("a wide screen opens the inbox from the sidebar and reads a job's report there", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    conversations: [conversation("c1", "Chung"), conversation("j1", "Bản tin sáng", "coach")],
    runs: [morning],
    reports: [{ run_id: "morning", text: "**Hôm qua** ngủ 7 giờ 10 phút.\n\n- Đi bộ nhẹ 30 phút" }],
    turns: [[{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }]],
  });
  await page.goto("/#/chat/c1");

  const open = page.getByRole("button", { name: /^Mở hộp thư/ });
  await expect(open).toHaveAccessibleName("Mở hộp thư (1 mục mới hoặc đang chờ)");
  await expect(page.locator(".sidebar-foot").getByRole("button", { name: /^Mở hộp thư/ })).toBeVisible();
  // The sidebar stays a column: no drawer button on a wide screen.
  await expect(page.locator(".menu-button")).toHaveCount(0);
  await open.click();
  await expect(page).toHaveURL(/#\/inbox$/);

  const report = page.getByRole("article", { name: /^Bản tin sáng/ });
  await expect(report).toContainText("Mới");
  await expect(report.locator("strong", { hasText: "Hôm qua" })).toBeVisible();
  // The column stays readable rather than stretching across the screen.
  const box = await report.boundingBox();
  expect(box?.width ?? 0).toBeLessThanOrEqual(44 * 16 + 1);

  await page.getByRole("button", { name: "Về cuộc trò chuyện" }).click();
  await expect(page).toHaveURL(/#\/chat\/c1$/);
  await expect(page.getByRole("button", { name: "Mở hộp thư" })).toBeVisible();
});
