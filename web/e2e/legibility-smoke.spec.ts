import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "./mock-api";

/**
 * What the eye and the keyboard can actually make out, measured on rendered pixels.
 *
 * jsdom computes no cascade, so contrast and focus rings only exist here. Each check mounts
 * a probe carrying the real class names into the running app, so it reads the same rules a
 * real screen does without needing the data that would make that screen appear.
 */

type Rgb = [number, number, number];

/** WCAG contrast of an element's text against the first solid background behind it. */
async function contrast(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate((el) => {
    const parse = (value: string): Rgb | null => {
      const m = value.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
      if (m) return m[4] !== undefined && Number(m[4]) === 0 ? null : [Number(m[1]), Number(m[2]), Number(m[3])];
      // A tint mixed with color-mix() computes to color(srgb …), with channels from 0 to 1.
      const mixed = value.match(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)(?: \/ ([\d.]+))?\)/);
      if (!mixed || (mixed[4] !== undefined && Number(mixed[4]) === 0)) return null;
      return [Number(mixed[1]) * 255, Number(mixed[2]) * 255, Number(mixed[3]) * 255];
    };
    const luminance = ([r, g, b]: Rgb) =>
      [r, g, b]
        .map((c) => c / 255)
        .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
        .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
    let node: Element | null = el;
    let background: Rgb | null = null;
    while (node && !background) {
      background = parse(getComputedStyle(node).backgroundColor);
      node = node.parentElement;
    }
    const text = parse(getComputedStyle(el).color) ?? [0, 0, 0];
    const [hi, lo] = [luminance(text), luminance(background ?? [255, 255, 255])].sort((a, b) => b - a);
    return (hi + 0.05) / (lo + 0.05);
  });
}

/** Mounts markup inside the app's own tree, where every stylesheet applies. */
async function probe(page: Page, html: string) {
  await page.evaluate((markup) => {
    const box = document.createElement("div");
    box.className = "probe";
    box.innerHTML = markup;
    document.body.prepend(box);
  }, html);
}

