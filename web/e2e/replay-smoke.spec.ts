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
  await expect(replay).toContainText("path=notes.md");
  expect(page.url()).toContain("#/manage/activity/older");

  // Reloading the link is the whole point of putting the run in the URL.
  await page.reload();
  await expect(page.getByTestId("run-replay").getByTestId("run-card")).toContainText("Dọn kho");

  await page.getByRole("button", { name: "← Tất cả hoạt động" }).click();
  await expect(page.getByTestId("run-replay")).toHaveCount(0);
  await expect(page.getByTestId("manage-screen")).toContainText("Gần đây");
});

// Runs recorded before the store kept arguments as a mapping hold them as one string.
// Those rows are still in the database, and walking a string by index showed a row per
// character — so the reader has to cope with the shape it actually finds.
test("a run recorded with its arguments flattened still reads as one line", async ({ page }) => {
  const legacy = run({
    id: "legacy",
    title: "Lượt cũ",
    steps: [
      { kind: "tool", name: "read_file", tool_call_id: "tc", arguments: "{'path': 'memory/2026-09-19.md'}", ok: true, output: "", duration_ms: 8 },
    ],
  });
  await mockApi(page, { agents: [defaultAgent], runs: [legacy] });
  await page.goto("/#/manage/activity/legacy");

  const replay = page.getByTestId("run-replay");
  await expect(replay.getByTestId("run-card")).toContainText("Lượt cũ");
  await expect(replay).toContainText("{'path': 'memory/2026-09-19.md'}");
  // The failure this guards: one row per character of that string.
  await expect(replay).not.toContainText("0={");
});

test("a link to a run that is gone says so instead of showing nothing", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent], runs: [] });
  await page.goto("/#/manage/activity/vanished");

  await expect(page.getByRole("status")).toContainText("Không tìm thấy lượt chạy vanished.");
});
