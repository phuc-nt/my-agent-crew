import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { type Conversation, mockApi, run } from "./mock-api";
import { liveActivity, serveTurn } from "./served-turn";

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

test("the same words sent again once the turn they started has ended are a new message", async ({ page }) => {
  // The answer to the first send is lost and its turn runs on the server all the same. The
  // page reads along with it to its end, and the words it handed back are sent again: the
  // next step the person asks for, which the name of the first send would start no turn for.
  const NEXT = "Đây là bản tóm tắt thứ hai.";
  const turn = await serveTurn(page, "c1", { writing: [{ type: "text_delta", text: "Đang tóm tắt" }], stoppable: true });
  const activity = await liveActivity(page);
  const next = [
    { type: "assistant_message", message_id: "4", content: NEXT, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
    { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
  ];
  const mock = await mockApi(page, { conversations: [conversation("c1", "Rớt mạng")], turns: [[], next], lostAnswers: 1 });
  const sends = () => mock.posted.filter((p) => p.path === "/conversations/c1/messages").map((p) => p.body as { request_id: string });
  await page.goto("/#/chat/c1");
  await activity.emit({ type: "snapshot", runs: [] });
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill(ASKED);
  await box.press("Enter");
  await expect(page.getByTestId("notice")).toContainText(vi.requestErrors.network);
  await expect(box).toHaveValue(ASKED);

  await activity.emit({ type: "run", run: run({ id: "r1", conversation_id: "c1", source: "chat", status: "running", finished_at: null, summary: "" }) });
  await expect(page.getByTestId("streaming")).toContainText("Đang tóm tắt");
  mock.conversations[0].messages.push({
    id: "2", seq: 2, role: "assistant", content: ANSWER, tool_calls: [], tool_call_id: null, name: null,
    provider: "fake", model: "echo", cost_usd: 0, created_at: "",
  });
  await turn.push(...answered);
  await turn.end();
  await activity.emit({ type: "run", run: run({ id: "r1", conversation_id: "c1", source: "chat", status: "done" }) });
  await expect(page.getByTestId("streaming")).toHaveCount(0);
  await expect(page.getByTestId("message-assistant")).toContainText(ANSWER);
  await expect(box).toHaveValue(ASKED);

  await box.press("Enter");

  await expect.poll(() => sends().length).toBe(2);
  expect(sends()[1].request_id).toMatch(/^[0-9a-f]{32}$/);
  expect(sends()[1].request_id).not.toBe(sends()[0].request_id);
  await expect(page.getByTestId("message-assistant")).toHaveCount(2);
  await expect(page.getByTestId("message-assistant").nth(1)).toContainText(NEXT);
  await expect(page.getByTestId("message-user")).toHaveCount(2);
  await expect(box).toHaveValue("");
  await expect(page.getByTestId("thinking")).toHaveCount(0);
  // Each send was stored as a message of its own, with the answer its turn gave.
  expect(mock.conversations[0].messages.map((m) => (m as { role: string }).role)).toEqual(["user", "assistant", "user", "assistant"]);
});
