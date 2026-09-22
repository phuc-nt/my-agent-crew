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

test("the activity section shows a live job with its steps and the finished one afterwards", async ({ page }) => {
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
  // While reading the thread, the count of what is running is all that reaches the person.
  await expect(page.getByTestId("status-line")).toContainText("Đang chạy: 1");

  await page.getByRole("button", { name: /Quản lý/ }).click();
  const panel = page.getByTestId("manage-screen");
  const live = panel.getByTestId("run-card").filter({ hasText: "HLV sức khoẻ" });
  await expect(live).toHaveAttribute("data-status", "running");
  await expect(live.getByTestId("run-step")).toHaveCount(2);
  await expect(live.getByTestId("run-step").first()).toContainText("shell_run");
  await expect(live.getByTestId("run-step").first()).toContainText("xong");
  await expect(live.getByTestId("run-step").nth(1)).toContainText("deepseek");
  await expect(live).toContainText("$0.002");
  await expect(panel.getByTestId("run-card").filter({ hasText: "Đã xong hôm qua" })).toHaveAttribute("data-status", "done");
});

test("the jobs section lists schedules and run-now posts to the server", async ({ page }) => {
  const mock = await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    jobs: [{ ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: "2026-09-20T00:00:00Z", last_run: null, running: false, paused: false }],
    stats: {
      runs: 2, model_calls: 5, spent_usd: 0.25, unknown_cost_calls: 0, by_agent: { coach: 0.2, default: 0.05 }, by_model: { deepseek: 0.25 }, by_day: { "2026-09-19": 0.25 },
      days: [{ day: "2026-09-19", calls: 5, cost_usd: 0.25, prompt_tokens: 900, completion_tokens: 120, unknown_cost_calls: 0 }],
      models: [{ model: "openrouter:deepseek", calls: 5, cost_usd: 0.25, prompt_tokens: 900, completion_tokens: 120, unknown_cost_calls: 0 }],
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Quản lý/ }).click();
  await page.getByRole("button", { name: "Lịch chạy" }).click();
  const job = page.getByTestId("job");
  await expect(job).toContainText("Bản tin sáng");
  await expect(job).toContainText("0 7 * * *");
  await job.getByRole("button", { name: /Chạy ngay/ }).click();
  await expect.poll(() => mock.posted.some((r) => r.path === "/jobs/coach/brief/run")).toBe(true);
  await job.getByRole("checkbox", { name: /Bật lịch/ }).click();
  await expect(job).toContainText("tạm dừng");
  await page.getByRole("button", { name: "Chi phí" }).click();
  await expect(page.getByTestId("stats")).toContainText("$0.25");
  await expect(page.getByTestId("stats")).toContainText("HLV sức khoẻ");
  await expect(page.getByTestId("stat-models")).toContainText("openrouter:deepseek");
  await expect(page.getByTestId("stat-days")).toContainText("900 vào / 120 ra");
});

test("the list holds only the master's conversations and new ones are created for it", async ({ page }) => {
  const mock = await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    conversations: [
      { id: "c1", agent_id: "default", channel: "", title: "Chung", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null },
      { id: "c2", agent_id: "coach", channel: "", title: "Sức khoẻ", created_at: "", updated_at: "", autonomous: true, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null },
    ],
  });
  await page.goto("/");
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("button", { name: /Chung/ })).toHaveCount(1);
  await expect(nav.getByRole("button", { name: /Sức khoẻ/ })).toHaveCount(0);
  await expect(nav.getByRole("radio")).toHaveCount(0);
  await nav.getByRole("button", { name: /Cuộc trò chuyện mới/ }).click();
  await expect.poll(() => mock.posted.find((r) => r.path === "/conversations")?.body).toEqual({ agent_id: "default" });
  await expect(page.locator(".agent-badge")).toHaveText("Agent");
});

function conversation(id: string, title: string) {
  return {
    id, title, agent_id: "default", channel: "", created_at: "", updated_at: "", autonomous: false,
    cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, messages: [], pending_approval: null,
  };
}

test("going back from the crew's work returns to the conversation that was open", async ({ page }) => {
  await mockApi(page, { conversations: [conversation("c1", "Chung"), conversation("c2", "Ôn thi")] });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /Ôn thi/ }).click();
  await expect(page).toHaveURL(/#\/chat\/c2$/);

  await page.getByRole("button", { name: /Quản lý/ }).click();
  await expect(page.getByTestId("manage-screen")).toBeVisible();

  // Leaving the crew's work is going back, so it lands on the thread that was being read
  // rather than on the welcome screen.
  await page.getByRole("button", { name: "← Chat" }).click();
  await expect(page).toHaveURL(/#\/chat\/c2$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ôn thi");
});

test("the badge for work waiting on a person opens the conversation holding it", async ({ page }) => {
  await mockApi(page, {
    conversations: [conversation("c1", "Chung"), conversation("c2", "Ôn thi")],
    runs: [run({ id: "waiting", conversation_id: "c2", status: "awaiting_approval", finished_at: null, summary: "" })],
  });
  await page.goto("/");

  // The count on the way into the crew's work is what tells the person there is something
  // to decide; following it has to end at the conversation that is waiting.
  const manage = page.getByRole("button", { name: /Quản lý/ });
  await expect(manage).toContainText("1");
  await manage.click();

  const attention = page.getByTestId("attention");
  await expect(attention).toContainText("đang chờ bạn duyệt");
  await attention.getByRole("button", { name: "Mở cuộc trò chuyện" }).click();

  await expect(page).toHaveURL(/#\/chat\/c2$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ôn thi");
});
