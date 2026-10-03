import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

const NOTE = "[Canvas · Kế hoạch tuần]\n> chạy 5 km";

test("a message sent with a canvas note shows it as a chip, and still does once the page is loaded again", async ({ page }) => {
  await mockApi(page, { turns: [[
    { type: "user_context", context: NOTE },
    { type: "assistant_message", message_id: "a1", content: "Đã sửa.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await page.getByRole("textbox").fill("sửa chỗ này");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("Đã sửa.");

  // Under the message it belongs to, and closed: the note quotes the canvas and is long.
  const chip = page.getByRole("button", { name: vi.canvas.noteChip });
  await expect(chip).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByTestId("canvas-note-body")).toHaveCount(0);
  expect(await page.getByTestId("message-user").evaluate((el) => el.nextElementSibling?.getAttribute("data-testid"))).toBe("canvas-note");

  await chip.click();
  await expect(chip).toHaveAttribute("aria-expanded", "true");
  expect(await page.getByTestId("canvas-note-body").locator("pre").textContent()).toBe(NOTE);
  await chip.click();
  await expect(page.getByTestId("canvas-note-body")).toHaveCount(0);

  // What the server stored with the message comes back with the conversation.
  await page.reload();
  await expect(page.getByTestId("message-user")).toContainText("sửa chỗ này");
  await expect(page.getByRole("button", { name: vi.canvas.noteChip })).toHaveAttribute("aria-expanded", "false");
});

test("a message sent without one has no chip", async ({ page }) => {
  await mockApi(page, { turns: [[
    { type: "assistant_message", message_id: "a1", content: "Chào bạn.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ]] });
  await page.goto("/");
  await page.getByRole("textbox").fill("xin chào");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("Chào bạn.");
  await expect(page.getByTestId("canvas-note")).toHaveCount(0);
});

// A note quotes a document, so it can be tall, and hold a line longer than any window.
const LONG_NOTE = [
  "[Canvas · Kế hoạch tuần]",
  ...Array.from({ length: 60 }, (_, i) => `> dòng ${i + 1} của bản kế hoạch dài`),
  `> ${"một dòng rất dài gồm nhiều từ ".repeat(20)}`,
  `> ${"a".repeat(400)}`,
].join("\n");

/** A saved conversation whose first message went to the agent with a canvas note. */
function noted(note = NOTE): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Kế hoạch", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
    messages: [
      { id: "m1", seq: 1, role: "user", content: "sửa chỗ này", context: note, tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" },
      { id: "m2", seq: 2, role: "assistant", content: "Đã sửa.", tool_calls: [], tool_call_id: null, name: null, provider: "fake", model: "echo", cost_usd: 0, created_at: "" },
    ],
  };
}

// A phone gets the floor from the width, a tablet only from the touch screen: both are held to it.
const TOUCH: [string, { width: number; height: number }][] = [
  ["a phone", { width: 390, height: 844 }],
  ["a tablet", { width: 1000, height: 800 }],
];

for (const [name, viewport] of TOUCH) {
  test.describe(`the canvas note on ${name}`, () => {
    test.use({ viewport, hasTouch: true, isMobile: true });

    test("opens with a tap, and every control it shows is big enough for a finger", async ({ page }) => {
      await mockApi(page, { conversations: [noted()] });
      await page.goto("/#/chat/c1");
      const chip = page.getByRole("button", { name: vi.canvas.noteChip });
      await expect(chip).toBeVisible();
      expect(await smallTargets(page, ".canvas-note")).toEqual([]);

      await chip.tap();
      // A tap leaves the chip pressed, drawn at 98% of its size, for a moment, and the scan
      // measures what is drawn: wait until the press is over, so a 40px button reads as 40px.
      await expect(chip).toHaveCSS("transform", "none");
      await expect(page.getByTestId("canvas-note-body")).toBeVisible();
      await expect(page.getByRole("button", { name: vi.canvas.noteCopy })).toBeVisible();
      expect(await smallTargets(page, ".canvas-note")).toEqual([]);

      // It reads inside the thread's width: nothing of the note pushes the page sideways.
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    });

    test("holds a long note in its box: lines wrap, and the height scrolls inside", async ({ page }) => {
      await mockApi(page, { conversations: [noted(LONG_NOTE)] });
      await page.goto("/#/chat/c1");
      await page.getByRole("button", { name: vi.canvas.noteChip }).tap();

      const text = page.getByTestId("canvas-note-body").locator("pre");
      await expect(text).toBeVisible();
      const box = await text.evaluate((el) => {
        el.scrollTop = el.scrollHeight;
        return { sideways: el.scrollWidth > el.clientWidth, height: el.getBoundingClientRect().height, scrolled: el.scrollTop };
      });
      // Neither a long line nor a long word scrolls the box sideways, and a tall note takes under
      // half the window and scrolls inside it rather than pushing the thread down.
      expect(box.sideways).toBe(false);
      expect(box.height).toBeLessThan(viewport.height / 2);
      expect(box.scrolled).toBeGreaterThan(0);
    });
  });
}
