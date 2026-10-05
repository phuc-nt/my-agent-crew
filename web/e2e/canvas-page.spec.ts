import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, coachAgent, defaultAgent, mockApi } from "./mock-api";

const { canvas } = vi;
const NOTE = "00aa00aa00aa";
const PLAN = "00ff00ff00ff";
const GONE = "0000000000ff";
const TEXT = "Dòng một\nDòng hai\n";
// A title with nowhere to break, wider than a phone.
const LONG_TITLE = `Biên bản ${"kéodàikhôngngắt".repeat(8)}`;

const SCREENS = [
  ["a wide screen", { viewport: { width: 1440, height: 900 } }],
  ["a phone", { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }],
] as const;

function chat(id: string, title: string): Conversation {
  return {
    id, agent_id: "default", channel: "", title, summary: "", created_at: "2026-09-19T08:00:00Z", updated_at: "2026-09-19T08:00:00Z",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle",
    over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** Two canvases, the first used in two conversations, the second with a name too long for a phone. */
async function serve(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: LONG_TITLE, agent_id: "coach", content: "Việc một" });
  fake.add({ id: NOTE, title: "Ghi chú họp", content: TEXT, conversationIds: ["c2", "c1"] });
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    conversations: [chat("c1", "Tóm tắt tuần"), chat("c2", "Việc nhà")],
    canvas: fake,
  });
  return fake;
}

const editor = (page: Page) => page.getByRole("textbox", { name: canvas.editor });
const back = (page: Page) => page.getByRole("button", { name: canvas.back });
const rows = (page: Page) => page.getByTestId("canvas-library-row");

/** What a person would have to scroll sideways to read: the page, the section, or a part of the canvas's page. */
function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [document.documentElement, ...document.querySelectorAll<HTMLElement>(".manage-body, .canvas-page, .canvas-header, .canvas-page-used")]
      .filter((el) => el.scrollWidth > el.clientWidth)
      .map((el) => `${el.tagName.toLowerCase()}.${el.className} ${el.scrollWidth}>${el.clientWidth}`),
  );
}

/** Where the page, its panel and the section around them sit on the screen, in pixels. */
function placed(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => (document.querySelector(selector) as HTMLElement).getBoundingClientRect();
    const body = document.querySelector(".manage-body") as HTMLElement;
    const panel = box(".canvas-page .canvas-panel");
    return {
      screen: window.innerHeight,
      // The foot of what the section has to give: its own, less the padding it keeps under its content.
      sectionFoot: box(".manage-body").bottom - Number.parseFloat(getComputedStyle(body).paddingBottom),
      sectionScrolls: body.scrollHeight > body.clientHeight + 1,
      pageTop: box(".canvas-page").top,
      pageFoot: box(".canvas-page").bottom,
      panelTop: panel.top,
      panelFoot: panel.bottom,
      panel: panel.height,
      header: box(".canvas-page .canvas-header").height,
      editor: box(".canvas-page .canvas-editor").height,
      usedTop: box(".canvas-page-used").top,
    };
  });
}

