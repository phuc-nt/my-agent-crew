import { expect, test, type Page } from "@playwright/test";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { smallTargets } from "./small-targets";

// A touch screen at the width people hold, where a finger is the pointer.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

function conversation(id: string, title: string): Conversation {
  return {
    id, agent_id: "default", channel: "", title, summary: "", created_at: "2026-09-19T08:00:00Z", updated_at: "2026-09-19T08:00:00Z",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0.2, unknown_cost_calls: 0, status: "idle",
    over_budget: false, parent_call_id: "", pending_approval: null,
    messages: [
      { id: "m1", seq: 1, role: "user", content: "Tóm tắt giúp tôi", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "2026-09-19T08:00:00Z" },
      { id: "m2", seq: 2, role: "assistant", tool_call_id: null, name: null, provider: "fake", model: "echo", cost_usd: 0.01, content: "Đây là bản tóm tắt, xem [nguồn](https://example.com).", tool_calls: [], created_at: "2026-09-19T08:00:05Z" },
    ],
  };
}

const waiting = run({
  id: "wait", conversation_id: "c1", status: "awaiting_approval", finished_at: null,
  pending: { call_id: "k1", tool_name: "shell", arguments: { command: "ls" }, kind: "approval", expires_at: null },
});
const failed = run({ id: "bad", conversation_id: "c1", status: "failed", summary: "Lỗi" });
const job = {
  ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach",
  next_run: "2026-09-20T00:00:00Z", last_run: null, running: false, paused: false,
};

async function open(page: Page, hash: string) {
  await mockApi(page, {
    agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent],
    conversations: [conversation("c1", "Tóm tắt tuần"), conversation("c2", "Việc nhà")],
    runs: [waiting, failed, run({ id: "ok", conversation_id: "c2" })],
    jobs: [job],
  });
  await page.goto(hash);
}

const PAGES: [string, string][] = [
  ["the chat", "/#/chat/c1"],
  ["activity", "/#/manage/activity"],
  ["approvals", "/#/manage/approvals"],
  ["costs", "/#/manage/costs"],
  ["crew", "/#/manage/crew"],
  ["an agent's editor", "/#/manage/crew/coach"],
  ["tools", "/#/manage/tools"],
  ["jobs", "/#/manage/jobs"],
  ["memory", "/#/manage/memory"],
  ["connections", "/#/manage/connections"],
  ["settings", "/#/manage/settings"],
];

for (const [name, hash] of PAGES) {
  test(`every control on ${name} is big enough for a finger`, async ({ page }) => {
    await open(page, hash);
    await expect(page.locator("main").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await smallTargets(page)).toEqual([]);
  });
}

test("every control in the phone's conversation drawer is big enough for a finger", async ({ page }) => {
  await open(page, "/#/chat/c1");
  await page.getByRole("button", { name: /^Mở danh sách cuộc trò chuyện/ }).tap();
  await expect(page.locator(".sidebar")).not.toHaveAttribute("inert");
  await expect(page.locator(".sidebar").getByRole("button", { name: /Việc nhà/ })).toBeInViewport();
  expect(await smallTargets(page)).toEqual([]);
});
