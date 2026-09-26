import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const { kind: _kind, ...briefRow } = coachAgent.schedules[0];

/** Coach, with the schedules its profile file declares. */
function declaring(...schedules: object[]) {
  return { ...coachAgent, declared: { delegates: [], schedules } };
}

test.describe("on a phone", () => {
  // A touch screen at the width people hold: the pointer is coarse, as on an iPhone.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("every schedule box is big enough to type in without the page zooming", async ({ page }) => {
    await mockApi(page, { agents: [master, declaring(briefRow)] });
    await page.goto("/#/manage/crew/coach/schedules");
    const editor = page.getByTestId("agent-editor");
    const row = editor.getByTestId("schedule-row").first();
    await row.getByRole("button", { name: "Lệnh shell" }).tap();
    await editor.getByLabel("Bật kênh Telegram").check();

    // Safari zooms the page into any field under 16px when it takes focus.
    const boxes = [
      row.getByLabel("Mã", { exact: true }),
      row.getByLabel("Cron", { exact: true }),
      row.getByLabel("Lệnh shell", { exact: true }),
      editor.getByLabel("Lịch gom ghi nhớ (cron)", { exact: true }),
      editor.getByLabel("Mã cuộc trò chuyện (chat_id)", { exact: true }),
    ];
    for (const box of boxes) {
      const size = await box.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
      expect(size, (await box.getAttribute("aria-label")) ?? "").toBeGreaterThanOrEqual(16);
      expect((await box.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    }

    // The switch says what it does on the screen, not only to a screen reader.
    await expect(row.locator(".schedule-switch")).toHaveText("Bật lịch");
    await expect(row.getByText("Bật lịch", { exact: true })).toBeVisible();
    const add = editor.getByRole("button", { name: "+ Thêm lịch" });
    expect((await add.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});

test("Xoá pressed twice in a row removes one schedule, by mouse or by keyboard", async ({ page }) => {
  const rows = ["a", "b", "c"].map((id) => ({ ...briefRow, id, name: `Lịch ${id}` }));
  await mockApi(page, { agents: [master, declaring(...rows)] });
  await page.goto("/#/manage/crew/coach/schedules");
  const editor = page.getByTestId("agent-editor");
  const names = editor.getByTestId("schedule-row").getByLabel("Tên", { exact: true });
  await expect(names).toHaveCount(3);

  // The second click lands on the Xoá of the row that moved up under the pointer.
  await editor.getByRole("button", { name: "Xoá lịch Lịch a" }).dblclick();
  await expect(names).toHaveCount(2);
  await expect(names.first()).toHaveValue("Lịch b");

  // By keyboard, focus moves off the removed row to the name of the one that took its
  // place, where a second Enter removes nothing.
  await editor.getByRole("button", { name: "Xoá lịch Lịch b" }).focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await expect(names).toHaveCount(1);
  await expect(names.first()).toHaveValue("Lịch c");
  await expect(names.first()).toBeFocused();
});
