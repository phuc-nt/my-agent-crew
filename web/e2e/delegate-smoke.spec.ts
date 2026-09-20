import { expect, test } from "@playwright/test";
import { coderTemplate, devAgent, mockApi, run } from "./mock-api";

const RESULT = "conversation=c-child status=done spent=$0.0250 steps=4\nĐã dọn xong hai tệp.";

test("a handed-off task reads as a job, not as a tool call", async ({ page }) => {
  await mockApi(page, {
    agents: [devAgent],
    turns: [[
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "delegate", arguments: { agent: "coder", task: "Dọn mã trong web" } }], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "tool_call", tool_call_id: "tc", name: "delegate", arguments: { agent: "coder", task: "Dọn mã trong web" } },
      { type: "tool_result", tool_call_id: "tc", name: "delegate", ok: true, output: RESULT },
      { type: "done", spent_usd: 0.03, unknown_cost_calls: 0 },
    ]],
  });
  await page.goto("/");
  await page.getByRole("textbox").fill("dọn giúp tôi");
  await page.keyboard.press("Enter");

  const card = page.getByTestId("delegate-card");
  await expect(card).toContainText("Dọn mã trong web");
  await expect(card.getByTestId("delegate-status")).toHaveText("done");
  await expect(card).toContainText("$0.0250");
  await expect(card).toContainText("4 bước");
  // The header is bookkeeping; opening the output shows the child's answer instead.
  await card.getByRole("button", { name: "Xem kết quả" }).click();
  await expect(card).toContainText("Đã dọn xong hai tệp.");
  await expect(card).not.toContainText("conversation=c-child");
});

test("a work agent is badged, and its delegated run nests in the rail", async ({ page }) => {
  const parent = run({ id: "r1", conversation_id: "c1", source: "chat", title: "Dọn mã", status: "running", finished_at: null });
  const child = run({ id: "r2", agent_id: "coder", conversation_id: "c-child", source: "delegate:c1", title: "Sửa hai tệp", status: "running", finished_at: null });
  await mockApi(page, {
    agents: [devAgent],
    runs: [parent, child],
    conversations: [{ id: "c1", agent_id: "dev", channel: "", title: "Dọn mã", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 5, spent_usd: 0.1, unknown_cost_calls: 0, status: "idle", over_budget: false, summary: "", skills: [], auto_approve: [], parent_call_id: "", messages: [], pending_approval: null }],
  });
  await page.goto("/");

  const children = page.getByTestId("run-children").first();
  await expect(children.getByTestId("run-card")).toContainText("Sửa hai tệp");
  await page.getByRole("navigation").getByRole("button", { name: /Dọn mã/ }).click();
  await expect(page.getByTestId("work-badge")).toHaveAttribute("title", /cap \$5/);
});

test("settings shows the crew's roles and how to install a bundled one", async ({ page }) => {
  await mockApi(page, { agents: [devAgent], templates: [coderTemplate] });
  await page.goto("/");
  await page.getByRole("button", { name: /Cài đặt/ }).click();

  const drawer = page.getByRole("dialog");
  await expect(drawer.getByTestId("crew-list")).toContainText("giao được cho: coder");
  await expect(drawer.getByTestId("template-list")).toContainText(
    "python -m my_agent_crew agent add coder",
  );
});
