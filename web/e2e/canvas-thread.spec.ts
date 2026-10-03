import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, mockApi } from "./mock-api";

const PLAN = "00ff00ff00ff";
const TITLE = "Kế hoạch tuần";
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
});
