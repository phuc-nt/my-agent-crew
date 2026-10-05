import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { type Conversation, mockApi } from "./mock-api";

/**
 * A message the server took, whose answer was lost on the way back. The words return to the
 * box, as for any send nothing was heard of, and sending them again says them once: the
 * second request goes under the name of the first, and the server answers with what the
 * first already got.
 */

const ASKED = "tóm tắt giúp tôi";
const ANSWER = "Đây là bản tóm tắt.";

function conversation(id: string, title: string): Conversation {
  return {
    id, agent_id: "default", channel: "", title, summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

const answered = [
  { type: "assistant_message", message_id: "2", content: ANSWER, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

for (const lostAnswers of [1, 0]) {
  const name = lostAnswers ? "a message whose answer was lost is said once when it is sent again" : "a message that was answered is sent once";
  test(name, async ({ page }) => {
    const mock = await mockApi(page, { conversations: [conversation("c1", "Rớt mạng")], turns: [answered], lostAnswers });
    await page.goto("/#/chat/c1");
    const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
    await box.fill(ASKED);
    await box.press("Enter");

    if (lostAnswers) {
      await expect(page.getByTestId("notice")).toContainText(vi.requestErrors.network);
      await expect(box).toHaveValue(ASKED);
      await expect(page.getByTestId("message-user")).toHaveCount(0);
      await box.press("Enter");
    }

    await expect(page.getByTestId("message-assistant")).toContainText(ANSWER);
    await expect(page.getByTestId("message-assistant")).toHaveCount(1);
    await expect(page.getByTestId("message-user")).toHaveCount(1);
    await expect(page.getByTestId("message-user")).toContainText(ASKED);
    await expect(box).toHaveValue("");
    await expect(page.getByTestId("thinking")).toHaveCount(0);

    const sends = mock.posted.filter((p) => p.path === "/conversations/c1/messages").map((p) => p.body as { request_id: string });
    expect(sends).toHaveLength(lostAnswers + 1);
    expect(sends[0].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(new Set(sends.map((s) => s.request_id)).size).toBe(1);
    // One message from the person and one answer are all the server ever stored.
    expect(mock.conversations[0].messages.map((m) => (m as { role: string }).role)).toEqual(["user", "assistant"]);
  });
}