for (const scheme of ["light", "dark"] as const) {
  test(`text on filled and sunken surfaces reads at 4.5:1 in ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("main")).toBeVisible();
    await probe(
      page,
      `<button type="button" class="primary">Lưu</button>
       <span class="badge live">3</span>
       <span class="channel-tag">Telegram</span>
       <span class="step-repeat">×4</span>
       <pre class="diff"><div class="added">thêm</div></pre>
       <div class="approval-bar callout"><div class="args-detail">
         <button type="button" class="link-button args-detail-toggle">Xem đầy đủ</button>
       </div></div>`,
    );

    // The toggle to a tool call's full arguments is small text on the approval bar's tint.
    const toggle = ".probe .approval-bar .args-detail-toggle";
    for (const selector of [".probe .primary", ".probe .badge.live", ".probe .channel-tag", ".probe .step-repeat", ".probe .diff .added", toggle]) {
      expect(await contrast(page, selector), selector).toBeGreaterThanOrEqual(4.5);
    }

    // Hovering a primary button changes its fill; the ink has to survive that too.
    const button = page.locator(".probe .primary");
    const resting = await button.evaluate((el) => getComputedStyle(el).backgroundColor);
    await button.hover();
    await expect.poll(() => button.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(resting);
    await page.waitForTimeout(300);
    expect(await contrast(page, ".probe .primary")).toBeGreaterThanOrEqual(4.5);
  });
}

test("a keyboard-focused checkbox or switch keeps a visible ring, and so does the search box", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  await probe(
    page,
    `<input type="checkbox" aria-label="a" /><input type="checkbox" class="switch" aria-label="b" />
     <div class="conversation-search"><input type="search" aria-label="c" /></div>`,
  );

  // A checkbox or switch draws no border for a halo to colour, so its ring is the outline;
  // a text field's ring is the halo around the border it colours.
  const outline = (selector: string) =>
    page.locator(selector).evaluate((el) => {
      const style = getComputedStyle(el);
      return style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2 && style.outlineColor !== "rgba(0, 0, 0, 0)";
    });
  const halo = (selector: string) =>
    page.locator(selector).evaluate((el) => getComputedStyle(el).boxShadow !== "none");

  await page.locator(".probe input[type=checkbox]").first().focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(".probe .switch")).toBeFocused();
  expect(await outline(".probe .switch")).toBe(true);
  await page.keyboard.press("Shift+Tab");
  expect(await outline(".probe input[type=checkbox]:not(.switch)")).toBe(true);

  await page.locator(".probe input[type=search]").focus();
  expect(await halo(".probe input[type=search]")).toBe(true);
});

test("a manage notice stacks its parts while a chat notice keeps its icon beside the text", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  await probe(page, `<div class="notice warn restart-banner"><strong>Cần khởi động lại</strong><div>Lý do</div></div>`);
  // The chat's notices sit straight under its main column, so this one goes in bare.
  await page.evaluate(() => {
    const notice = document.createElement("div");
    notice.className = "notice halted chat-probe";
    notice.innerHTML = `<svg width="16" height="16"></svg>Dừng`;
    document.querySelector("main")?.prepend(notice);
  });

  expect(await page.locator(".probe .restart-banner").evaluate((el) => getComputedStyle(el).display)).toBe("block");
  expect(await page.locator("main > .chat-probe").evaluate((el) => getComputedStyle(el).display)).toBe("flex");
});

// iOS zooms the whole page into a field whose text is under 16px, and leaves it zoomed.
test("the memory editor's text is large enough that a phone does not zoom into it", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  await probe(page, `<div class="memory-editor"><textarea aria-label="m"></textarea></div>`);

  const size = await page.locator(".probe textarea").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(size).toBeGreaterThanOrEqual(16);
});

// Approving a command means reading all of it. On a phone the full view has to wrap where
// the card ends: a block that scrolls sideways hides exactly the tail nobody then reads,
// and one wider than the screen drags the whole page sideways with it.
test("a tool call's full arguments wrap at phone width instead of widening the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const command = `find /h/workspace/logs -name '*.log' -mtime +30 -delete && echo ${"cleaned-".repeat(24)}done`;
  await mockApi(page, {
    conversations: [
      {
        id: "c1", agent_id: "default", channel: "", title: "Dọn log", summary: "", created_at: "", updated_at: "",
        autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], parent_call_id: "", spent_usd: 0,
        unknown_cost_calls: 0, status: "awaiting_approval", over_budget: false, messages: [],
        pending_approval: {
          id: "ap", conversation_id: "c1", message_id: "m", tool_call_id: "tc", tool_name: "shell_run",
          arguments: { command, timeout: 60 }, status: "pending", created_at: "2026-09-26T01:00:00Z",
          expires_at: "2026-09-26T01:10:00Z", resolved_at: null, kind: "tool", options: [],
        },
      },
    ],
  });
  await page.goto("/#/chat/c1");
  const bar = page.getByRole("alertdialog");
  const toggle = bar.getByRole("button", { name: "Xem đầy đủ" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect((await toggle.boundingBox())?.height).toBeGreaterThanOrEqual(40);
  await toggle.click();

  const block = bar.locator(".args-detail-code").first();
  await expect(block).toHaveText(command);
  const fit = await block.evaluate((el) => {
    const box = el.getBoundingClientRect();
    return {
      page: document.documentElement.scrollWidth,
      width: window.innerWidth,
      right: box.right,
      sideways: el.scrollWidth - el.clientWidth,
    };
  });
  expect(fit.page).toBeLessThanOrEqual(fit.width);
  expect(fit.right).toBeLessThanOrEqual(fit.width);
  expect(fit.sideways).toBeLessThanOrEqual(0);
});