for (const [name, screen] of SCREENS) {
  test.describe(`a canvas's own page on ${name}`, () => {
    test.use(screen);

    test("is opened from its name in the library, fills what the screen has left, and is still there after a reload", async ({ page }) => {
      await serve(page);
      await page.goto("/#/manage/canvas");
      await expect(rows(page)).toHaveCount(2);

      await page.getByRole("button", { name: "Ghi chú họp", exact: true }).click();

      await expect(page).toHaveURL(new RegExp(`#/manage/canvas/${NOTE}$`));
      await expect(editor(page)).toHaveValue(TEXT);
      await expect(page.getByRole("heading", { level: 2, name: "Ghi chú họp" })).toBeVisible();
      await expect(rows(page)).toHaveCount(0);

      // The page reaches the foot of the section without making it scroll; the panel is all of it
      // down to the line under it, and the text is all of the panel that its header leaves.
      const at = await placed(page);
      expect(Math.abs(at.pageFoot - at.sectionFoot)).toBeLessThan(1);
      expect(at.sectionScrolls).toBe(false);
      expect(at.panelTop).toBe(at.pageTop);
      expect(at.usedTop - at.panelFoot).toBeGreaterThanOrEqual(0);
      expect(at.usedTop - at.panelFoot).toBeLessThan(16);
      expect(at.panel).toBeGreaterThan(at.screen / 2);
      expect(at.panel - at.header - at.editor).toBeLessThan(40);
      expect(at.editor).toBeGreaterThan(at.header);
      expect(await overflowing(page)).toEqual([]);

      await page.reload();
      await expect(page).toHaveURL(new RegExp(`#/manage/canvas/${NOTE}$`));
      await expect(editor(page)).toHaveValue(TEXT);
    });

    test("is left at once with words not yet saved, and the save still reaches the server", async ({ page }) => {
      const fake = await serve(page);
      await page.goto(`/#/manage/canvas/${NOTE}`);
      await expect(editor(page)).toHaveValue(TEXT);
      const release = fake.holdNext("PUT", "request");

      await editor(page).fill(`${TEXT}Dòng ba\n`);
      await back(page).click();

      await expect(page).toHaveURL(/#\/manage\/canvas$/);
      await expect(rows(page)).toHaveCount(2);
      expect(fake.content(NOTE)).toBe(TEXT);

      await release();
      await expect.poll(() => fake.content(NOTE)).toBe(`${TEXT}Dòng ba\n`);
      await expect(page.getByRole("alert")).toHaveCount(0);
    });

    test("says above the library that a save left behind was refused, and keeps the words on the device", async ({ page }) => {
      const fake = await serve(page);
      await page.goto(`/#/manage/canvas/${NOTE}`);
      await expect(editor(page)).toHaveValue(TEXT);
      fake.refuseNext("PUT", 503);

      await editor(page).fill(`${TEXT}Dòng ba\n`);
      await back(page).click();

      const notice = page.getByRole("alert");
      await expect(notice).toContainText(canvas.handoffFailed("Ghi chú họp", true));
      await expect(rows(page)).toHaveCount(2);
      expect(fake.content(NOTE)).toBe(TEXT);
      expect(await overflowing(page)).toEqual([]);

      // The draft is what the page opens on again.
      await page.getByRole("button", { name: "Ghi chú họp", exact: true }).click();
      await expect(editor(page)).toHaveValue(`${TEXT}Dòng ba\n`);
    });

    test("names the conversations the canvas is used in, and opens the one chosen", async ({ page }) => {
      await serve(page);
      await page.goto(`/#/manage/canvas/${NOTE}`);

      const used = page.locator(".canvas-page-used");
      await expect(used).toContainText(canvas.usedIn(2));
      await expect(used.getByRole("button")).toHaveText(["Việc nhà", "Tóm tắt tuần"]);
      expect(await overflowing(page)).toEqual([]);

      await used.getByRole("button", { name: "Việc nhà" }).click();
      await expect(page).toHaveURL(/#\/chat\/c2$/);
    });

    test("keeps a name too long for the screen inside it", async ({ page }) => {
      await serve(page);
      await page.goto(`/#/manage/canvas/${PLAN}`);

      // An agent wrote this one, so it opens to be read.
      await expect(page.getByRole("heading", { level: 2, name: LONG_TITLE })).toBeVisible();
      await expect(page.locator(".canvas-page .canvas-body")).toContainText("Việc một");
      await expect(page.locator(".canvas-page-used")).toHaveCount(0);
      expect(await overflowing(page)).toEqual([]);
    });

    test("says a canvas that is gone is gone, and still leads back to the library", async ({ page }) => {
      await serve(page);
      await page.goto(`/#/manage/canvas/${GONE}`);

      await expect(page.getByRole("alert")).toContainText(canvas.gone);
      await expect(page.locator(".canvas-page-used")).toHaveCount(0);
      expect(await overflowing(page)).toEqual([]);

      await back(page).click();
      await expect(page).toHaveURL(/#\/manage\/canvas$/);
      await expect(rows(page)).toHaveCount(2);
    });
  });
}

test("an address naming what is no canvas's id shows the library and asks the server nothing about it", async ({ page }) => {
  await serve(page);
  const asked: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.startsWith("/api/artifacts/")) asked.push(pathname);
  });

  await page.goto("/#/manage/canvas/..%2F..%2Fsettings");

  await expect(rows(page)).toHaveCount(2);
  await expect(back(page)).toHaveCount(0);
  // The build under test runs each read twice, so it is which addresses were asked that is told.
  expect([...new Set(asked)]).toEqual(["/api/artifacts/usage"]);
});

test("an address cut short in the middle of an escape shows the library instead of a blank screen", async ({ page }) => {
  await serve(page);
  const broke: string[] = [];
  page.on("pageerror", (error) => broke.push(error.message));

  await page.goto("/#/manage/canvas/%E0%A4%A");

  await expect(rows(page)).toHaveCount(2);
  await expect(back(page)).toHaveCount(0);
  expect(broke).toEqual([]);
});

test.describe("the canvas open beside a conversation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("opens on its own page in a new tab cut off from this one, once what was typed is saved", async ({ page, context }) => {
    const fake = await serve(page);
    await page.goto("/#/chat/c1");
    await page.getByRole("button", { name: canvas.buttonLabel(1) }).click();
    await page.getByRole("button", { name: /Ghi chú họp/ }).click();
    await expect(editor(page)).toHaveValue(TEXT);

    const own = page.getByRole("button", { name: canvas.openStandalone });
    // Unsaved words would not be on the page that opens: the way there waits for the save.
    const release = fake.holdNext("PUT", "request");
    await editor(page).fill(`${TEXT}Dòng ba\n`);
    await expect(own).toBeDisabled();
    await release();
    await expect.poll(() => fake.content(NOTE)).toBe(`${TEXT}Dòng ba\n`);
    await expect(own).toBeEnabled();

    const opening = context.waitForEvent("page");
    await own.click();
    const tab = await opening;

    await tab.waitForLoadState("domcontentloaded");
    expect(new URL(tab.url()).hash).toBe(`#/manage/canvas/${NOTE}`);
    // The new tab was opened cut off from the one that opened it: it cannot reach back, nor tell where it came from.
    expect(await tab.evaluate(() => ({ opener: window.opener, referrer: document.referrer }))).toEqual({ opener: null, referrer: "" });
    await expect(page).toHaveURL(/#\/chat\/c1$/);
  });
});
