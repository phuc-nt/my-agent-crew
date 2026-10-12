import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeScriptStore } from "../src/test/fake-script-store";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";
import { spills } from "./spills";

// A real browser folds a line break, a tab and a run of spaces into one space, drops a space
// a text ends with, and does the same to the name it hands a screen reader. Keys that differ
// only in those would be one key on the page, so each is written out, the same way wherever
// it is drawn, named or asked about.

const { scriptStore: words } = vi;
const STORE = '[data-testid="script-store"]';
const BRIEF = 'lịch "Bản tin sáng"';

/** A key as it is kept, and as the page writes it. */
const KEYS: Array<[string, string]> = [
  ["a b", "a b"],
  ["a  b", "a[U+0020][U+0020]b"],
  ["a b ", "a b[U+0020]"],
  [" a b", "[U+0020]a b"],
  ["a\nb", "a\\nb"],
  ["a\r\nb", "a\\r\\nb"],
  ["a\tb", "a\\tb"],
  ["a\u0085b", "a\\u0085b"],
  ["a b", "a\\u2028b"],
  ["a b", "a[U+00A0]b"],
  // Written out, a key of nothing but spaces is eight times as long, and still has to wrap.
  [" ".repeat(120), "[U+0020]".repeat(120)],
];
const WRITTEN = KEYS.map(([, written]) => written);

async function open(page: Page, store: FakeScriptStore) {
  for (const [key] of KEYS) store.keep("coach", "job:brief", key, 1);
  await mockApi(page, { agents: [defaultAgent, coachAgent], scriptStore: store });
  await page.goto("/#/manage/memory/scripts/coach");
  await expect(page.locator(".script-store-key")).toHaveCount(KEYS.length);
}

const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`keys a page would draw alike, at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("are each drawn their own way, inside the page's width", async ({ page }) => {
      await open(page, new FakeScriptStore());

      // What the page draws of each row, white space folded as it folds it.
      const drawn = await page.locator(".script-store-key").evaluateAll((rows) => rows.map((row) => (row as HTMLElement).innerText));

      expect([...drawn].sort()).toEqual([...WRITTEN].sort());
      expect(await spills(page, STORE)).toEqual([]);
    });

    test("each have buttons of their own by the name a screen reader is given", async ({ page }) => {
      await open(page, new FakeScriptStore());

      for (const written of WRITTEN) {
        await expect(button(page, words.viewLabel(written))).toHaveCount(1);
        await expect(button(page, words.deleteKeyLabel(written))).toHaveCount(1);
      }
      await button(page, words.viewLabel("a\\nb")).click();
      await expect(page.getByRole("group", { name: words.valueLabel("a\\nb"), exact: true })).toBeVisible();
      await expect(button(page, words.hideLabel("a\\nb"))).toHaveCount(1);
      await expect(button(page, words.viewLabel("a\\nb"))).toHaveCount(0);
    });

    test("are asked about in the writing the row has, and only the one asked about goes", async ({ page }) => {
      const store = new FakeScriptStore();
      const asked: string[] = [];
      page.on("dialog", (dialog) => {
        asked.push(dialog.message());
        void dialog.accept();
      });
      await open(page, store);

      await button(page, words.deleteKeyLabel("a b[U+0020]")).click();

      await expect(page.locator(STORE).getByRole("status")).toHaveText(words.deletedKey('"a b[U+0020]"'));
      expect(asked).toEqual([words.deleteKeyConfirm('"a b[U+0020]"', BRIEF)]);
      expect(store.keys("coach", "job:brief")).toEqual(KEYS.map(([key]) => key).filter((key) => key !== "a b ").sort());
    });
  });
}
