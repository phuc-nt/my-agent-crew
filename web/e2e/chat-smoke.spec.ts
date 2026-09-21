import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

test("send a message and read the streamed reply", async ({ page }) => {
  await mockApi(page, { turns: [[
    { type: "text_delta", text: "Xin chào" },
    { type: "assistant_message", message_id: "a1", content: "Xin chào từ agent", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0.05, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2 })).toContainText("Xin chào");
  await page.getByRole("textbox").fill("hello");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-user")).toHaveText(/hello/);
  await expect(page.getByTestId("message-assistant")).toContainText("Xin chào từ agent");
  await expect(page.getByTestId("budget")).toContainText("$0.05 / $1.00");
});

test("approval bar pauses the turn and approving resumes it", async ({ page }) => {
  await mockApi(page, { turns: [
    [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "write_file", arguments: { path: "a.md" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: { path: "a.md" } },
    ],
    [
      { type: "tool_result", tool_call_id: "tc", name: "write_file", ok: true, output: "ok" },
      { type: "assistant_message", message_id: "a2", content: "Đã ghi.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ],
  ] });
  await page.goto("/");
  await page.getByRole("textbox").fill("ghi tệp");
  await page.keyboard.press("Enter");
  const bar = page.getByRole("alertdialog");
  await expect(bar).toContainText("write_file");
  await expect(page.getByRole("textbox")).toBeDisabled();
  await bar.getByRole("button", { name: "Cho phép", exact: true }).click();
  await expect(page.getByTestId("message-assistant")).toContainText("Đã ghi.");
  await expect(page.getByTestId("tool-card")).toContainText("xong");
  await expect(page.getByRole("textbox")).toBeEnabled();
});

test("settings drawer lists routes and key presence", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Cài đặt/ }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("fake:echo");
  await expect(drawer).toContainText("chưa có");
  await expect(drawer).toContainText("Asia/Ho_Chi_Minh");
  await drawer.getByRole("button", { name: "Đóng" }).click();
  await expect(drawer).toHaveCount(0);
});
