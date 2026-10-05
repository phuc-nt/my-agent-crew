import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { coachAgent, type Conversation, defaultAgent, mockApi } from "./mock-api";

// The app is one window tall and each column scrolls itself. A label positioned against
// something outside its scroller stays where the unscrolled content put it, far below the
// window, and then the page itself scrolls: a wheel that runs off the end of a column drags
// the whole app up and leaves a blank band under it.

const LONG = Array.from({ length: 60 }, (_, i) => `## Mục ${i}\n\n- dòng ${i}\n\n\`\`\`sh\necho ${i}\n\`\`\`\n`).join("\n");

function conversation(id: string, updatedAt = ""): Conversation {
  const message = (seq: number) => ({
    id: `${id}-m${seq}`, seq, role: seq % 2 ? "user" : "assistant", content: `Tin ${seq}\n\n`.repeat(6),
    tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "",
  });
  return {
    id, agent_id: "default", channel: "", title: `Cuộc ${id}`, summary: "", created_at: "", updated_at: updatedAt,
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
    messages: Array.from({ length: 30 }, (_, i) => message(i + 1)),
  } as unknown as Conversation;
}

/** How far the page itself can scroll, and how far it has. */
const pageScroll = (page: Page) =>
  page.evaluate(() => {
    const root = document.documentElement;
    return { room: root.scrollHeight - window.innerHeight, top: root.scrollTop + document.body.scrollTop };
  });

async function openApp(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ title: "Sức khoẻ", content: LONG, conversationIds: ["c1"] });
  await mockApi(page, { conversations: Array.from({ length: 40 }, (_, i) => conversation(`c${i + 1}`)), canvas: fake });
  await page.goto("/#/chat/c1");
  await expect(page.getByText("Tin 30").first()).toBeVisible();
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`the page at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("has nothing to scroll under a long thread and a long list of conversations", async ({ page }) => {
      await openApp(page);
      expect(await pageScroll(page)).toEqual({ room: 0, top: 0 });
    });

    test("stays put when a wheel runs off the end of a long canvas", async ({ page }) => {
      await openApp(page);
      await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
      await page.getByRole("button", { name: /Sức khoẻ/ }).click();
      const body = page.locator(".canvas-body");
      await expect(body).toBeVisible();
      await body.hover();
      for (let turn = 0; turn < 4; turn += 1) await page.mouse.wheel(0, 20_000);
      await page.mouse.wheel(0, -300);
      await page.waitForTimeout(300);
      expect(await pageScroll(page)).toEqual({ room: 0, top: 0 });
    });

    test("has nothing to scroll on the manage screen", async ({ page }) => {
      await openApp(page);
      await page.goto("/#/manage");
      await page.waitForTimeout(500);
      expect(await pageScroll(page)).toEqual({ room: 0, top: 0 });
    });

    // A row's unread dot carries its meaning in a label only a screen reader gets.
    test("has nothing to scroll under a long list of unread conversations", async ({ page }) => {
      const changed = "2099-01-01T00:00:00+00:00";
      await mockApi(page, { conversations: Array.from({ length: 60 }, (_, i) => conversation(`c${i + 1}`, changed)) });
      await page.goto("/#/chat/c1");
      await expect(page.getByText("Tin 30").first()).toBeVisible();
      await expect(page.getByTestId("unread-dot")).toHaveCount(59);
      expect(await pageScroll(page)).toEqual({ room: 0, top: 0 });
    });

    // The editor is the tallest manage page, and its badges and status lines carry such labels.
    test("has nothing to scroll under an agent's editor", async ({ page }) => {
      await mockApi(page, { agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent] });
      await page.goto("/#/manage/crew/coach");
      await expect(page.getByTestId("agent-editor")).toBeVisible();
      const prompt = page.getByTestId("section-prompt");
      await prompt.getByRole("button", { name: "Xem lời nhắc" }).click();
      await expect(prompt.locator(".prompt-preview")).toBeVisible();
      expect(await pageScroll(page)).toEqual({ room: 0, top: 0 });
    });
  });
}
