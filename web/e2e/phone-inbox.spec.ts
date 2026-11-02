import { expect, test } from "@playwright/test";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";

test.use({ viewport: { width: 390, height: 844 } });

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
  summary: "Hôm qua ngủ 7 giờ 10 phút, nhịp tim nghỉ 58. Hôm nay nên đi bộ nhẹ 30 phút và ngủ trước 23 giờ.",
});
// What the chat was sent: longer than the summary, and formatted.
const words = [
  "**Hôm qua** ngủ 7 giờ 10 phút, nhịp tim nghỉ 58.",
  "- Đi bộ nhẹ 30 phút\n- Ngủ trước 23 giờ",
  ...Array.from({ length: 12 }, (_, n) => `Ghi chú ${n + 1}: một dòng nữa để bản tin dài hơn một màn hình.`),
].join("\n\n");
const quiet = run({ id: "check", source: "job:check", conversation_id: "j2", title: "Kiểm tra ổ đĩa", summary: "OK" });

// The daily loop from a phone, with no chat app: the badge says something came in, the
// inbox settles the request in place and opens the report in its conversation.
test("the inbox settles a request and opens a job's report from a phone", async ({ page }) => {
  const pending = {
    id: "ap1", conversation_id: "c2", message_id: "m", tool_call_id: "tc", tool_name: "write_file",
    arguments: { path: "notes/ke-hoach.md" }, status: "pending", created_at: "",
    expires_at: new Date(Date.now() + 5 * 60_000).toISOString(), resolved_at: null,
  };
  const mock = await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    conversations: [
      conversation("c1", "Chung"),
      { ...conversation("c2", "Ôn thi"), status: "awaiting_approval", pending_approval: pending },
      conversation("j1", "Bản tin sáng", "coach"),
    ],
    runs: [run({ id: "waiting", conversation_id: "c2", status: "awaiting_approval", finished_at: null, summary: "" }), morning, quiet],
    reports: [{ run_id: "morning", text: words }],
    turns: [[{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }]],
  });
  await page.goto("/");

  const open = page.getByRole("button", { name: /^Mở hộp thư/ });
  await expect(open).toHaveAccessibleName("Mở hộp thư (2 mục mới hoặc đang chờ)");
  await open.click();
  await expect(page).toHaveURL(/#\/inbox$/);

  const report = page.getByRole("article", { name: /^Bản tin sáng/ });
  await expect(report).toContainText("Mới");
  await expect(report.locator("strong", { hasText: "Hôm qua" })).toBeVisible();
  await expect(report.getByRole("listitem")).toHaveCount(2);
  await expect(report).not.toContainText("[lịch]");
  await expect(page.getByText("Kiểm tra ổ đĩa")).toHaveCount(0);
  // Long, so it opens folded and unfolds in place.
  await expect(report.locator(".inbox-report-body")).toHaveClass(/folded/);
  await report.getByRole("button", { name: "Xem hết" }).click();
  await expect(report.locator(".inbox-report-body")).not.toHaveClass(/folded/);
  await expect(report.getByRole("button", { name: "Thu gọn" })).toBeVisible();
  for (const name of ["Thu gọn", "Mở cuộc trò chuyện của Bản tin sáng để trả lời"]) {
    const box = await report.getByRole("button", { name }).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(40);
  }
  const [scrollWidth, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scrollWidth).toBeLessThanOrEqual(width);

  const row = page.getByTestId("attention-row");
  await row.getByRole("button", { name: "Cho phép" }).click();
  await expect(row).toHaveCount(0);
  expect(mock.posted).toContainEqual({ path: "/conversations/c2/approvals/ap1", body: { approve: true } });

  await report.getByRole("button", { name: "Mở cuộc trò chuyện của Bản tin sáng để trả lời" }).click();
  await expect(page).toHaveURL(/#\/chat\/j1$/);
  await expect(page.getByRole("button", { name: "Mở hộp thư" })).toBeVisible();
});
