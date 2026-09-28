import { expect, test, type Page } from "@playwright/test";
import { mockApi, run } from "./mock-api";

// A phone, where the manage sections are one row of pills scrolled sideways.
test.use({ viewport: { width: 390, height: 844 } });

/**
 * The live stream, made in the page so a test can speak on it when it chooses. The mock's
 * stream says everything the moment the page opens, and these counts have to change later,
 * once the row sits where the test wants it.
 */
async function liveStream(page: Page) {
  await page.addInitScript(() => {
    const opened: EventTarget[] = [];
    class Stream extends EventTarget {
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor() {
        super();
        opened.push(this);
        setTimeout(() => {
          this.onopen?.(new Event("open"));
          this.dispatchEvent(new MessageEvent("snapshot", { data: JSON.stringify({ type: "snapshot", runs: [] }) }));
        });
      }
      close() {}
    }
    Object.assign(window, {
      EventSource: Stream,
      say: (payload: { type: string }) => {
        for (const stream of opened) stream.dispatchEvent(new MessageEvent(payload.type, { data: JSON.stringify(payload) }));
      },
    });
  });
}

/**
 * Opens a section once the page's font is in. A font landing after the current pill was
 * placed widens every pill, which would move the row for a reason no count explains.
 */
async function arrive(page: Page, section: string, label: string) {
  await liveStream(page);
  await mockApi(page);
  await page.goto("/#/manage/crew");
  await expect(page.locator(".manage-nav-groups")).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await page.evaluate((hash) => (location.hash = hash), `#/manage/${section}`);
  await expect(page.locator('.manage-nav-groups [aria-current="page"]')).toContainText(label);
}

/** Tells the page a run changed, as the server's stream does. */
const runChanged = (page: Page, id: string, status: string) =>
  page.evaluate(
    (changed) => (window as unknown as { say: (payload: object) => void }).say({ type: "run", run: changed }),
    run({ id, status, conversation_id: `c-${id}`, finished_at: status === "running" ? null : "2026-09-19T08:00:05Z" }),
  );

/** How far the row is scrolled, and whether the named pill lies wholly inside it. */
const rowAt = (page: Page, pill: string) =>
  page.locator(".manage-nav-groups").evaluate((row, name) => {
    const button = [...row.querySelectorAll("button")].find((b) => b.textContent?.includes(name));
    const box = row.getBoundingClientRect();
    const at = button!.getBoundingClientRect();
    return { scrollLeft: row.scrollLeft, inView: at.left >= box.left - 1 && at.right <= box.right + 1 };
  }, pill);

const activityBadges = (page: Page) => page.getByRole("button", { name: /Hoạt động/ }).locator(".badge");

test("a count arriving leaves the row where the person scrolled it", async ({ page }) => {
  await arrive(page, "activity", "Hoạt động");
  const row = page.locator(".manage-nav-groups");

  // Swiped to the far end, reaching for the last section, as a run starts...
  await row.evaluate(
    (el) =>
      new Promise<void>((done) => {
        el.addEventListener("scroll", () => done(), { once: true });
        el.scrollLeft = el.scrollWidth;
      }),
  );
  const reached = await rowAt(page, "Cài đặt");
  expect(reached.inView).toBe(true);
  await runChanged(page, "live", "running");
  await expect(activityBadges(page)).toHaveCount(1);

  // ...and the row stays there: snapping back to the current pill put another under the finger.
  expect((await rowAt(page, "Cài đặt")).scrollLeft).toBe(reached.scrollLeft);
});

test("the current pill stays in view as the counts before it widen the row", async ({ page }) => {
  await arrive(page, "settings", "Cài đặt");
  expect((await rowAt(page, "Cài đặt")).inView).toBe(true);

  await runChanged(page, "live", "running");
  await runChanged(page, "broke", "error");
  await expect(activityBadges(page)).toHaveCount(2);

  expect((await rowAt(page, "Cài đặt")).inView).toBe(true);
});
