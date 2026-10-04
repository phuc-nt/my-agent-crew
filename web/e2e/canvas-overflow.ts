import type { Page } from "@playwright/test";

/** The parts of the canvas a phone must not have to scroll sideways, the list of a page's errors among them. */
const PARTS = ".canvas-dock, .canvas-header, .canvas-body, .canvas-errors-list";

/** What a phone would scroll sideways: the page, or a part of the canvas wider than its room. */
export function overflowing(page: Page): Promise<string[]> {
  return page.evaluate(
    (parts) =>
      [document.documentElement, ...document.querySelectorAll<HTMLElement>(parts)]
        .filter((el) => el.scrollWidth > el.clientWidth)
        .map((el) => `${el.tagName.toLowerCase()}.${el.className} ${el.scrollWidth}>${el.clientWidth}`),
    PARTS,
  );
}
