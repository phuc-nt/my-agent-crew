import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeCanvas } from "../src/test/fake-canvas";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

const { card } = vi.canvas;
const LETTER = "9c2f41ab07de";
const TITLE = "Thư trả lời";
const CHILD = "3f9a1c0b7d2e";
const ASKED = "soạn thư trả lời khách";
const REPLY = "Thư đã soạn xong.";
const CHILD_REPLY = "Kính gửi anh Minh, hoá đơn tháng 10 đã được gia hạn.";
const SOURCE = [
  'kind = llm.classify(mail, ["hoá đơn", "khác"])',
  'draft = tools.delegate(task="Soạn thư trả lời", agent="coach")',
  'tools.artifact_create(title="Thư trả lời", content=draft)',
].join("\n");

/** The three things the script did on its own, as the server lists them: a model it asked
 *  under a name no tool has, a task it handed off with what the other agent spent, and a
 *  canvas it made, whose tag stands whole at the head of a line that is otherwise cut. */
const classified = {
  name: "llm.classify", arguments: { text: "Kính gửi quý khách, hoá đơn tháng 10…", labels: '["hoá đơn", "khác"]' },
  ok: true, output: "hoá đơn", ms: 812, cost_usd: 0.00021, metered: true,
};
const handedOff = {
  name: "delegate", arguments: { task: "Soạn thư trả lời", agent: "coach" }, ok: true,
  output: `conversation=${CHILD} status=done spent=$0.0123 steps=7 outcome=done Thư đã soạn xong: Kính gửi anh Minh…`,
  ms: 41_000, cost_usd: null, metered: false, child_spent_usd: 0.0123,
};
const wrote = {
  name: "artifact_create", arguments: { title: TITLE, kind: "markdown", content: "Kính gửi anh Minh…" }, ok: true,
  output: `[artifact ${LETTER} v1] Đã tạo canvas "${TITLE}" (markdown).`, ms: 21, cost_usd: null, metered: false, gated: true,
};
const MADE = [classified, handedOff, wrote];

const asking = { id: "ts", name: "tool_script", arguments: { script: SOURCE } };

/** A turn in which the agent runs the script and says how it went, as the server streams it. */
const TURN = [
  { type: "assistant_message", message_id: "a1", content: "", provider: null, model: null, cost_usd: null, tool_calls: [asking] },
  { type: "tool_call", tool_call_id: "ts", name: "tool_script", arguments: asking.arguments },
  ...MADE.map((call, index) => ({ type: "nested_call", tool_call_id: "ts", index, call })),
  { type: "tool_result", tool_call_id: "ts", name: "tool_script", ok: true, output: "xong", calls: MADE, received_chars: 240, printed_chars: 4 },
  { type: "assistant_message", message_id: "a2", content: REPLY, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0.0125, unknown_cost_calls: 0 },
];

const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };

/** A conversation with nothing said in it yet. */
function quiet(): Conversation {
  return {
    id: "c1", agent_id: "default", channel: "", title: "Thư khách", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  };
}

/** The conversation the handed-off task ran in. The call it says opened it is the script's
 *  id and the place of the hand-off among the script's calls: no call of the thread has it. */
function child(): Conversation {
  return {
    ...quiet(), id: CHILD, agent_id: "coach", title: "Soạn thư trả lời", parent_call_id: "ts:1", parent_conversation_id: "c1",
    messages: [
      { ...STORED, id: "k1", seq: 1, role: "user", content: "Soạn thư trả lời" },
      { ...STORED, id: "k2", seq: 2, role: "assistant", content: CHILD_REPLY, provider: "fake", model: "echo" },
    ],
  };
}

const SCREENS = [
  { name: "a wide screen", width: 1440, beside: true, touch: false, use: { viewport: { width: 1440, height: 900 } } },
  { name: "a narrow window", width: 1000, beside: false, touch: false, use: { viewport: { width: 1000, height: 800 } } },
  { name: "a phone", width: 390, beside: false, touch: true, use: { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true } },
] as const;

/** The first message is sent, and the agent answers it by running the script. */
async function runScript(page: Page) {
  const fake = new FakeCanvas();
  fake.add({ id: LETTER, title: TITLE, agent_id: "default", content: "Kính gửi anh Minh…", conversationIds: ["c1"] });
  await mockApi(page, {
    agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent],
    conversations: [quiet(), child()],
    canvas: fake,
    turns: [TURN],
  });
  await page.goto("/#/chat/c1");
  const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
  await box.fill(ASKED);
  await box.press("Enter");
  await expect(page.getByTestId("message-assistant")).toContainText(REPLY);
  return box;
}

const panelTitle = (page: Page, name: string) => page.getByRole("heading", { level: 2, name });
const openLetter = (page: Page) => page.getByTestId("canvas-card").getByRole("button", { name: card.openLabel(TITLE) });

