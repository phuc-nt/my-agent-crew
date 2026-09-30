import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

/** A conversation already carrying two turns, the way a reload reports it: both bubbles
 *  have the server's own numeric ids rather than the composer's optimistic `local-N`. */
function twoTurnConversation() {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Việc", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0.02, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "",
    messages: [
      { id: "1", seq: 1, role: "user", content: "câu đầu gõ sai", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" },
      { id: "2", seq: 2, role: "assistant", content: "trả lời câu đầu", tool_calls: [], tool_call_id: null, name: null, provider: "fake", model: "echo", cost_usd: 0.01, created_at: "" },
      { id: "3", seq: 3, role: "user", content: "câu sau", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" },
      { id: "4", seq: 4, role: "assistant", content: "trả lời câu sau", tool_calls: [], tool_call_id: null, name: null, provider: "fake", model: "echo", cost_usd: 0.01, created_at: "" },
    ],
    pending_approval: null,
  };
}

test("forking at the second saved message keeps the first turn, prefills the composer, and links back", async ({ page }) => {
  const mock = await mockApi(page, { conversations: [twoTurnConversation()] });
  await page.goto("/#/chat/c1");
  await expect(page.getByTestId("message-user")).toHaveCount(2);
  await expect(page.getByTestId("fork-origin")).toHaveCount(0);

  // Forks at "câu sau", the second saved user message: the branch keeps the first turn
  // (câu đầu + its reply) and drops everything from "câu sau" on, which comes back only
  // as the composer's seeded draft — not as a message a fresh copy of the fork must never
  // gain back. (Cutting at the very first message instead makes the branch empty; both
  // are exercised in the store's own Python tests — this spec only has to prove the web
  // side wires whichever one the person actually picks.)
  const secondBubble = page.getByTestId("message-user").nth(1);
  await expect(secondBubble).toContainText("câu sau");
  await secondBubble.locator(".fork-button").click();

  await expect(page.getByRole("textbox")).toHaveValue("câu sau");
  await expect(page.getByRole("textbox")).toBeFocused();
  await expect(page.getByTestId("message-user")).toHaveCount(1);
  await expect(page.getByTestId("message-user")).toContainText("câu đầu gõ sai");
  await expect(page.getByTestId("message-assistant")).toHaveCount(1);
  await expect(page.getByTestId("message-assistant")).toContainText("trả lời câu đầu");

  const origin = page.getByTestId("fork-origin");
  await expect(origin).toBeVisible();
  await expect(origin).toContainText("Rẽ nhánh từ");
  await expect(origin).toContainText("Việc");

  // The source is untouched: still the same four messages it had before the fork.
  const source = mock.conversations.find((c) => c.id === "c1");
  expect(source?.messages).toHaveLength(4);

  // Clicking the origin line returns to the source, with its own history intact.
  await origin.locator("button").click();
  await expect(page.getByTestId("message-user")).toHaveCount(2);
  await expect(page.getByTestId("message-assistant")).toHaveCount(2);
  await expect(page.getByTestId("fork-origin")).toHaveCount(0);
});

// The bubble a send just produced keeps its optimistic `local-N` id until the next reload
// (`use-thread.ts` does not reload after its own turn), so forking right after sending has
// to resolve that id through a fresh read of the conversation rather than trusting it as-is.
test("forking right after sending, before any reload, still resolves to the real message", async ({ page }) => {
  await mockApi(page, {
    turns: [[
      { type: "assistant_message", message_id: "a1", content: "trả lời ngay", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0.01, unknown_cost_calls: 0 },
    ]],
  });
  await page.goto("/");
  await page.getByRole("textbox").fill("gõ nhầm rồi");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText("trả lời ngay");

  await page.getByTestId("message-user").locator(".fork-button").click();

  await expect(page.getByRole("textbox")).toHaveValue("gõ nhầm rồi");
  await expect(page.getByRole("textbox")).toBeFocused();
  await expect(page.getByTestId("fork-origin")).toBeVisible();
});
