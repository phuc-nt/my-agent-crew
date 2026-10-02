import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, mockApi } from "./mock-api";

const NOTE = "Dòng một\nDòng hai\n";

test.use({ viewport: { width: 1440, height: 900 } });

/** A conversation with nothing said in it yet, which the canvas "Ghi chú" is shared with. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Kế hoạch", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

test("a message sent over typing the canvas has not saved yet waits for the save, then names the canvas", async ({ page }) => {
  const fake = new FakeCanvas();
  fake.add({ title: "Ghi chú", content: NOTE, conversationIds: ["c1"] });
  await mockApi(page, {
    conversations: [quiet()],
    canvas: fake,
    turns: [[
      { type: "assistant_message", message_id: "a1", content: "Đã đọc.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ]],
  });
  const order: string[] = [];
  const messages: unknown[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (request.method() === "PUT" && pathname === "/api/artifacts/a1") order.push("save");
    if (request.method() === "POST" && pathname === "/api/conversations/c1/messages") {
      order.push("message");
      messages.push(request.postDataJSON());
    }
  });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).click();
  await page.getByRole("button", { name: /Ghi chú/ }).click();
  const editor = page.getByRole("textbox", { name: vi.canvas.editor });
  await expect(editor).toHaveValue(NOTE);
  const release = fake.holdNext("PUT", "request");
  await editor.fill(`${NOTE}Dòng ba\n`);

  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill("đọc lại giúp tôi");
  await box.press("Enter");

  // The save is out and held: the message waits behind it, and the words wait in a box that takes
  // no more typing, so nothing can be added to what is about to go.
  await expect.poll(() => order).toEqual(["save"]);
  await expect(box).toHaveAttribute("readonly", "");
  await expect(box).toHaveValue("đọc lại giúp tôi");
  await page.waitForTimeout(500);
  expect(order).toEqual(["save"]);

  await release();
  await expect(page.getByTestId("message-assistant")).toContainText("Đã đọc.");
  expect(order).toEqual(["save", "message"]);
  expect(messages).toEqual([{ text: "đọc lại giúp tôi", canvas: { artifact_id: "a1", selection: null } }]);
  expect(fake.content("a1")).toBe(`${NOTE}Dòng ba\n`);
  await expect(box).toHaveValue("");
  await expect(box).not.toHaveAttribute("readonly");
});
