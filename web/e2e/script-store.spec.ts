import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeScriptStore } from "../src/test/fake-script-store";
import { coachAgent, type Conversation, defaultAgent, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

// What an agent's scripts keep between runs is as long as the scripts made it: a key with
// nowhere to break, a value of tens of thousands of characters, a namespace of sixty keys.
// None of it may push the page sideways, and a long value scrolls in its own box.

const { scriptStore: words } = vi;
const STORE = '[data-testid="script-store"]';
const LIST = "/api/agents/coach/script-store";

/** A key with nowhere to break, as a script that keys by a URL writes them. */
const LONG_KEY = `orders/${"k".repeat(300)}`;
/** Far taller than its box once set out, and each row a line with nowhere to break. */
const LONG_VALUE = Array.from({ length: 280 }, (_, id) => ({ id, url: `https://shop.example.test/orders/${"a".repeat(110)}` }));
const LONG_TITLE = `Đơn_hàng_tháng_mười_${"x".repeat(160)}`;

function conversation(id: string, title: string): Conversation {
  return {
    id, agent_id: "coach", channel: "", title, summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** Sixty keys and one long one under a schedule, near the limit; a conversation with a title
 *  that cannot break; a schedule the agent no longer declares; and a name of neither kind. */
function fullStore(): FakeScriptStore {
  const store = new FakeScriptStore();
  store.limitChars = 50_000;
  for (let i = 1; i <= 60; i += 1) store.keep("coach", "job:brief", `seen-${String(i).padStart(2, "0")}`, { order: i, done: i % 2 === 0 });
  store.keep("coach", "job:brief", LONG_KEY, LONG_VALUE);
  store.keep("coach", "conv:c1", "cursor", "x".repeat(900));
  store.keep("coach", "job:retired", "a", 1).keep("coach", "job:retired", "b", [2, 3]);
  store.keep("coach", "misc", "note", null);
  return store;
}

async function open(page: Page, store: FakeScriptStore) {
  await mockApi(page, { agents: [defaultAgent, coachAgent], conversations: [conversation("c1", LONG_TITLE)], scriptStore: store });
  await page.goto("/#/manage/memory/scripts/coach");
  await expect(page.getByRole("tab", { name: words.tab })).toHaveAttribute("aria-selected", "true");
}

const card = (page: Page, namespace: string) => page.locator(`[data-namespace="${namespace}"]`);
const box = (of: Locator) => of.evaluate((el) => el.getBoundingClientRect().toJSON() as DOMRect);

/** How far the page itself can scroll, down and sideways. */
const pageRoom = (page: Page) =>
  page.evaluate(() => {
    const root = document.documentElement;
    return { down: root.scrollHeight - window.innerHeight, across: root.scrollWidth - window.innerWidth };
  });

/** Nothing of the store reaches past its own box or past the screen, and the page has
 *  nowhere to scroll: the column the store stands in does the scrolling. */
async function fits(page: Page, width: number) {
  expect(await pageRoom(page)).toEqual({ down: 0, across: 0 });
  expect(await spills(page, STORE)).toEqual([]);
  const edges = await box(page.locator(STORE));
  expect(edges.left).toBeGreaterThanOrEqual(0);
  expect(edges.right).toBeLessThanOrEqual(width);
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 1000, height: 800 }, { width: 390, height: 844 }]) {
  test.describe(`the script store at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("holds long keys, a long title and many keys inside the screen", async ({ page }) => {
      await open(page, fullStore());

      const brief = card(page, "job:brief");
      await expect(brief.getByTestId("script-store-entry")).toHaveCount(61);
      await expect(brief.getByRole("heading")).toHaveText(`${words.kinds.job}Bản tin sáng`);
      await expect(brief.getByText(LONG_KEY)).toBeVisible();
      await expect(brief.getByText(words.nearLimit)).toBeVisible();
      await expect(brief.getByRole("progressbar")).toHaveClass(/warn/);
      await expect(card(page, "conv:c1").getByRole("link", { name: LONG_TITLE })).toBeVisible();
      await expect(card(page, "conv:c1").getByRole("progressbar")).toHaveClass(/accent/);
      await expect(card(page, "job:retired").getByText(words.orphan)).toBeVisible();
      await expect(card(page, "job:retired").getByText(words.orphanHint.job)).toBeVisible();
      await expect(card(page, "misc").getByRole("heading")).toHaveText(`${words.kinds.other}misc`);

      await fits(page, viewport.width);
      // A name is read as it was written: the stored name of a namespace tells cases apart.
      for (const name of await page.locator(".script-store-name").all()) await expect(name).toHaveCSS("text-transform", "none");
      // A key too long for a line takes one to itself, and its size and buttons drop under it.
      const long = brief.getByTestId("script-store-entry").filter({ hasText: LONG_KEY });
      const key = await box(long.locator(".script-store-key"));
      expect((await box(long.locator(".script-store-entry-meta"))).top).toBeGreaterThanOrEqual(key.bottom);
      expect(key.width).toBeGreaterThan((await box(long)).width * 0.9);
      // The preview of a value is a few lines, however long the value.
      expect((await box(long.getByTestId("script-store-preview"))).height).toBeLessThan(80);
      // Every namespace's delete stands at the card's right edge, whatever is beside it.
      for (const one of await page.getByTestId("script-store-namespace").all()) {
        const head = await box(one.locator(".script-store-namespace-head"));
        expect(Math.abs((await box(one.locator(".script-store-delete-all"))).right - head.right)).toBeLessThanOrEqual(1);
      }
      if (viewport.width <= 720) expect(await smallTargets(page, STORE)).toEqual([]);
    });

    test("scrolls a long value inside its own box, from the keyboard too", async ({ page }) => {
      await open(page, fullStore());
      const row = card(page, "job:brief").getByTestId("script-store-entry").filter({ hasText: LONG_KEY });

      await row.getByRole("button", { name: words.viewLabel(LONG_KEY) }).press("Enter");

      const value = row.getByTestId("script-store-value");
      await expect(value).toContainText('"id": 279');
      const size = await value.evaluate((el) => ({ tall: el.scrollHeight, shown: el.clientHeight }));
      expect(size.tall).toBeGreaterThan(size.shown * 5);
      await fits(page, viewport.width);
      if (viewport.width <= 720) expect(await smallTargets(page, STORE)).toEqual([]);

      // Tab leaves the view button for the delete beside it, then lands on the box.
      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      await expect(value).toBeFocused();
      await page.keyboard.press("End");
      await expect.poll(() => value.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
      expect(await pageRoom(page)).toEqual({ down: 0, across: 0 });
    });

    test("says what it is when the agent's scripts kept nothing", async ({ page }) => {
      await open(page, new FakeScriptStore());

      await expect(page.locator(STORE).getByTestId("empty-state")).toHaveText(words.empty);
      await expect(page.locator(STORE).getByText(words.intro)).toBeVisible();
      await fits(page, viewport.width);
      if (viewport.width <= 720) expect(await smallTargets(page, STORE)).toEqual([]);
    });

    test("says it is loading until the server answers", async ({ page }) => {
      let answer = () => {};
      const held = new Promise<void>((resolve) => {
        answer = resolve;
      });
      await mockApi(page, { agents: [defaultAgent, coachAgent], scriptStore: fullStore() });
      await page.route(new RegExp(`^https?://[^/]+${LIST}$`), async (route) => {
        await held;
        await route.fallback();
      });
      await page.goto("/#/manage/memory/scripts/coach");

      await expect(page.locator(STORE).getByText(vi.loading)).toBeVisible();
      await expect(page.getByTestId("script-store-namespace")).toHaveCount(0);
      await expect(page.locator(STORE).getByTestId("empty-state")).toHaveCount(0);
      await fits(page, viewport.width);

      answer();
      await expect(page.getByTestId("script-store-namespace")).toHaveCount(4);
      await expect(page.locator(STORE).getByText(vi.loading)).toHaveCount(0);
    });

    test("shows the usual error with a way to read again when the list cannot be read", async ({ page }) => {
      const store = fullStore();
      store.refuse.list = { status: 500, detail: "boom" };
      await open(page, store);

      const alert = page.locator(STORE).getByRole("alert");
      await expect(alert).toContainText(vi.requestErrors.server(500));
      await expect(page.locator(STORE).getByTestId("empty-state")).toHaveCount(0);
      await fits(page, viewport.width);
      if (viewport.width <= 720) expect(await smallTargets(page, STORE)).toEqual([]);

      store.refuse = {};
      await alert.getByRole("button", { name: vi.retry }).click();
      await expect(page.getByTestId("script-store-namespace")).toHaveCount(4);
      await expect(page.locator(STORE).getByRole("alert")).toHaveCount(0);
    });
  });
}
