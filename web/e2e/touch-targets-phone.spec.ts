import { expect, test, type Page } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { smallTargets } from "./small-targets";

// A touch screen at the width people hold, where a finger is the pointer.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

function conversation(id: string, title: string): Conversation {
  return {
    id, agent_id: "default", channel: "", title, summary: "", created_at: "2026-09-19T08:00:00Z", updated_at: "2026-09-19T08:00:00Z",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0.2, unknown_cost_calls: 0, status: "idle",
    over_budget: false, parent_call_id: "", pending_approval: null,
    messages: [
      { id: "m1", seq: 1, role: "user", content: "Tóm tắt giúp tôi", tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "2026-09-19T08:00:00Z" },
      { id: "m2", seq: 2, role: "assistant", tool_call_id: null, name: null, provider: "fake", model: "echo", cost_usd: 0.01, content: "Đây là bản tóm tắt, xem [nguồn](https://example.com).", tool_calls: [], created_at: "2026-09-19T08:00:05Z" },
    ],
  };
}

const waiting = run({
  id: "wait", conversation_id: "c1", status: "awaiting_approval", finished_at: null,
  pending: { call_id: "k1", tool_name: "shell", arguments: { command: "ls" }, kind: "approval", expires_at: null },
});
const failed = run({ id: "bad", conversation_id: "c1", status: "failed", summary: "Lỗi" });
const job = {
  ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach",
  next_run: "2026-09-20T00:00:00Z", last_run: null, running: false, paused: false,
};

async function open(page: Page, hash: string) {
  // A canvas no conversation is linked to: a row of the library, with its delete button.
  const canvas = new FakeCanvas();
  canvas.add({ title: "Ghi chú", agent_id: "coach", source: "workspace:coach/notes/a.md" });
  await mockApi(page, {
    canvas,
    agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent],
    conversations: [conversation("c1", "Tóm tắt tuần"), conversation("c2", "Việc nhà")],
    runs: [waiting, failed, run({ id: "ok", conversation_id: "c2" })],
    jobs: [job],
  });
  await page.goto(hash);
}

const PAGES: [string, string][] = [
  ["the chat", "/#/chat/c1"],
  ["activity", "/#/manage/activity"],
  ["approvals", "/#/manage/approvals"],
  ["costs", "/#/manage/costs"],
  ["crew", "/#/manage/crew"],
  ["an agent's editor", "/#/manage/crew/coach"],
  ["tools", "/#/manage/tools"],
  ["jobs", "/#/manage/jobs"],
  ["memory", "/#/manage/memory"],
  ["the canvas library", "/#/manage/canvas"],
  ["connections", "/#/manage/connections"],
  ["settings", "/#/manage/settings"],
];

for (const [name, hash] of PAGES) {
  test(`every control on ${name} is big enough for a finger`, async ({ page }) => {
    await open(page, hash);
    await expect(page.locator("main").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await smallTargets(page)).toEqual([]);
  });
}

test("every control in the phone's conversation drawer is big enough for a finger", async ({ page }) => {
  await open(page, "/#/chat/c1");
  await page.getByRole("button", { name: /^Mở danh sách cuộc trò chuyện/ }).tap();
  await expect(page.locator(".sidebar")).not.toHaveAttribute("inert");
  await expect(page.locator(".sidebar").getByRole("button", { name: /Việc nhà/ })).toBeInViewport();
  expect(await smallTargets(page)).toEqual([]);
});

const PLAN = "00ff00ff00ff";

