import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { overflowing } from "./canvas-overflow";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

type Put = { content: string; base_version: number };

const NOTE = "Dòng một\nDòng hai\n";

/** A conversation paused on the owner's approval: a button the canvas over it must keep out of reach. */
function waiting(): Conversation {
  const call = { id: "tc", name: "write_file", arguments: { path: "a.md" } };
  return {
    id: "c1", agent_id: "default", channel: "", title: "Ghi tệp", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "awaiting_approval", over_budget: false, parent_call_id: "",
    messages: [{ id: "m1", seq: 1, role: "assistant", content: "", tool_calls: [call], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" }],
    pending_approval: { id: "ap", conversation_id: "c1", message_id: "m1", tool_call_id: "tc", tool_name: "write_file", arguments: call.arguments, status: "pending", created_at: "", expires_at: null, resolved_at: null, kind: "tool" },
  };
}

/** The app on that conversation, whose one canvas "Ghi chú" a person wrote; each save it sends is kept. */
async function openChat(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ title: "Ghi chú", content: NOTE, conversationIds: ["c1"] });
  await mockApi(page, { conversations: [waiting()], canvas: fake });
  const puts: Put[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && /\/api\/artifacts\//.test(request.url())) puts.push(request.postDataJSON());
  });
  await page.goto("/#/chat/c1");
  await expect(approve(page)).toBeVisible();
  return { fake, puts };
}

const approve = (page: Page) => page.getByRole("button", { name: "Cho phép", exact: true });
const canvasButton = (page: Page) => page.getByRole("button", { name: vi.canvas.buttonLabel(1) });
const editor = (page: Page) => page.getByRole("textbox", { name: vi.canvas.editor });
const cover = (page: Page) => page.getByRole("region", { name: vi.canvas.button });

async function openNote(page: Page) {
  await canvasButton(page).click();
  await page.getByRole("button", { name: /Ghi chú/ }).click();
  await expect(editor(page)).toHaveValue(NOTE);
}

test.describe("a canvas beside a wide conversation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("opens in a tab beside the chat, and a pause in typing saves once from the version it began on", async ({ page }) => {
    const { fake, puts } = await openChat(page);
    await openNote(page);
    await expect(page.getByRole("tab", { name: vi.canvas.tabs.canvas })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: vi.canvas.tabs.activity })).toBeVisible();
    await expect(approve(page)).toBeVisible();

    await editor(page).fill(`${NOTE}Dòng ba\n`);

    await expect.poll(() => fake.content("a1")).toBe(`${NOTE}Dòng ba\n`);
    await page.waitForTimeout(2000);
    expect(puts).toEqual([{ content: `${NOTE}Dòng ba\n`, base_version: 1 }]);
  });

  test("keeps every character typed while a save is held for two seconds", async ({ page }) => {
    const { fake, puts } = await openChat(page);
    await openNote(page);
    const release = fake.holdNext("PUT", "request");

    await editor(page).fill(`${NOTE}abc`);
    await expect.poll(() => puts.length).toBe(1);
    await editor(page).pressSequentially("xyz");
    await page.waitForTimeout(2000);
    await release();

    await expect.poll(() => fake.content("a1")).toBe(`${NOTE}abcxyz`);
    await expect(editor(page)).toHaveValue(`${NOTE}abcxyz`);
    expect(puts).toEqual([
      { content: `${NOTE}abc`, base_version: 1 },
      { content: `${NOTE}abcxyz`, base_version: 2 },
    ]);
  });

  test("an agent's save on the line being edited raises the conflict bar, and keeping mine saves over it", async ({ page }) => {
    const { fake, puts } = await openChat(page);
    await openNote(page);
    fake.write("a1", "Dòng một của agent\nDòng hai\n");

    await editor(page).fill("Dòng một của tôi\nDòng hai\n");
    const bar = page.locator(".canvas-conflict[role=alert]");
    await expect(bar).toContainText("v2");
    await bar.getByRole("button", { name: vi.canvas.keepMine }).click();

    await expect.poll(() => fake.content("a1")).toBe("Dòng một của tôi\nDòng hai\n");
    expect(puts.at(-1)).toEqual({ content: "Dòng một của tôi\nDòng hai\n", base_version: 2 });
    await expect(bar).toHaveCount(0);
    await expect(editor(page)).toHaveValue("Dòng một của tôi\nDòng hai\n");
  });
});

const NARROW: [string, { width: number; height: number }][] = [
  ["a tablet", { width: 1000, height: 800 }],
  ["a phone", { width: 390, height: 844 }],
];

for (const [name, viewport] of NARROW) {
  test.describe(`a canvas over the chat on ${name}`, () => {
    test.use({ viewport, hasTouch: true, isMobile: true });

    test("saves, keeps the approval out of reach, fits a finger and goes back to the chat", async ({ page }) => {
      const { puts } = await openChat(page);
      await expect(canvasButton(page)).toBeInViewport({ ratio: 1 });
      await openNote(page);
      await expect(page.getByRole("tablist")).toHaveCount(0);

      await editor(page).fill(`${NOTE}Dòng ba\n`);
      await expect.poll(() => puts).toEqual([{ content: `${NOTE}Dòng ba\n`, base_version: 1 }]);

      // Round the page and back to the canvas more than once: the chat under it takes no focus.
      for (let press = 0; press < 40; press++) {
        await page.keyboard.press("Tab");
        expect(await page.evaluate(() => Boolean(document.activeElement?.closest("main")))).toBe(false);
      }
      expect(await smallTargets(page, ".canvas-dock")).toEqual([]);
      expect(await overflowing(page)).toEqual([]);

      await cover(page).getByRole("button", { name: vi.canvas.backToChat }).click();
      await expect(cover(page)).toHaveCount(0);
      await expect(canvasButton(page)).toBeFocused();
      await expect(approve(page)).toBeVisible();
    });
  });
}
