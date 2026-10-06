import type { Page } from "@playwright/test";

/** Boxes under `within` whose content reaches past their own edge: text with nowhere to
 *  break. A box further out may clip what spills, so the page's own width does not show it. */
export const spills = (page: Page, within: string) =>
  page.evaluate((within) => {
    const found: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>(`${within}, ${within} *`)) {
      if (el.clientWidth === 0 || el.scrollWidth <= el.clientWidth + 1) continue;
      found.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} ${el.scrollWidth}>${el.clientWidth}`);
    }
    return found;
  }, within);
