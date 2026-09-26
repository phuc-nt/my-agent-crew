import { expect, type Locator, test } from "@playwright/test";
import { mockApi } from "./mock-api";

// What the chat says about its own state, held the way a phone holds it.
test.use({ viewport: { width: 390, height: 844 } });

/** The vertical middle of the text an element starts with, rather than of its box: a box
 *  stretched by its row centres whatever its text does. */
function textMiddle(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el.firstChild!);
    const box = range.getBoundingClientRect();
    return box.top + box.height / 2;
  });
}

// The stream is held until the test lets the mock answer it, and the answer ends at once,
// so the pill is caught while it connects and again once the drop offers a retry.
test("the retry takes no room of its own, so the composer stays put when the stream drops", async ({ page }) => {
  await mockApi(page);
  let answer = () => {};
  const held = new Promise<void>((resolve) => (answer = resolve));
  await page.route(/^https?:\/\/[^/]+\/api\/activity\/stream$/, async (route) => {
    await held;
    await route.fallback();
  });
  await page.goto("/");
  const line = page.getByTestId("status-line");
  const state = page.getByTestId("stream-state");
  const composer = page.getByRole("textbox");
  await expect(state).toContainText("đang kết nối");
  const lineBefore = (await line.boundingBox())!;
  const composerBefore = (await composer.boundingBox())!;

  answer();
  const retry = line.getByRole("button", { name: "Thử lại kết nối trực tiếp" });
  await expect(retry).toBeVisible();
  expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(40);
  expect((await line.boundingBox())!.height).toBe(lineBefore.height);
  expect((await composer.boundingBox())!.y).toBe(composerBefore.y);
  // The thread's side of the line sits level with the stream's.
  expect(Math.abs((await textMiddle(line.locator("span").first())) - (await textMiddle(state)))).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(844);
});