for (const screen of SCREENS) {
  /** A finger on a phone, the pointer everywhere else. */
  const press = (at: Locator) => (screen.touch ? at.tap() : at.click());

  test.describe(`a script that asked a model, handed a task off and made a canvas, on ${screen.name}`, () => {
    test.use(screen.use);

    test("lists the three on its card, each in its own words, and has the canvas's card under it", async ({ page }) => {
      await runScript(page);

      const own = page.getByTestId("tool-card");
      const list = own.getByTestId("script-calls");
      const calls = list.getByTestId("script-call");
      await expect(own).toHaveAttribute("data-tool", "tool_script");
      await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 0));
      await expect(calls.first()).toBeHidden();

      await press(list.locator("summary"));

      await expect(calls).toHaveCount(3);
      await expect(calls.nth(2)).toBeVisible();
      // The model: said in words, with what it cost, and never by the name it travels under.
      await expect(calls.nth(0).locator(".script-call-name")).toHaveText(vi.scriptModelCall["llm.classify"]);
      await expect(calls.nth(0)).not.toContainText("llm.");
      await expect(calls.nth(0).locator("code")).toHaveCount(0);
      await expect(calls.nth(0).getByTestId("script-call-cost")).toHaveText(vi.stepToolCost("$0.0002"));
      // The task: what the other agent spent, which is no price of this call, and a way in.
      await expect(calls.nth(1).locator("code.script-call-name")).toHaveText("delegate");
      await expect(calls.nth(1).getByTestId("script-call-child-spent")).toHaveText(vi.scriptCallChildSpent("$0.0123"));
      await expect(calls.nth(1).getByTestId("script-call-cost")).toHaveCount(0);
      await expect(calls.nth(1).getByRole("button", { name: vi.delegateOpenChild })).toBeVisible();
      // The canvas: a write the gate let through, listed like any other call.
      await expect(calls.nth(2).locator("code.script-call-name")).toHaveText("artifact_create");
      await expect(calls.nth(2).getByTestId("script-call-gated")).toHaveText(vi.scriptCallGated);
      await expect(calls.nth(0).getByRole("button")).toHaveCount(0);
      await expect(calls.nth(2).getByRole("button")).toHaveCount(0);

      // The canvas has a card of its own, after the script's and outside the list it folds.
      const made = page.getByTestId("canvas-card");
      await expect(made).toHaveCount(1);
      await expect(made).toHaveAttribute("data-tool", "artifact_create");
      await expect(made).toContainText(TITLE);
      await expect(made).toContainText(card.version(card.created, 1));
      const placed = await own.evaluate((box) => {
        const canvas = document.querySelector('[data-testid="canvas-card"]')!;
        return { outside: !box.contains(canvas), after: Boolean(box.compareDocumentPosition(canvas) & Node.DOCUMENT_POSITION_FOLLOWING) };
      });
      expect(placed).toEqual({ outside: true, after: true });

      // Nothing here is wider than the screen, with the list open.
      const inside = (await own.boundingBox())!;
      for (const part of [...(await calls.all()), calls.nth(1).getByRole("button", { name: vi.delegateOpenChild })]) {
        const box = (await part.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(inside.x);
        expect(box.x + box.width).toBeLessThanOrEqual(inside.x + inside.width);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(screen.width);
      expect(await spills(page, '[data-testid="tool-card"]')).toEqual([]);
      expect(await spills(page, '[data-testid="canvas-card"]')).toEqual([]);
      if (screen.touch) {
        // The line that opens the list and the way into the task are both a finger wide.
        expect(await smallTargets(page, '[data-testid="tool-card"] [data-testid="script-calls"]')).toEqual([]);
        expect(await smallTargets(page, '[data-testid="canvas-card"]')).toEqual([]);
      }
    });

    if (screen.beside) {
      test("has the canvas it made open beside the thread, while the keyboard stays in the box", async ({ page }) => {
        const box = await runScript(page);

        await expect(panelTitle(page, TITLE)).toBeVisible();
        await expect(box).toBeFocused();
        await page.keyboard.type("rút gọn");
        await expect(box).toHaveValue("rút gọn");
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(screen.width);
      });

      test("brings the canvas back from its card after it was closed", async ({ page }) => {
        await runScript(page);
        await expect(panelTitle(page, TITLE)).toBeVisible();
        await page.getByRole("button", { name: vi.canvas.close }).click();
        await expect(panelTitle(page, TITLE)).toHaveCount(0);

        await openLetter(page).click();

        await expect(panelTitle(page, TITLE)).toBeVisible();
      });
    } else {
      test("opens no canvas by itself, and the canvas's card opens it", async ({ page }) => {
        await runScript(page);
        await expect(page.getByTestId("canvas-card")).toContainText(TITLE);
        await expect(panelTitle(page, TITLE)).toHaveCount(0);
        await expect(page.getByRole("region", { name: vi.canvas.button })).toHaveCount(0);

        await press(openLetter(page));

        await expect(page.getByRole("region", { name: vi.canvas.button })).toBeVisible();
        await expect(panelTitle(page, TITLE)).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(screen.width);
      });
    }

    test("leads from the task's call into the conversation the task ran in", async ({ page }) => {
      await runScript(page);
      const list = page.getByTestId("tool-card").getByTestId("script-calls");
      await press(list.locator("summary"));

      await press(list.getByRole("button", { name: vi.delegateOpenChild }));

      await expect(page).toHaveURL(new RegExp(`#/chat/${CHILD}$`));
      await expect(page.getByTestId("message-assistant")).toContainText(CHILD_REPLY);
      // The script's card belongs to the conversation that asked, and stays there.
      await expect(page.getByTestId("tool-card")).toHaveCount(0);
    });

    test("has, in Hoạt động, the task's run under the turn that asked and the three on the script's one step", async ({ page }) => {
      // The turn that asked has the script's step and none for the hand-off; the other
      // agent's run says only which conversation asked, and began while that turn ran.
      const step = { kind: "tool", name: "tool_script", tool_call_id: "ts", arguments: asking.arguments, ok: true, output: "xong", duration_ms: 42_000, calls: MADE, received_chars: 240, printed_chars: 4 };
      const asked = run({ id: "asked", conversation_id: "c1", title: "Thư khách", started_at: "2026-09-19T08:00:00Z", finished_at: "2026-09-19T08:01:00Z", spent_usd: 0.0002, steps: [step] });
      const handed = run({ id: "handed", agent_id: "coach", conversation_id: CHILD, source: "delegate:c1", title: "Soạn thư trả lời", started_at: "2026-09-19T08:00:05Z", finished_at: "2026-09-19T08:00:46Z", spent_usd: 0.0123 });
      await mockApi(page, { agents: [{ ...defaultAgent, delegates: ["coach"] }, coachAgent], conversations: [quiet(), child()], runs: [asked, handed] });
      await page.goto("/#/manage/activity");

      const group = page.getByTestId("manage-screen").getByTestId("run-group");
      await expect(group).toHaveCount(1);
      const own = group.locator(':scope > [data-testid="run-card"]');
      await expect(own).toContainText("Thư khách");
      await expect(group.getByTestId("run-children").getByTestId("run-card")).toHaveCount(1);
      await expect(group.getByTestId("run-children").getByTestId("run-card")).toContainText("Soạn thư trả lời");
      // What the other agent spent is its own run's, and the asking run's total stays its own.
      await expect(own.locator(".run-meta")).toContainText("$0.0002");
      await expect(group.getByTestId("run-children").locator(".run-meta")).toContainText("$0.01");

      await expect(own.locator(".run-summary")).toHaveAttribute("aria-expanded", "false");
      await press(own.locator(".run-summary"));
      const stop = own.getByTestId("run-step");
      await expect(stop).toHaveCount(1);
      await expect(stop).toContainText("tool_script");
      const list = stop.getByTestId("script-calls");
      const calls = list.getByTestId("script-call");
      await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 0));
      await press(list.locator("summary"));

      await expect(calls).toHaveCount(3);
      await expect(calls.nth(0).locator(".script-call-name")).toHaveText(vi.scriptModelCall["llm.classify"]);
      await expect(calls.nth(0).getByTestId("script-call-cost")).toHaveText(vi.stepToolCost("$0.0002"));
      await expect(calls.nth(1).getByTestId("script-call-child-spent")).toHaveText(vi.scriptCallChildSpent("$0.0123"));
      await expect(calls.nth(1).getByTestId("script-call-cost")).toHaveCount(0);
      await expect(calls.nth(2).getByTestId("script-call-gated")).toHaveText(vi.scriptCallGated);
      // A run has no thread to stand a canvas's card in: the write is a row of the list.
      await expect(page.getByTestId("canvas-card")).toHaveCount(0);

      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(screen.width);
      expect(await spills(page, '[data-testid="run-group"] [data-testid="script-calls"]')).toEqual([]);
      if (screen.touch) expect(await smallTargets(page, '[data-testid="run-group"] [data-testid="script-calls"]')).toEqual([]);

      await press(calls.nth(1).getByRole("button", { name: vi.delegateOpenChild }));

      await expect(page).toHaveURL(new RegExp(`#/chat/${CHILD}$`));
      await expect(page.getByTestId("message-assistant")).toContainText(CHILD_REPLY);
    });
  });
}