/** A saved conversation whose first message went with a canvas note, and in which the agent made a canvas. */
function withCanvas(): Conversation {
  const call = { id: "w1", name: "artifact_create", arguments: { title: "Kế hoạch tuần", content: "Việc một" } };
  const stored = { tool_calls: [], tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "" };
  return {
    ...conversation("c1", "Kế hoạch"),
    messages: [
      { ...stored, id: "m1", seq: 1, role: "user", content: "viết kế hoạch", context: "[Canvas · Ghi chú]\n> chạy 5 km" },
      { ...stored, id: "m2", seq: 2, role: "assistant", content: "", tool_calls: [call] },
      { ...stored, id: "m3", seq: 3, role: "tool", content: `[artifact ${PLAN} v1]\nCanvas "Kế hoạch tuần" was created.`, tool_call_id: "w1", name: "artifact_create" },
      { ...stored, id: "m4", seq: 4, role: "assistant", content: "Xong." },
    ],
  };
}

test("the canvas card's Open button and the note chip in the thread are big enough for a finger", async ({ page }) => {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: "Kế hoạch tuần", agent_id: "master", conversationIds: ["c1"] });
  await mockApi(page, { conversations: [withCanvas()], canvas: fake });
  await page.goto("/#/chat/c1");
  await expect(page.getByRole("button", { name: vi.canvas.card.openLabel("Kế hoạch tuần") })).toBeVisible();
  await expect(page.getByRole("button", { name: vi.canvas.noteChip })).toBeVisible();

  expect(await smallTargets(page, ".canvas-card")).toEqual([]);
  expect(await smallTargets(page, ".canvas-note")).toEqual([]);
});

test("the buttons of the bar that asks about a passage of the canvas are big enough for a finger", async ({ page }) => {
  const text = "Việc một\n\nViệc hai";
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: "Kế hoạch tuần", content: text, conversationIds: ["c1"] });
  await mockApi(page, { conversations: [conversation("c1", "Kế hoạch")], canvas: fake });
  await page.goto("/#/chat/c1");
  await page.getByRole("button", { name: vi.canvas.buttonLabel(1) }).tap();
  await page.getByRole("button", { name: /Kế hoạch tuần/ }).tap();
  const field = page.getByRole("textbox", { name: vi.canvas.editor });
  await expect(field).toHaveValue(text);
  await field.focus();
  await field.evaluate((el: HTMLTextAreaElement) => el.setSelectionRange(0, 8));

  const bar = page.getByRole("group", { name: vi.canvas.ask.group });
  await expect(bar).toBeVisible();
  expect(await smallTargets(page, ".canvas-ask")).toEqual([]);

  // With the box open it holds the question and the two buttons that send or put it away.
  await bar.getByRole("button", { name: vi.canvas.ask.button }).tap();
  await expect(bar.getByRole("textbox", { name: vi.canvas.ask.question })).toBeVisible();
  await expect(bar.getByRole("button", { name: vi.send, exact: true })).toBeVisible();
  await expect(bar.getByRole("button", { name: vi.canvas.ask.cancel })).toBeVisible();
  expect(await smallTargets(page, ".canvas-ask")).toEqual([]);
});

test("every control on a canvas's own page is big enough for a finger, a conversation named in one letter too", async ({ page }) => {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: "Kế hoạch tuần", content: "Việc một", conversationIds: ["c1", "c2"] });
  await mockApi(page, { conversations: [conversation("c1", "A"), conversation("c2", "Việc nhà")], canvas: fake });
  await page.goto(`/#/manage/canvas/${PLAN}`);
  await expect(page.getByRole("textbox", { name: vi.canvas.editor })).toHaveValue("Việc một");
  await expect(page.locator(".canvas-page-used").getByRole("button")).toHaveText(["A", "Việc nhà"]);
  await expect(page.getByRole("button", { name: vi.canvas.back })).toBeVisible();

  expect(await smallTargets(page)).toEqual([]);
});

test("the name that opens a canvas from the library is big enough for a finger, one letter long too", async ({ page }) => {
  const fake = new FakeCanvas();
  fake.add({ id: PLAN, title: "A" });
  await mockApi(page, { canvas: fake });
  await page.goto("/#/manage/canvas");
  await expect(page.getByRole("button", { name: "A", exact: true })).toBeVisible();

  expect(await smallTargets(page, ".canvas-library")).toEqual([]);
});
