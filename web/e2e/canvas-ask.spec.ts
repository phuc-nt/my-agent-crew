import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, mockApi } from "./mock-api";
import { sentMessage } from "./sent-message";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
// Five lines: three paragraphs on the first, third and fifth.
const TEXT = "Việc một\n\nViệc hai\n\nViệc ba";
const PASSAGE = "Việc hai";
const QUESTION = "chỗ này nên làm trước hay sau?";
const NOTE = `[Canvas · ${TITLE}]\n> ${PASSAGE}`;
const ANSWER = "Nên làm trước.";

/** What the server streams for the question: the note it kept with it, then the answer. */
const TURN = [
  { type: "user_context", context: NOTE },
  { type: "assistant_message", message_id: "a1", content: ANSWER, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** A conversation with nothing said in it yet, which the canvas is shared with. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Kế hoạch", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/**
 * The canvas open beside or over the conversation, and the messages the browser sends. A canvas a
 * person wrote opens to edit, one the agent wrote opens to read.
 */
async function openCanvas(page: Page, writer: "person" | "agent") {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: TITLE, agent_id: writer === "agent" ? "master" : "", content: TEXT, conversationIds: ["c1"] });
  await mockApi(page, { conversations: [quiet()], canvas: fake, turns: [TURN] });
  const messages: unknown[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") messages.push(sentMessage(request));
  });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
  await page.getByRole("button", { name: new RegExp(TITLE) }).click();
  return messages;
}

const bar = (page: Page) => page.getByRole("group", { name: vi.canvas.ask.group });
const cover = (page: Page) => page.getByRole("region", { name: vi.canvas.button });

/** Selects `needle` in the editor, as dragging across it or the shift keys leave it. */
async function selectInEditor(page: Page, needle: string) {
  const field = page.getByRole("textbox", { name: vi.canvas.editor });
  await expect(field).toHaveValue(TEXT);
  await field.focus();
  await field.evaluate((el: HTMLTextAreaElement, text: string) => {
    const at = el.value.indexOf(text);
    if (at < 0) throw new Error(`the editor holds no "${text}"`);
    el.setSelectionRange(at, at + text.length);
  }, needle);
}

/** Selects `needle` in the canvas being read, with a range over its text as a drag would make. */
async function selectInView(page: Page, needle: string) {
  await page.locator(".canvas-view").evaluate((root: HTMLElement, text: string) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
      const at = node.data.indexOf(text);
      if (at < 0) continue;
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + text.length);
      const selection = document.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      return;
    }
    throw new Error(`the view shows no "${text}"`);
  }, needle);
}

/** A press of a finger on a phone, of the mouse elsewhere. */
const press = (target: Locator, touch: boolean) => (touch ? target.tap() : target.click());

/** Opens the box, types the question and sends it. */
async function ask(page: Page, touch = false) {
  const group = bar(page);
  await press(group.getByRole("button", { name: vi.canvas.ask.button }), touch);
  await group.getByRole("textbox", { name: vi.canvas.ask.question }).fill(QUESTION);
  await press(group.getByRole("button", { name: vi.send, exact: true }), touch);
}

/** The question stands in the thread over its answer, with the note it went with closed until the chip opens it. */
async function expectAsked(page: Page) {
  const asked = page.getByTestId("message-user");
  await expect(asked).toContainText(QUESTION);
  await expect(page.getByTestId("message-assistant")).toContainText(ANSWER);
  const chip = page.getByRole("button", { name: vi.canvas.noteChip });
  await expect(chip).toHaveAttribute("aria-expanded", "false");
  expect(await asked.evaluate((el) => el.nextElementSibling?.getAttribute("data-testid"))).toBe("canvas-note");
  await chip.click();
  await expect(page.getByTestId("canvas-note-body").locator("pre")).toHaveText(NOTE);
}

const ASKED = { text: QUESTION, canvas: { artifact_id: PLAN, selection: { version: 1, text: PASSAGE, line_start: 3, line_end: 3 } } };

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a passage selected in the editor goes with the question, on its own lines", async ({ page }) => {
    const messages = await openCanvas(page, "person");
    await selectInEditor(page, PASSAGE);

    await expect(bar(page)).toContainText(vi.canvas.ask.lines(3, 3, PASSAGE.length));
    await expect(bar(page).locator("blockquote")).toHaveText(PASSAGE);
    await ask(page);

    await expectAsked(page);
    expect(messages).toEqual([ASKED]);
    // The box is put away, the canvas stays beside the conversation.
    await expect(bar(page).getByRole("textbox", { name: vi.canvas.ask.question })).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
  });

  test("a passage selected with the keys is offered while it is selected, and gone with the caret", async ({ page }) => {
    await openCanvas(page, "person");
    const field = page.getByRole("textbox", { name: vi.canvas.editor });
    await expect(field).toHaveValue(TEXT);

    // From the start of the text to the start of the third line, then one letter at a time: the End key
    // goes to the end of the text on a Mac, so it is not what picks a line.
    await field.click({ position: { x: 2, y: 2 } });
    await field.press("ArrowDown");
    await field.press("ArrowDown");
    for (let letter = 0; letter < PASSAGE.length; letter++) await field.press("Shift+ArrowRight");
    await expect(bar(page)).toContainText(vi.canvas.ask.lines(3, 3, PASSAGE.length));
    await expect(bar(page).locator("blockquote")).toHaveText(PASSAGE);

    await field.press("ArrowRight");
    await expect(bar(page)).toHaveCount(0);
  });

  test("a passage selected in the canvas being read goes with the question, on the lines it was drawn from", async ({ page }) => {
    const messages = await openCanvas(page, "agent");
    await selectInView(page, PASSAGE);

    await expect(bar(page)).toContainText(vi.canvas.ask.lines(3, 3, PASSAGE.length));
    await ask(page);

    await expectAsked(page);
    expect(messages).toEqual([ASKED]);
  });

  test("a triple click picks the paragraph under it, the last one too", async ({ page }) => {
    await openCanvas(page, "agent");
    for (const [paragraph, line] of [["Việc hai", 3], ["Việc ba", 5], ["Việc một", 1]] as const) {
      await page.locator(".canvas-view p", { hasText: paragraph }).click({ clickCount: 3 });
      await expect(bar(page)).toContainText(`Dòng ${line} ·`);
      await expect(bar(page).locator("blockquote")).toHaveText(paragraph);
    }
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("asking from the canvas over the chat puts the canvas away, so the question and its answer show", async ({ page }) => {
    const messages = await openCanvas(page, "person");
    await expect(cover(page)).toBeVisible();
    await selectInEditor(page, PASSAGE);
    await expect(bar(page)).toBeInViewport({ ratio: 1 });

    await ask(page, true);

    await expect(cover(page)).toHaveCount(0);
    await expectAsked(page);
    expect(messages).toEqual([ASKED]);
  });
});
