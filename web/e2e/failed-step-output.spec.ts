import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FAILED_KEPT_CHARS } from "../src/lib/step-preview";
import { type Conversation, defaultAgent, mockApi, run } from "./mock-api";

const LONG = "https://selfhostedknowledgebaseofthewholehouseholdandtheneighbours.example.test/workspaces/home/pages";
const ADVICE = "Hãy gọi workspace_write trực tiếp để chủ duyệt.";
/** As long as a failed step is ever kept at, with a word that has nowhere to break, ending
 *  with what to do instead. Opens the way the thread tells a stored reply failed. */
const REASON = `Công cụ lỗi: ${LONG} ${"script chỉ đọc không được ghi. ".repeat(30)}`.slice(0, FAILED_KEPT_CHARS - ADVICE.length) + ADVICE;

const failed = { kind: "tool", name: "workspace_write", tool_call_id: "w1", arguments: { path: "a.md" }, ok: false, output: REASON, duration_ms: 20 };
const done = { kind: "tool", name: "workspace_read", tool_call_id: "r1", arguments: { path: "a.md" }, ok: true, output: "hai dòng\n".repeat(60), duration_ms: 20 };
const kept = run({ id: "kept", conversation_id: "c1", title: "Ghi a.md", status: "error", summary: "", steps: [failed, done] });

const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };
const asking = { id: "w1", name: "workspace_write", arguments: { path: "a.md" } };

const conversation = (): Conversation => ({
  id: "c1", agent_id: "default", channel: "", title: "Ghi chú", summary: "", created_at: "", updated_at: "",
  autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
  status: "idle", over_budget: false, parent_call_id: "", pending_approval: null,
  messages: [
    { ...STORED, id: "1", seq: 1, role: "user", content: "Ghi a.md" },
    { ...STORED, id: "2", seq: 2, role: "assistant", content: "", tool_calls: [asking], provider: "fake", model: "echo" },
    { ...STORED, id: "3", seq: 3, role: "tool", content: REASON, tool_call_id: "w1", name: "workspace_write" },
  ],
});

/** How the box of a reason sits: what of it is cut off or scrolled to, and where its edges are. */
const fit = (box: Locator) =>
  box.evaluate((el) => {
    const { left, right } = el.getBoundingClientRect();
    return { below: el.scrollHeight - el.clientHeight, beside: el.scrollWidth - el.clientWidth, left, right, cap: getComputedStyle(el).maxHeight };
  });

/** The reason is there without a press, all of it, wrapped inside the screen. */
async function readsWhole(page: Page, within: Locator, width: number) {
  const box = within.locator(".tool-output");
  await expect(box).toHaveText(REASON);
  await expect(box.getByText(ADVICE)).toBeInViewport({ ratio: 0 });
  const sits = await fit(box);
  expect(sits.cap).toBe("none");
  expect(sits.below).toBeLessThanOrEqual(1);
  expect(sits.beside).toBeLessThanOrEqual(1);
  expect(sits.left).toBeGreaterThanOrEqual(0);
  expect(sits.right).toBeLessThanOrEqual(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

for (const width of [1440, 1000, 390]) {
  test.describe(`a failed step at ${width}px`, () => {
    test.use({ viewport: { width, height: 844 } });

    test("says why on the run's page without a press, whole, and a step that went through stays folded", async ({ page }) => {
      await mockApi(page, { agents: [defaultAgent], runs: [kept], conversations: [conversation()] });
      await page.goto("/#/manage/activity/kept");

      const steps = page.getByTestId("run-replay").getByTestId("run-step");
      await expect(steps).toHaveCount(2);
      await expect(steps.first()).toHaveAttribute("data-state", "failed");
      await steps.first().locator(".tool-output").scrollIntoViewIfNeeded();
      await readsWhole(page, steps.first(), width);

      // The compact look a step that went through always had: folded, and opened it scrolls.
      await expect(steps.nth(1).locator(".tool-output")).toHaveCount(0);
      await steps.nth(1).getByRole("button", { name: vi.showOutput }).click();
      const scrolls = await fit(steps.nth(1).locator(".tool-output"));
      expect(scrolls.cap).not.toBe("none");
      expect(scrolls.below).toBeGreaterThan(0);
    });

    test("says why on its card in the chat and on the chat's own activity, whole", async ({ page }) => {
      await mockApi(page, { agents: [defaultAgent], runs: [kept], conversations: [conversation()] });
      await page.goto("/#/chat/c1");

      const card = page.getByTestId("tool-card");
      await expect(card).toHaveCount(1);
      await card.locator(".tool-output").scrollIntoViewIfNeeded();
      await readsWhole(page, card, width);

      const activity = page.getByTestId("conversation-activity");
      const expand = activity.getByRole("button", { name: vi.conversationActivity.expand });
      if (await expand.count()) await expand.click();
      const step = activity.getByTestId("run-step").first();
      if (!(await step.count())) await activity.getByTestId("run-card").getByRole("button", { expanded: false }).first().click();
      await expect(step).toHaveAttribute("data-state", "failed");
      await step.locator(".tool-output").scrollIntoViewIfNeeded();
      await readsWhole(page, step, width);
    });
  });
}
