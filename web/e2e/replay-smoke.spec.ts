import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

const older = run({
  id: "older",
  agent_id: "coach",
  title: "Dọn kho",
  summary: "Đã xong hôm qua",
  steps: [
    { kind: "tool", name: "read_file", tool_call_id: "tc", arguments: { path: "notes.md" }, ok: true, output: "hai dòng", duration_ms: 20 },
  ],
});

test("a run opens on its own from its link, and the address bar keeps it", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/");
  await page.getByRole("button", { name: /Quản lý/ }).click();

  const panel = page.getByTestId("manage-screen");
  await panel.getByTestId("run-card").filter({ hasText: "Dọn kho" }).click();
  await panel.getByRole("button", { name: "Xem riêng" }).click();

  const replay = page.getByTestId("run-replay");
  await expect(replay).toBeVisible();
  await expect(replay.getByTestId("run-card")).toHaveCount(1);
  // The arguments read as names and values; stored as one string they came back as a row
  // per character.
  await expect(replay).toContainText("path=notes.md");
  expect(page.url()).toContain("#/manage/activity/older");

  // Reloading the link is the whole point of putting the run in the URL.
  await page.reload();
  await expect(page.getByTestId("run-replay").getByTestId("run-card")).toContainText("Dọn kho");

  await page.getByRole("button", { name: "← Tất cả hoạt động" }).click();
  await expect(page.getByTestId("run-replay")).toHaveCount(0);
  await expect(page.getByTestId("manage-screen")).toContainText("Gần đây");
});

test("a link to a run that is gone says so instead of showing nothing", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent], runs: [] });
  await page.goto("/#/manage/activity/vanished");

  await expect(page.getByRole("status")).toContainText("Không tìm thấy lượt chạy vanished.");
});
