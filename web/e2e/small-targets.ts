import type { Page } from "@playwright/test";

const MIN = 40;

/**
 * Every control on screen that a finger could miss: narrower or shorter than 40px, measured
 * on what takes the tap — a checkbox inside a label is tapped through its label, so the label
 * is measured. A link inside running text is exempt, as WCAG exempts it: growing it would
 * push the lines of the sentence apart. `within` narrows the search to one region.
 */
export async function smallTargets(page: Page, within = "body"): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  return page.evaluate(
    ([min, within]) => {
      const root = document.querySelector(within);
      // A region that is not there is reported, so a scoped check never passes on nothing.
      if (!root) return [`no ${within} on screen`];
      const found: string[] = [];
      const controls = root.querySelectorAll<HTMLElement>(
        "button, a[href], input:not([type=hidden]), select, textarea, summary, [role=switch], [role=tab]",
      );
      for (const el of controls) {
        const style = getComputedStyle(el);
        if (style.visibility === "hidden" || el.closest("[inert], [aria-hidden=true]")) continue;
        const target = el.closest("label") ?? el;
        const box = target.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        const inline = el.tagName === "A" && getComputedStyle(el).display === "inline" && el.parentElement?.closest("p, li, td");
        if (inline) continue;
        if (box.width >= min && box.height >= min) continue;
        const name = (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30);
        found.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} "${name}" ${Math.round(box.width)}×${Math.round(box.height)}`);
      }
      return found;
    },
    [MIN, within] as const,
  );
}
