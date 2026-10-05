import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { type Conversation, mockApi, run } from "./mock-api";
import { liveActivity, serveTurn } from "./served-turn";

/**
 * A turn belongs to the server: a tab that did not start it, or stopped reading it, reads
 * along from where the turn stands. These run against the real DOM with the turn's stream
 * and the activity stream made in the page (see `served-turn.ts`).
 */

const ASKED = "kể một câu chuyện";
const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };

function conversation(id: string, title: string, asked?: string): Conversation {
  return {
    id, agent_id: "default", channel: "", title, summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
    messages: asked ? [{ ...STORED, id: "1", seq: 1, role: "user", content: asked }] : [],
  };
}

const going = (source: string) => run({ id: "r1", conversation_id: "c1", source, status: "running", finished_at: null, summary: "" });
const over = (source: string) => run({ id: "r1", conversation_id: "c1", source, status: "done" });
const text = (piece: string) => ({ type: "text_delta", text: piece });

/** The page on c1 while a turn it did not start is writing `written` there. */
async function openMidTurn(page: Page, source: string, written: string, stoppable = false) {
  const turn = await serveTurn(page, "c1", { writing: [text(written)], stoppable });
  const activity = await liveActivity(page);
  const mock = await mockApi(page, { conversations: [conversation("c1", "Chuyện kể", ASKED), conversation("c2", "Cuộc khác")] });
  await page.goto("/#/chat/c1");
  await expect(page.getByTestId("message-user")).toContainText(ASKED);
  await activity.emit({ type: "snapshot", runs: [going(source)] });
  return { turn, activity, mock };
}

for (const width of [1440, 1000, 390]) {
  test(`a turn started elsewhere is shown as it is written and followed to its end (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const { turn, activity, mock } = await openMidTurn(page, "telegram", "Ngày xửa ");
    const writing = page.getByTestId("streaming");
    await expect(writing).toContainText("Ngày xửa");
    // The bot's turn: there to read, not this tab's to end.
    await expect(page.getByRole("button", { name: vi.stop })).toHaveCount(0);

    await turn.push(text("ngày xưa"));
    await expect(writing).toContainText("Ngày xửa ngày xưa");

    const answer = "Ngày xửa ngày xưa, có một chú mèo.";
    mock.conversations[0].messages.push({ ...STORED, id: "2", seq: 2, role: "assistant", content: answer, provider: "fake", model: "echo" });
    await turn.push(
      { type: "assistant_message", message_id: "2", content: answer, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    );
    await turn.end();
    await activity.emit({ type: "run", run: over("telegram") });

    await expect(writing).toHaveCount(0);
    await expect(page.getByTestId("thinking")).toHaveCount(0);
    await expect(page.getByTestId("message-assistant")).toHaveCount(1);
    await expect(page.getByTestId("message-assistant")).toContainText(answer);
    await expect(page.getByTestId("message-user")).toHaveCount(1);
    // Nothing the turn did pushed the page sideways.
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}

test("a reload mid-turn picks the turn up where it stands", async ({ page }) => {
  const { turn, activity } = await openMidTurn(page, "chat", "phần một", true);
  await expect(page.getByTestId("streaming")).toContainText("phần một");

  await page.reload();
  await expect(page.getByTestId("message-user")).toContainText(ASKED);
  await activity.emit({ type: "snapshot", runs: [going("chat")] });
  await expect(page.getByTestId("streaming")).toContainText("phần một");
  await expect(page.getByTestId("message-user")).toHaveCount(1);
  expect(await turn.stops()).toBe(0);
});

test("leaving the conversation leaves the turn going, and coming back joins it again", async ({ page }) => {
  const { turn } = await openMidTurn(page, "chat", "phần một", true);
  await expect(page.getByTestId("streaming")).toContainText("phần một");
  expect(await turn.watchers()).toBe(1);

  await page.goto("/#/chat/c2");
  await expect(page.getByRole("heading", { level: 1, name: "Cuộc khác" })).toBeVisible();
  await expect.poll(() => turn.watchers()).toBe(0);
  await expect(page.getByTestId("streaming")).toHaveCount(0);
  expect(await turn.stops()).toBe(0); // leaving is not stopping

  await turn.write(text("phần một, phần hai")); // the turn kept writing meanwhile
  await page.goto("/#/chat/c1");
  await expect(page.getByTestId("streaming")).toContainText("phần một, phần hai");
  await expect(page.getByTestId("message-user")).toHaveCount(1);
  expect(await turn.watchers()).toBe(1);
});

test("Stop ends a turn the server reads itself, from a tab that only watches it", async ({ page }) => {
  const { turn, activity } = await openMidTurn(page, "chat", "đang viết", true);
  await expect(page.getByTestId("streaming")).toContainText("đang viết");

  await page.getByRole("button", { name: vi.stop }).click();
  await expect(page.getByTestId("notice")).toContainText(vi.stopped);
  await expect(page.getByTestId("streaming")).toHaveCount(0);
  expect(await turn.stops()).toBe(1);
  expect(await turn.watchers()).toBe(0);

  await activity.emit({ type: "run", run: run({ id: "r1", conversation_id: "c1", source: "chat", status: "error", summary: "interrupted" }) });
  await expect(page.getByTestId("thinking")).toHaveCount(0);
  await expect(page.getByRole("button", { name: vi.stop })).toHaveCount(0);
});
