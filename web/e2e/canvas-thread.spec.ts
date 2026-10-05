import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, mockApi } from "./mock-api";
import { smallTargets } from "./small-targets";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
// A title with nowhere to break, wider than a phone.
const LONG_TITLE = `Biên bản ${"kéodàikhôngngắt".repeat(8)}`;
const WRITE = { title: TITLE, content: "Việc một\n\nViệc hai" };
const REPLY = "Đã viết kế hoạch.";

/** A turn in which the agent makes the canvas and says so, as the server streams it. */
const TURN = [
  {
    type: "assistant_message", message_id: "a1", content: "", provider: null, model: null, cost_usd: null,
    tool_calls: [{ id: "w1", name: "artifact_create", arguments: WRITE }],
  },
  { type: "tool_call", tool_call_id: "w1", name: "artifact_create", arguments: WRITE },
  {
    type: "tool_result", tool_call_id: "w1", name: "artifact_create", ok: true,
    output: `[artifact ${PLAN} v1]\nCanvas "${TITLE}" was created.`,
  },
  { type: "assistant_message", message_id: "a2", content: REPLY, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** A conversation with nothing said in it yet, which the canvas the agent is about to make is shared with. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Kế hoạch", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** The first message is sent, and the agent answers it by making the canvas. */
async function askForPlan(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: TITLE, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });
  await mockApi(page, { conversations: [quiet()], canvas: fake, turns: [TURN] });
  await page.goto("/#/chat/c1");
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill("viết kế hoạch tuần");
  await box.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText(REPLY);
  return box;
}

/** A saved conversation whose reply sent the canvas to the chat as a file, opened with the canvas named `title`. */
async function openSent(page: Page, title = TITLE) {
  const stored = { tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" };
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title, agent_id: "master", content: WRITE.content, conversationIds: ["c1"] });
  const messages = [
    { ...stored, id: "m1", seq: 1, role: "user", content: "gửi kế hoạch cho tôi" },
    { ...stored, id: "m2", seq: 2, role: "assistant", content: `Kế hoạch đây:\nFILE: artifact:${PLAN}\nXem nhé.` },
  ];
  await mockApi(page, { conversations: [{ ...quiet(), messages }], canvas: fake });
  await page.goto("/#/chat/c1");
  const chip = page.getByTestId("message-assistant").getByTestId("canvas-ref");
  await expect(chip).toHaveText(`${title}${vi.canvas.card.open}`);
  return { chip, open: chip.getByRole("button", { name: vi.canvas.card.openLabel(title) }) };
}

/** How the chip sits in its reply: inside it, the name in front of a button at the chip's end whose word is on one line. */
function placed(page: Page) {
  return page.evaluate(() => {
    const box = (selector: string) => (document.querySelector(selector) as HTMLElement).getBoundingClientRect();
    const [bubble, chip, title, button] = ['[data-testid="message-assistant"]', ".canvas-ref", ".canvas-ref .canvas-chip-title", ".canvas-ref button"].map(box);
    const word = document.createRange();
    word.selectNodeContents(document.querySelector(".canvas-ref button") as HTMLElement);
    return {
      inside: chip.left >= bubble.left && chip.right <= bubble.right,
      buttonAfterName: button.left >= title.right && button.right <= chip.right,
      buttonLines: word.getClientRects().length,
      sideways: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
}

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the canvas the agent makes opens beside the thread while the keyboard stays in the box", async ({ page }) => {
    const messages: unknown[] = [];
    page.on("request", (request) => {
      const { pathname } = new URL(request.url());
      if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") messages.push(request.postDataJSON());
    });
    const box = await askForPlan(page);

    await expect(page.getByTestId("canvas-card")).toContainText(TITLE);
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
    await expect(box).toBeFocused();
    await page.keyboard.type("và thêm");
    await expect(box).toHaveValue("và thêm");

    // The canvas on show is the one the next message is about.
    await box.press("Enter");
    await expect.poll(() => messages.length).toBe(2);
    expect(messages[1]).toEqual({ text: "và thêm", canvas: { artifact_id: PLAN, selection: null } });
  });

  test("the card's Open brings a canvas back after it was closed", async ({ page }) => {
    await askForPlan(page);
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();

    await page.getByRole("button", { name: vi.canvas.close }).click();
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toHaveCount(0);
    await page.getByRole("button", { name: vi.canvas.card.openLabel(TITLE) }).click();

    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
  });

  test("a line of a reply that sends a canvas is a chip in the reply, which opens the canvas beside the thread", async ({ page }) => {
    const { open } = await openSent(page);
    await expect(page.getByTestId("message-file")).toHaveCount(0);
    await expect(page.getByTestId("message-assistant")).not.toContainText("FILE:");
    expect(await placed(page)).toEqual({ inside: true, buttonAfterName: true, buttonLines: 1, sideways: false });

    await open.click();

    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the card offers the canvas, and a tap on Open covers the thread with it", async ({ page }) => {
    await askForPlan(page);
    const open = page.getByRole("button", { name: vi.canvas.card.openLabel(TITLE) });
    await expect(open).toBeVisible();
    await expect(page.getByRole("region", { name: vi.canvas.button })).toHaveCount(0);

    await open.tap();

    await expect(page.getByRole("region", { name: vi.canvas.button })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
  });

  test("the chip of a line that sends a canvas is big enough for a finger, and a tap covers the thread with the canvas", async ({ page }) => {
    const { open } = await openSent(page);

    expect(await smallTargets(page, ".canvas-ref")).toEqual([]);
    expect((await open.boundingBox())?.height).toBeGreaterThanOrEqual(40);
    expect(await placed(page)).toEqual({ inside: true, buttonAfterName: true, buttonLines: 1, sideways: false });

    await open.tap();

    await expect(page.getByRole("region", { name: vi.canvas.button })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: TITLE })).toBeVisible();
  });

  test("a chip named in one long word wraps inside its reply, and keeps a button a finger can press", async ({ page }) => {
    await openSent(page, LONG_TITLE);

    expect(await placed(page)).toEqual({ inside: true, buttonAfterName: true, buttonLines: 1, sideways: false });
    expect(await smallTargets(page, ".canvas-ref")).toEqual([]);
  });
});
