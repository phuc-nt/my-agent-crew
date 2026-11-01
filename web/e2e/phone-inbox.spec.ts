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
  id: "morning", agent_id: "coach", source: "job:morning", conversation_id: "j1", title: "Bản tin sáng",
  finished_at: new Date(Date.now() - 60 * 60_000).toISOString(),
  summary: "Hôm qua ngủ 7 giờ 10 phút, nhịp tim nghỉ 58. Hôm nay nên đi bộ nhẹ 30 phút và ngủ trước 23 giờ.",
});
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
    turns: [[{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }]],
  });
  await page.goto("/");

  const open = page.getByRole("button", { name: /^Mở hộp thư/ });
  await expect(open).toHaveAccessibleName("Mở hộp thư (2 mục mới hoặc đang chờ)");
  await open.click();
  await expect(page).toHaveURL(/#\/inbox$/);

  const result = page.getByRole("button", { name: /^Bản tin sáng/ });
  await expect(result).toContainText("Mới");
  await expect(page.getByText("Kiểm tra ổ đĩa")).toHaveCount(0);
  const [scrollWidth, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scrollWidth).toBeLessThanOrEqual(width);

  const row = page.getByTestId("attention-row");
  await row.getByRole("button", { name: "Cho phép" }).click();
  await expect(row).toHaveCount(0);
  expect(mock.posted).toContainEqual({ path: "/conversations/c2/approvals/ap1", body: { approve: true } });

  await result.click();
  await expect(page).toHaveURL(/#\/chat\/j1$/);
  await expect(page.getByRole("button", { name: "Mở hộp thư" })).toBeVisible();
});
