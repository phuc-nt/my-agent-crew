import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { type Conversation, mockApi } from "./mock-api";

// A phone, where the button under each of the person's own messages is a full finger tall:
// when a turn starts those buttons leave, and everything below them moves up by their height.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

const TURNS_BEFORE = 8;
const ANSWER = "Đã xong.";
const TURN = [
  { type: "assistant_message", message_id: "a9", content: ANSWER, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** Replies of several lines each, so that a screen of the thread holds one of the person's messages at most. */
function longConversation(): Conversation {
  const stored = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "" };
  const messages = Array.from({ length: TURNS_BEFORE }, (_, i) => [
    { ...stored, id: String(2 * i + 1), seq: 2 * i + 1, role: "user", content: `Câu hỏi số ${i + 1}`, provider: null, model: null },
    {
      ...stored, id: String(2 * i + 2), seq: 2 * i + 2, role: "assistant", provider: "fake", model: "echo",
      content: `Trả lời số ${i + 1}. ${"Câu này dài để chiếm nhiều dòng trên màn hình hẹp. ".repeat(8)}`,
    },
  ]).flat();
  return {
    id: "c1", agent_id: "default", channel: "", title: "Việc dài", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages,
  };
}

/** Opens the long conversation, with the answer to the next message held back until the returned function is called. */
async function open(page: Page) {
  await mockApi(page, { conversations: [longConversation()], turns: [TURN] });
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(/^https?:\/\/[^/]+\/api\/conversations\/c1\/messages$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await held;
    await route.fallback();
  });
  await page.goto("/#/chat/c1");
  await expect(page.getByTestId("message-assistant").last()).toContainText(`Trả lời số ${TURNS_BEFORE}`);
  return release;
}

/** How much of the thread lies below what shows: 0 when the newest line is the one in view. */
function hiddenBelow(thread: Locator) {
  return thread.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight);
}

async function send(page: Page, text: string) {
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill(text);
  await box.press("Enter");
  await expect(page.getByTestId("thinking")).toBeVisible();
  // Nothing can be forked while the turn runs, which is what takes the height out above.
  await expect(page.locator(".fork-button")).toHaveCount(0);
}

test("a turn that starts with the thread on its newest line leaves it there", async ({ page }) => {
  const release = await open(page);
  const thread = page.locator("section.thread");
  await expect.poll(() => hiddenBelow(thread)).toBeLessThanOrEqual(1);

  await send(page, "và thêm một câu nữa");
  await expect.poll(() => hiddenBelow(thread)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId("jump-newest")).toHaveCount(0);

  release();
  await expect(page.getByTestId("message-assistant").last()).toContainText(ANSWER);
  await expect.poll(() => hiddenBelow(thread)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId("jump-newest")).toHaveCount(0);
});

// The browser lowers the position by the height that left above what shows, to keep that in
// place. While the thread follows its newest line the follow does the moving, and the
// browser's lowering reads as the person scrolling up: whether the thread stops following
// then depends on which of the two reaches it first, so the switch is pinned itself.
test("the browser's own anchoring is off while the thread follows its newest line and on once it is read", async ({ page }) => {
  await open(page);
  const thread = page.locator("section.thread");
  const anchoring = () => thread.evaluate((el) => getComputedStyle(el).overflowAnchor);
  await expect.poll(anchoring).toBe("none");

  await thread.evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect(page.getByTestId("jump-newest")).toBeVisible();
  await expect.poll(anchoring).toBe("auto");

  await page.getByTestId("jump-newest").tap();
  await expect.poll(anchoring).toBe("none");
  await expect(page.getByTestId("jump-newest")).toHaveCount(0);
});

test("a reader who scrolled back keeps their place when the buttons above leave", async ({ page }) => {
  const release = await open(page);
  // The top of the thread is the reply's own top, so what the browser holds in place is the reply.
  const reading = page.getByTestId("message-assistant").filter({ hasText: "Trả lời số 5." });
  await reading.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await expect(page.getByTestId("jump-newest")).toBeVisible();
  const before = (await reading.boundingBox())!.y;

  await send(page, "và thêm một câu nữa");
  expect(Math.abs((await reading.boundingBox())!.y - before)).toBeLessThanOrEqual(1);
  await expect(page.getByTestId("jump-newest")).toBeVisible();

  release();
  await expect(page.getByTestId("message-assistant").last()).toContainText(ANSWER);
});
