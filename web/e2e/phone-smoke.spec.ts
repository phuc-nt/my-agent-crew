import { expect, test } from "@playwright/test";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";

// A phone, not a narrow desktop window: the width people actually hold.
test.use({ viewport: { width: 390, height: 844 } });

const older = run({ id: "older", agent_id: "coach", title: "Dọn kho", summary: "Đã xong hôm qua" });

/**
 * Nothing may be wider than the screen.
 *
 * A single over-wide element gives the whole page a horizontal scrollbar, and
 * then every tap-target drifts as the person scrolls sideways looking for it.
 * Asserting on the document's own scroll width catches that wherever it comes
 * from, which a per-element width assertion would not.
 */
async function widestOverflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const offenders: string[] = [];
    for (const el of document.querySelectorAll("*")) {
      const box = el.getBoundingClientRect();
      if (box.width > window.innerWidth + 1 && box.height > 0) {
        offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
      }
    }
    return { scrollWidth: document.documentElement.scrollWidth, width: window.innerWidth, offenders };
  });
}

test("the conversation fits the screen, with the sidebar above it rather than beside it", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [] });
  await page.goto("/");

  // Both are on screen at once: at this width the sidebar is a strip on top, not
  // a drawer, so switching conversation stays one tap.
  const sidebar = page.locator(".sidebar");
  const thread = page.locator(".thread");
  await expect(sidebar).toBeVisible();
  await expect(thread).toBeVisible();

  const above = await sidebar.boundingBox();
  const below = await thread.boundingBox();
  expect(above && below && above.y + above.height).toBeLessThanOrEqual((below?.y ?? 0) + 1);

  // And the composer is still reachable rather than pushed off the bottom.
  await expect(page.getByRole("textbox")).toBeVisible();

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("the manage sections stay reachable when the nav has no room to stack", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity");

  // The nav turns into one scrolling row; every section must still be clickable.
  await expect(page.getByTestId("manage-screen")).toBeVisible();
  await page.getByRole("button", { name: /Đội/ }).click();
  await expect(page).toHaveURL(/#\/manage\/crew/);

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("a run opened on its own still fits, timeline and all", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [older] });
  await page.goto("/#/manage/activity/older");

  await expect(page.getByTestId("run-replay")).toBeVisible();
  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});

test("connections fit, keys, host defaults and an open key field included", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent, coachAgent] });
  await page.goto("/#/manage/connections");

  // Opened, a row is at its widest: the field and its two buttons share one line.
  const router = page.getByTestId("credential-OPENROUTER_API_KEY");
  await router.getByRole("button", { name: "Thay" }).click();
  await expect(router.getByLabel("Giá trị cho OPENROUTER_API_KEY")).toBeVisible();
  await expect(page.getByTestId("credential-OLLAMA_BASE_URL")).toContainText("11434");

  const overflow = await widestOverflow(page);
  expect(overflow.offenders).toEqual([]);
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.width);
});
