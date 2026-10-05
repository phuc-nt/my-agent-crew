import { expect, type Locator, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { ask, card, piece } from "./writing-turn";

const text = vi.canvas.writing;
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc một';

/** The words, the size and the dot between them on the card's line, once the first piece is in. */
async function line(page: Parameters<typeof ask>[0]) {
  const { turn } = await ask(page);
  await turn.push(piece(HEAD));
  const words = card(page).getByText(text.creating);
  const size = card(page).getByText(text.written(""));
  await expect(size).toBeVisible();
  return { words, size, dot: card(page).getByText("·", { exact: true }) };
}

const top = async (part: Locator) => (await part.boundingBox())?.y ?? Number.NaN;
const edges = async (part: Locator) => {
  const box = await part.boundingBox();
  return box === null ? null : { left: box.x, right: box.x + box.width };
};

test.describe("the line of a canvas being written, on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("puts the size on a row of its own, which does not start with the dot that parts it from the words", async ({ page }) => {
    const { words, size, dot } = await line(page);

    // The size is a row lower than the words: the card is too narrow for both.
    expect(await top(size)).toBeGreaterThan((await top(words)) + 8);
    await expect(dot).toHaveCount(1);
    await expect(dot).not.toBeInViewport();
    await expect(size).toBeInViewport({ ratio: 0.8 });
  });
});

test.describe("the line of a canvas being written, on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("keeps the words and the size on one row, the dot between them", async ({ page }) => {
    const { words, size, dot } = await line(page);

    expect(Math.abs((await top(size)) - (await top(words)))).toBeLessThan(4);
    await expect(dot).toBeInViewport({ ratio: 1 });
    const [before, between, after] = [await edges(words), await edges(dot), await edges(size)];
    expect(between?.left).toBeGreaterThanOrEqual(before?.right ?? Number.NaN);
    expect(between?.right).toBeLessThanOrEqual(after?.right ?? Number.NaN);
  });
});
