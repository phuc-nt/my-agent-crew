import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

// Not a smoke test: this exists to put the timeline in front of a human. It
// renders one live run, one finished run and one that died mid-tool, then
// writes a screenshot. Run with `npx playwright test shot`.

const liveRun = run({
  id: "live",
  agent_id: "coach",
  conversation_id: "c1",
  status: "running",
  title: "Tìm sách cho tuần này",
  started_at: new Date(Date.now() - 42_000).toISOString(),
  finished_at: null,
  spent_usd: 0.0183,
  summary: "Đang tra cứu Goodreads…",
  steps: [
    { kind: "model", chars: 310, provider: "openrouter", model: "sonnet", cost_usd: 0.004, tool_calls: ["web_search"], preview: "Tôi sẽ tìm vài đầu sách hợp với mục tiêu đọc của anh.", duration_ms: 2100 },
    { kind: "tool", name: "web_search", tool_call_id: "t1", arguments: { query: "sách hay 2026" }, ok: true, output: "10 kết quả", duration_ms: 820 },
    { kind: "tool", name: "web_search", tool_call_id: "t2", arguments: { query: "sách hay 2026" }, ok: true, output: null, duration_ms: 760 },
    { kind: "tool", name: "web_search", tool_call_id: "t3", arguments: { query: "sách hay 2026" }, ok: true, output: null, duration_ms: 790 },
    { kind: "tool", name: "web_search", tool_call_id: "t4", arguments: { query: "sách hay 2026" }, ok: true, output: null, duration_ms: 810 },
    { kind: "fallback", provider: "openrouter", model: "glm-5.3-flash", error: "HTTP 429 quá tải", duration_ms: 120 },
    { kind: "tool", name: "delegate", tool_call_id: "t5", arguments: { target: "coder", task: "Dựng bảng so sánh" }, ok: true, output: "xong", duration_ms: 12_400 },
    { kind: "tool", name: "shell_run", tool_call_id: "t6", arguments: { command: "python3 rank.py --top 5" }, ok: null, output: null, duration_ms: null },
  ],
});

const deadRun = run({
  id: "dead",
  agent_id: "coach",
  conversation_id: "c1",
  status: "error",
  title: "Đồng bộ ghi chú",
  started_at: "2026-09-22T06:10:00Z",
  finished_at: "2026-09-22T06:10:31Z",
  spent_usd: 0.0021,
  summary: "Hết hạn mức.",
  steps: [
    { kind: "model", chars: 90, provider: "openrouter", model: "haiku", cost_usd: 0.0002, tool_calls: ["read_file"], preview: "Đọc ghi chú trước.", duration_ms: 640 },
    { kind: "tool", name: "read_file", tool_call_id: "d1", arguments: { path: "notes.md" }, ok: true, output: null, duration_ms: 30 },
    { kind: "tool", name: "workspace_write", tool_call_id: "d2", arguments: { path: "out.md" }, ok: false, output: "permission denied", duration_ms: 12 },
    { kind: "tool", name: "shell_run", tool_call_id: "d3", arguments: { command: "sync" }, ok: null, output: null, duration_ms: null },
  ],
});

const doneRun = run({
  id: "done",
  agent_id: "default",
  conversation_id: "c1",
  status: "done",
  title: "Bản tin sáng",
  started_at: "2026-09-22T00:00:00Z",
  finished_at: "2026-09-22T00:00:09Z",
  spent_usd: 0.0064,
  summary: "Đã gửi bản tin.",
  steps: [
    { kind: "model", chars: 420, provider: "openrouter", model: "sonnet", cost_usd: 0.0064, tool_calls: [], preview: "Chào buổi sáng! Hôm nay có ba việc đáng chú ý.", duration_ms: 3200 },
  ],
});

test("timeline screenshot", async ({ page }) => {
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    runs: [liveRun, deadRun, doneRun],
    conversations: [
      {
        id: "c1", agent_id: "default", channel: "", title: "Sách tuần này", created_at: "", updated_at: "",
        autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0.02,
        unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null,
      },
    ],
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("run-card").first()).toBeVisible();
  // Give the shimmer and the breathing node a moment to be mid-cycle.
  await page.waitForTimeout(900);
  await page.screenshot({ path: "test-results/timeline.png", fullPage: false });

  const panel = page.locator(".activity-panel");
  await panel.screenshot({ path: "test-results/timeline-panel.png" });

  // Dark mode is a separate palette, not an inverted one, so it has to be
  // looked at rather than assumed. Every token has a dark value; a rule that
  // slipped a raw colour past review only shows up here.
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/timeline-dark.png", fullPage: false });
  await panel.screenshot({ path: "test-results/timeline-panel-dark.png" });
});
