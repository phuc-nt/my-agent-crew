import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { handedOn, lookalikes } from "../src/test/script-handoff-message";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

// The message a script job opens a turn with holds the schedule's prompt, a sentence for the
// model and what the script printed between two marker lines. The thread shows the prompt
// as the message and what was printed as a block of its own under it.

const PROMPT = "Tóm tắt các đơn mới cho tôi.";
const SHORT = "2 đơn mới\n  - Tiki #123 · 250.000đ\n  - Shopee #456 · 99.000đ";
/** Taller than its box, and with a line that has nowhere to break. */
const LONG = [
  ...Array.from({ length: 80 }, (_, i) => `đơn ${i + 1} · đã giao cho đơn vị vận chuyển`),
  `https://shop.example.test/orders/${"a".repeat(400)}`,
].join("\n");

/** The block what was printed stands in: nothing in it may reach past its own edge. */
const BLOCK = '[data-testid="script-printed"]';

const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };

function conversation(asked: string): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Đơn mới", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
    messages: [
      { ...STORED, id: "1", seq: 1, role: "user", content: asked },
      { ...STORED, id: "2", seq: 2, role: "assistant", content: "Có 2 đơn mới.", provider: "fake", model: "echo" },
    ],
  };
}

async function open(page: Page, asked: string) {
  const mock = await mockApi(page, { conversations: [conversation(asked)] });
  await page.goto("/#/chat/c1");
  await expect(page.getByTestId("message-assistant")).toContainText("Có 2 đơn mới.");
  return mock;
}

/** How far the page itself can scroll, down and sideways. */
const pageRoom = (page: Page) =>
  page.evaluate(() => {
    const root = document.documentElement;
    return { down: root.scrollHeight - window.innerHeight, across: root.scrollWidth - window.innerWidth };
  });

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`a script job's message at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("is the prompt in the bubble and what the script printed under it, with no marker on screen", async ({ page }) => {
      await open(page, handedOn(PROMPT, SHORT));

      const bubble = page.getByTestId("message-user");
      await expect(bubble).toContainText(PROMPT);
      await expect(page.locator(".thread")).not.toContainText("SCRIPT_IN_RA");
      await expect(page.locator(".thread")).not.toContainText("DỮ LIỆU");

      const block = page.getByRole("group", { name: vi.scriptHandoff.printed });
      expect(await bubble.evaluate((el) => el.nextElementSibling?.getAttribute("data-testid"))).toBe("script-printed");
      await expect(block.getByRole("button", { name: vi.scriptHandoff.toggle(3) })).toHaveAttribute("aria-expanded", "true");
      expect(await block.getByTestId("script-printed-text").textContent()).toBe(SHORT);
      await expect(block.getByText(vi.scriptHandoff.asData)).toBeVisible();
      // Set as a terminal sets it, so the columns a script lined up stay lined up.
      expect(await block.getByTestId("script-printed-text").evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/mono/i);

      const edges = await block.evaluate((el) => el.getBoundingClientRect().toJSON());
      expect(edges.left).toBeGreaterThanOrEqual(0);
      expect(edges.right).toBeLessThanOrEqual(viewport.width);
      expect(await pageRoom(page)).toEqual({ down: 0, across: 0 });
      expect(await spills(page, BLOCK)).toEqual([]);
      if (viewport.width <= 720) expect(await smallTargets(page, BLOCK)).toEqual([]);
    });

    test("keeps a long one folded, and opened it scrolls in its own box, wrapped", async ({ page }) => {
      await open(page, handedOn(PROMPT, LONG));

      const block = page.getByTestId("script-printed");
      const toggle = block.getByRole("button", { name: vi.scriptHandoff.toggle(81) });
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(block.getByTestId("script-printed-text")).toHaveCount(0);
      await expect(page.getByTestId("message-assistant")).toBeInViewport();

      await toggle.focus();
      await page.keyboard.press("Enter");
      const text = block.getByTestId("script-printed-text");
      expect(await text.textContent()).toBe(LONG);
      const box = await text.evaluate((el) => ({ below: el.scrollHeight - el.clientHeight, beside: el.scrollWidth - el.clientWidth }));
      expect(box.below).toBeGreaterThan(0);
      expect(box.beside).toBeLessThanOrEqual(1);
      expect(await pageRoom(page)).toEqual({ down: 0, across: 0 });
      expect(await spills(page, BLOCK)).toEqual([]);

      // The box takes the keys once it is reached, so the end of the text is a key away.
      await page.keyboard.press("Tab");
      await expect(text).toBeFocused();
      await page.keyboard.press("End");
      await expect.poll(() => text.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

      await toggle.click();
      await expect(block.getByTestId("script-printed-text")).toHaveCount(0);
    });
  });
}

test("sending a script job's message again starts from the message as it is stored", async ({ page }) => {
  const stored = handedOn(PROMPT, SHORT);
  await open(page, stored);

  await page.getByTestId("message-user").locator(".fork-button").click();

  await expect(page.getByRole("textbox", { name: vi.composerPlaceholder })).toHaveValue(stored);
});

test("a message that only quotes the markers stays the plain message it is", async ({ page }) => {
  const [, quoted] = lookalikes(PROMPT, SHORT).find(([what]) => what === "an opening marker with another number") ?? [];
  expect(quoted).toBeDefined();
  await open(page, quoted as string);

  await expect(page.getByTestId("message-user")).toContainText("SCRIPT_IN_RA 0123456789abcdef>>>");
  await expect(page.getByTestId("message-user")).toContainText(SHORT.split("\n")[0]);
  await expect(page.getByTestId("script-printed")).toHaveCount(0);
});
