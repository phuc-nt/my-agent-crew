import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

const liveRun = run({
  id: "live",
  agent_id: "coach",
  source: "job:coach/brief",
  status: "running",
  finished_at: null,
  spent_usd: 0,
  summary: "",
  steps: [
    { kind: "tool", name: "shell_run", tool_call_id: "tc", arguments: { command: "date" }, ok: null, output: null, duration_ms: null },
  ],
});

test("the activity rail shows a live job with its steps and the finished one afterwards", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [run({ id: "old", summary: "Đã xong hôm qua" })],
    stream: [
      { type: "snapshot", runs: [liveRun] },
      { type: "event", run_id: "live", agent_id: "coach", conversation_id: null, status: "running", event: { type: "tool_result", tool_call_id: "tc", name: "shell_run", ok: true, output: "Fri" } },
      { type: "event", run_id: "live", agent_id: "coach", conversation_id: null, status: "running", event: { type: "assistant_message", message_id: "m", content: "Hôm nay thứ sáu.", tool_calls: [], provider: "openrouter", model: "deepseek", cost_usd: 0.002 } },
    ],
  });
  await page.goto("/");
  const panel = page.getByTestId("activity-panel");
  const live = panel.getByTestId("run-card").filter({ hasText: "HLV sức khoẻ" });
  await expect(live).toHaveAttribute("data-status", "running");
  await expect(live.getByTestId("run-step")).toHaveCount(2);
  await expect(live.getByTestId("run-step").first()).toContainText("shell_run");
  await expect(live.getByTestId("run-step").first()).toContainText("xong");
  await expect(live.getByTestId("run-step").nth(1)).toContainText("deepseek");
  await expect(live).toContainText("$0.002");
  await expect(page.getByTestId("status-line")).toContainText("Đang chạy: 1");
  await expect(panel.getByTestId("run-card").filter({ hasText: "Đã xong hôm qua" })).toHaveAttribute("data-status", "done");
});

test("jobs tab lists schedules and run-now posts to the server", async ({ page }) => {
  const mock = await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    jobs: [{ ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: "2026-09-20T00:00:00Z", last_run: null, running: false }],
    stats: { runs: 2, model_calls: 5, spent_usd: 0.25, unknown_cost_calls: 0, by_agent: { coach: 0.2, default: 0.05 }, by_model: { deepseek: 0.25 }, by_day: { "2026-09-19": 0.25 } },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "Lịch chạy" }).click();
  const job = page.getByTestId("job");
  await expect(job).toContainText("Bản tin sáng");
  await expect(job).toContainText("0 7 * * *");
  await job.getByRole("button", { name: /Chạy ngay/ }).click();
  await expect.poll(() => mock.posted.some((r) => r.path === "/jobs/coach/brief/run")).toBe(true);
  await page.getByRole("tab", { name: "Chi phí" }).click();
  await expect(page.getByTestId("stats")).toContainText("$0.25");
  await expect(page.getByTestId("stats")).toContainText("HLV sức khoẻ");
});

test("agent switcher scopes the list and new conversations to that agent", async ({ page }) => {
  const mock = await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    conversations: [
      { id: "c1", agent_id: "default", title: "Chung", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 1, skills: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null },
      { id: "c2", agent_id: "coach", title: "Sức khoẻ", created_at: "", updated_at: "", autonomous: true, cost_cap_usd: 1, skills: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null },
    ],
  });
  await page.goto("/");
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("button", { name: /Chung|Sức khoẻ/ })).toHaveCount(2);
  await nav.getByRole("radio", { name: /HLV sức khoẻ/ }).click();
  await expect(nav.getByRole("button", { name: /Chung/ })).toHaveCount(0);
  await nav.getByRole("button", { name: /Cuộc trò chuyện mới/ }).click();
  await expect.poll(() => mock.posted.find((r) => r.path === "/conversations")?.body).toEqual({ agent_id: "coach" });
  await expect(page.locator(".agent-badge")).toHaveText("HLV sức khoẻ");
});
