import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";

const { canvas } = vi;
const PLAN = "00ff00ff00ff";
// A path and a title with nowhere to break, each wider than a phone.
const LONG_PATH = `notes/${"rat-dai-".repeat(14)}ke-hoach.md`;
const LONG_TITLE = `Biên bản ${"kéodàikhôngngắt".repeat(8)}`;

const SCREENS = [
  ["a wide screen", { viewport: { width: 1440, height: 900 } }],
  ["a phone", { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }],
] as const;

/** The library over three canvases: an agent's from a workspace file, a person's, and one with a long name. */
async function openLibrary(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: "Kế hoạch tuần", agent_id: "coach", content: "Việc một", source: `workspace:coach/${LONG_PATH}` });
  fake.add({ title: "Ghi chú họp", content: "abc" });
  fake.add({ title: LONG_TITLE, kind: "code", language: "python", content: "print(1)" });
  await mockApi(page, { agents: [defaultAgent, coachAgent], canvas: fake });
  await page.goto("/#/manage/canvas");
  await expect(page.getByTestId("canvas-library-row")).toHaveCount(3);
  return fake;
}

/** What a person would have to scroll sideways to read: the page, the section, the library or a row of it. */
function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [document.documentElement, ...document.querySelectorAll<HTMLElement>(".manage-body, .canvas-library, .canvas-library-row")]
      .filter((el) => el.scrollWidth > el.clientWidth)
      .map((el) => `${el.tagName.toLowerCase()}.${el.className} ${el.scrollWidth}>${el.clientWidth}`),
  );
}

for (const [name, screen] of SCREENS) {
  test.describe(`the canvas library on ${name}`, () => {
    test.use(screen);

    test("lists every canvas with who made it and where it came from, inside the screen's width", async ({ page }) => {
      await openLibrary(page);
      const rows = page.getByTestId("canvas-library-row");

      // Newest first, whatever conversation each was written in.
      await expect(rows.nth(0)).toContainText(LONG_TITLE);
      await expect(rows.nth(0).locator(".badge")).toHaveText(`${canvas.kinds.code} · python`);
      await expect(rows.nth(1)).toContainText(`${canvas.libraryCreatedBy} ${canvas.you}`);
      await expect(rows.nth(2)).toContainText(`${canvas.libraryCreatedBy} ${coachAgent.name}`);
      await expect(rows.nth(2).locator(".canvas-library-source")).toHaveText(`${coachAgent.name}/${LONG_PATH}`);
      await expect(rows.nth(2)).toContainText(`12 B ${canvas.libraryAllVersions}`);
      await expect(page.locator(".canvas-library-total")).toHaveText(canvas.libraryTotal(3, "23 B", "1 GB"));
      // Where a canvas came from is said, not linked.
      await expect(page.getByTestId("canvas-library").getByRole("link")).toHaveCount(0);

      expect(await overflowing(page)).toEqual([]);
    });

    test("finds a canvas by its name, and every canvas again once the box is empty", async ({ page }) => {
      await openLibrary(page);
      const rows = page.getByTestId("canvas-library-row");
      const box = page.getByRole("searchbox", { name: canvas.librarySearch });

      await box.fill("ke hoach");
      await expect(rows).toHaveCount(1);
      await expect(rows).toContainText("Kế hoạch tuần");

      await box.fill("không có tên này");
      await expect(page.getByText(canvas.libraryNoMatch)).toBeVisible();
      await expect(rows).toHaveCount(0);

      await box.fill("");
      await expect(rows).toHaveCount(3);
    });

    test("deletes a canvas only after the person says yes", async ({ page }) => {
      const fake = await openLibrary(page);
      const rows = page.getByTestId("canvas-library-row");
      const said = page.getByTestId("canvas-library").getByRole("status");
      // The room between the search box's line and the list, against the gap the column keeps.
      const spare = () =>
        page.getByTestId("canvas-library").evaluate((library) => {
          const head = library.querySelector(".canvas-library-head")?.getBoundingClientRect().bottom ?? 0;
          const list = library.querySelector(".canvas-library-list")?.getBoundingClientRect().top ?? 0;
          return Math.round(list - head - Number.parseFloat(getComputedStyle(library).rowGap));
        });
      const asked: string[] = [];
      let answer = false;
      page.on("dialog", (dialog) => {
        asked.push(dialog.message());
        void (answer ? dialog.accept() : dialog.dismiss());
      });
      const remove = page.getByRole("button", { name: canvas.deleteLabel("Kế hoạch tuần") });

      await remove.click();
      await expect.poll(() => asked).toEqual([canvas.deleteConfirm("Kế hoạch tuần")]);
      await expect(rows).toHaveCount(3);
      expect(fake.canvases.has(PLAN)).toBe(true);
      // The line that says what was deleted takes no room until it has something to say.
      await expect(said).toHaveText("");
      expect(await spare()).toBe(0);

      answer = true;
      await remove.click();
      await expect(rows).toHaveCount(2);
      await expect(rows.filter({ hasText: "Kế hoạch tuần" })).toHaveCount(0);
      expect(fake.canvases.has(PLAN)).toBe(false);
      // The row the keyboard was on was the last: the keyboard is on the row before it, and a line
      // says which canvas went.
      await expect(page.getByRole("button", { name: "Ghi chú họp", exact: true })).toBeFocused();
      await expect(said).toHaveText(canvas.libraryDeleted("Kế hoạch tuần"));
      await expect(said).toBeVisible();
      expect(await spare()).toBeGreaterThan(0);
      await expect(page.locator(".canvas-library-total")).toHaveText(canvas.libraryTotal(2, "11 B", "1 GB"));
    });
  });
}

test("the canvas library is reached from the crew's part of the manage screen", async ({ page }) => {
  await mockApi(page, { agents: [defaultAgent] });
  await page.goto("/#/manage/memory");

  await page.getByRole("navigation", { name: vi.manage.nav }).getByRole("button", { name: canvas.tab }).click();

  await expect(page).toHaveURL(/#\/manage\/canvas$/);
  await expect(page.getByRole("heading", { level: 2, name: canvas.tab })).toBeVisible();
  await expect(page.getByText(canvas.libraryEmpty)).toBeVisible();
});
