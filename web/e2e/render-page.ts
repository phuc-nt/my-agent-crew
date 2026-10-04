import { expect, type Page } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, mockApi } from "./mock-api";

/**
 * A page an agent wrote, on show in the canvas of a real browser. It comes with the policy and the
 * reporter the server sends (`mock-render.ts`), so what a page does here is what it would do there.
 */

export const PAGE = "0a0b0c0d0e0f";
export const OTHER = "f0e0d0c0b0a0";
export const TITLE = "Trang thử";

export const html = (body: string) =>
  `<!doctype html>\n<html lang="vi">\n<head><meta charset="utf-8"><title>${TITLE}</title></head>\n<body>\n${body}\n</body>\n</html>\n`;
export const script = (code: string) => `<script>${code}</script>`;

export const frame = (page: Page) => page.locator("iframe.canvas-frame");
export const inside = (page: Page) => page.frameLocator("iframe.canvas-frame");
export const composer = (page: Page) => page.getByRole("textbox", { name: vi.composerPlaceholder });

/** What the server streams for a message: an answer, so the send ends as sent. */
const TURN = [
  { type: "assistant_message", message_id: "a1", content: "Để tôi xem.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** A conversation with nothing said in it yet, which the canvas is shared with. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Trang", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** A server holding the agent's page whose body is `body`, and another page it could move to. */
export async function serve(page: Page, body: string): Promise<FakeCanvas> {
  const fake = new FakeCanvas();
  fake.add({ id: PAGE, title: TITLE, kind: "html", agent_id: "master", content: html(body), conversationIds: ["c1"] });
  fake.add({ id: OTHER, title: "Trang khác", kind: "html", agent_id: "master", content: html("<p>Trang khác</p>") });
  await mockApi(page, { conversations: [quiet()], canvas: fake, turns: [TURN] });
  return fake;
}

/**
 * The page on show in the canvas beside or over the conversation, with the messages the browser
 * sends and every request the page itself makes after the one that loads it.
 */
export async function openPage(page: Page, body: string) {
  const fake = await serve(page, body);
  const messages: unknown[] = [];
  const fromFrame: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") messages.push(request.postDataJSON());
    if (!request.isNavigationRequest() && request.frame() !== page.mainFrame()) fromFrame.push(`${request.method()} ${request.url()}`);
  });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
  await page.getByRole("button", { name: new RegExp(TITLE) }).click();
  await expect(frame(page)).toBeVisible();
  return { fake, messages, fromFrame };
}
