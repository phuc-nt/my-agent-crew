import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { holdTurn } from "./live-stream";
import { type Conversation, coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { liveActivity } from "./served-turn";
import { smallTargets } from "./small-targets";
import { spills } from "./spills";

const SOURCE = 'found = tools.mcp__notion__search(query="kế hoạch")\nprint(len(found))';

/** One call a script made on its own, as the server keeps it on the step (`tools/result.py`). */
const call = (overrides: Record<string, unknown> = {}) => ({
  name: "mcp__notion__search",
  arguments: { query: "kế hoạch" },
  ok: true,
  output: "3 trang",
  ms: 120,
  cost_usd: null,
  metered: false,
  ...overrides,
});

/** The step of the script itself: still open unless `settled` says how it ended. */
const script = (settled: Record<string, unknown> = {}) => ({
  kind: "tool", name: "tool_script", tool_call_id: "ts", arguments: { script: SOURCE }, ok: null, output: null, duration_ms: null, ...settled,
});

const event = (run_id: string, agent_id: string, result: Record<string, unknown>) => ({
  type: "event", run_id, agent_id, conversation_id: null, status: "running", event: { type: "tool_result", ok: true, ...result },
});

test("what a script called arrives with its result and is listed, folded, under its step", async ({ page }) => {
  const made = [
    call(),
    call({ name: "workspace_read", arguments: { path: "notes/ke-hoach.md" }, ok: false, output: "Không có tệp notes/ke-hoach.md", ms: 8 }),
    call({ name: "pdf_read", arguments: { path: "bao-cao.pdf", question: "Tổng chi?" }, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true }),
  ];
  const scripting = run({ id: "live", agent_id: "coach", source: "job:coach/brief", status: "running", finished_at: null, spent_usd: 0, summary: "", steps: [script()] });
  const plain = run({
    id: "plain", title: "Xem ngày", status: "running", finished_at: null, spent_usd: 0, summary: "",
    steps: [{ kind: "tool", name: "shell_run", tool_call_id: "tc", arguments: { command: "date" }, ok: null, output: null, duration_ms: null }],
  });
  await mockApi(page, {
    agents: [defaultAgent, coachAgent],
    stream: [
      { type: "snapshot", runs: [scripting, plain] },
      event("live", "coach", { tool_call_id: "ts", name: "tool_script", output: "3", calls: made }),
      // Every result says what was called on the way; for any other tool that is nothing.
      event("plain", "default", { tool_call_id: "tc", name: "shell_run", output: "Fri", calls: [] }),
    ],
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Quản lý/ }).click();

  const panel = page.getByTestId("manage-screen");
  const live = panel.getByTestId("run-card").filter({ hasText: "HLV sức khoẻ" });
  await expect(live).toHaveAttribute("data-status", "running");
  // The script is one stop on the rail, whatever it went on to call.
  const step = live.getByTestId("run-step");
  await expect(step).toHaveCount(1);
  await expect(step).toHaveAttribute("data-state", "done");
  await expect(step).toContainText("tool_script");

  const list = step.getByTestId("script-calls");
  const calls = list.getByTestId("script-call");
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 1));
  await expect(calls).toHaveCount(3);
  await expect(calls.first()).toBeHidden();

  await list.locator("summary").click();

  await expect(calls.first()).toBeVisible();
  await expect(calls.nth(0)).toContainText("mcp__notion__search");
  await expect(calls.nth(0)).toContainText("query=kế hoạch");
  await expect(calls.nth(0)).toHaveAttribute("data-ok", "true");
  await expect(calls.nth(0).locator(".step-state")).toHaveCount(0);
  await expect(calls.nth(0).getByTestId("script-call-output")).toHaveText("3 trang");
  await expect(calls.nth(0).getByTestId("script-call-cost")).toHaveCount(0);
  await expect(calls.nth(1)).toHaveAttribute("data-ok", "false");
  await expect(calls.nth(1).locator(".step-state.failed")).toHaveText(vi.toolFailed);
  await expect(calls.nth(1).getByTestId("script-call-output")).toHaveText("Không có tệp notes/ke-hoach.md");
  await expect(calls.nth(2)).toContainText(vi.stepDuration(1_500));
  await expect(calls.nth(2).getByTestId("script-call-cost")).toHaveText(vi.stepToolCost("$0.0040"));

  // What the script printed is the step's own output, behind the step's own toggle.
  await expect(step.locator(".tool-output")).toHaveCount(0);
  await step.getByRole("button", { name: vi.showOutput }).click();
  await expect(step.locator(".tool-output")).toHaveText("3");

  await list.locator("summary").click();
  await expect(calls.first()).toBeHidden();

  const other = panel.getByTestId("run-card").filter({ hasText: "Xem ngày" });
  await expect(other.getByTestId("run-step")).toHaveAttribute("data-state", "done");
  await expect(other.getByTestId("script-calls")).toHaveCount(0);
});

test("each call a script makes is listed and charged as it ends, and the script is counted once it has ended", async ({ page }) => {
  const paid = call({ name: "pdf_read", arguments: { path: "bao-cao.pdf" }, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true });
  const unpriced = call({ name: "image_read", arguments: { path: "bieu-do.png" }, output: "một biểu đồ", ms: 900, metered: true });
  const said = (inner: Record<string, unknown>) => ({ type: "event", run_id: "live", agent_id: "coach", conversation_id: null, status: "running", event: inner });
  const heard = (index: number, made: Record<string, unknown>) => said({ type: "nested_call", tool_call_id: "ts", index, call: made });
  const activity = await liveActivity(page);
  await mockApi(page, { agents: [defaultAgent, coachAgent] });
  await page.goto("/");
  await page.getByRole("button", { name: /Quản lý/ }).click();
  await activity.emit({
    type: "snapshot",
    runs: [run({ id: "live", agent_id: "coach", source: "job:coach/brief", status: "running", finished_at: null, spent_usd: 0, summary: "", steps: [script()] })],
  });

  const card = page.getByTestId("manage-screen").getByTestId("run-card").filter({ hasText: "HLV sức khoẻ" });
  const step = card.getByTestId("run-step");
  const total = card.locator(".run-meta");
  const list = step.getByTestId("script-calls");
  await expect(step).toHaveAttribute("data-state", "running");
  await expect(total).toHaveText(/\$0\.00(?!\d)/);
  await expect(list).toHaveCount(0);

  // One that paid no model: listed, and the total stays where it was.
  await activity.emit(heard(0, call()));
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(1, 0));
  await expect(total).toHaveText(/\$0\.00(?!\d)/);

  // One that did: the card says so now, with the script still running.
  await activity.emit(heard(1, paid));
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(2, 0));
  await expect(total).toHaveText(/\$0\.0040/);
  await expect(total).not.toContainText("?");
  await expect(step).toHaveAttribute("data-state", "running");
  await expect(step.getByTestId("script-measures")).toHaveCount(0);

  // A stream joined again says its last call once more, and one whose price nobody knows.
  await activity.emit(heard(1, paid), heard(2, unpriced), heard(2, unpriced));
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 0));
  await expect(total).toHaveText(/\$0\.0040 · \? 1(?!\d)/);

  // The result names them all again, in the order the script made them, and one more no
  // event came for: that one alone is added.
  const late = call({ name: "pdf_read", arguments: { path: "phu-luc.pdf" }, output: "Hai trang.", ms: 700, cost_usd: 0.002, metered: true });
  await activity.emit(said({ type: "tool_result", tool_call_id: "ts", name: "tool_script", ok: true, output: "3", calls: [call(), paid, unpriced, late], received_chars: 12_480, printed_chars: 1 }));
  await expect(step).toHaveAttribute("data-state", "done");
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(4, 0));
  await expect(total).toHaveText(/\$0\.0060 · \? 1(?!\d)/);
  await expect(step.getByTestId("script-measures")).toHaveText("Nhận 12.480 ký tự từ 4 lời gọi, trả về 1 ký tự");
  // The count stands under the list it counts, and above what the script printed.
  const order = await step.evaluate((row) => {
    const after = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const [made, count] = [row.querySelector('[data-testid="script-calls"]')!, row.querySelector('[data-testid="script-measures"]')!];
    return [after(made, count), after(count, [...row.querySelectorAll(":scope > button.link-button")].pop()!)];
  });
  expect(order).toEqual([true, true]);
});

test.describe("on the card of the script in the chat", () => {
  const STORED = { tool_calls: [], tool_call_id: null, name: null, cost_usd: null, created_at: "", provider: null, model: null };
  const ASKED = "Gom ghi chú tuần này";
  const asking = { id: "ts", name: "tool_script", arguments: { script: SOURCE } };
  const missing = call({ name: "workspace_read", arguments: { path: "notes/ke-hoach.md" }, ok: false, output: "Không có tệp notes/ke-hoach.md", ms: 8 });
  const paid = call({ name: "pdf_read", arguments: { path: "bao-cao.pdf" }, output: "Tổng chi 4,2 triệu.", ms: 1_500, cost_usd: 0.004, metered: true });

  const conversation = (): Conversation => ({
    id: "c1", agent_id: "default", channel: "", title: "Ghi chú", summary: "", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0,
    status: "idle", over_budget: false, parent_call_id: "", pending_approval: null, messages: [],
  });

  test("the calls are listed as they end, counted with the result, and there again after a reload", async ({ page }) => {
    const turn = await holdTurn(page, "c1");
    const mock = await mockApi(page, { conversations: [conversation()] });
    await page.goto("/#/chat/c1");
    const box = page.getByRole("textbox", { name: vi.composerPlaceholder });
    await box.fill(ASKED);
    await box.press("Enter");
    await expect(page.getByTestId("message-user")).toContainText(ASKED);

    await turn.push(
      { type: "assistant_message", message_id: "2", content: "", tool_calls: [asking], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "tool_call", tool_call_id: "ts", name: "tool_script", arguments: asking.arguments },
      { type: "nested_call", tool_call_id: "ts", index: 0, call: call() },
    );
    const card = page.getByTestId("tool-card");
    const list = card.getByTestId("script-calls");
    const calls = list.getByTestId("script-call");
    await expect(card).toHaveAttribute("data-tool", "tool_script");
    await expect(list.locator("summary")).toHaveText(vi.scriptCalls(1, 0));
    await expect(card.getByTestId("script-measures")).toHaveCount(0);

    await turn.push({ type: "nested_call", tool_call_id: "ts", index: 1, call: missing });
    await expect(list.locator("summary")).toHaveText(vi.scriptCalls(2, 1));
    await expect(card.getByTestId("script-measures")).toHaveCount(0);

    await turn.push({ type: "tool_result", tool_call_id: "ts", name: "tool_script", ok: true, output: "3", calls: [call(), missing, paid], received_chars: 57, printed_chars: 1 });
    await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 1));
    await expect(card.getByTestId("script-measures")).toHaveText("Nhận 57 ký tự từ 3 lời gọi, trả về 1 ký tự");

    // The turn ends, and the server has stored what the card showed beside the output.
    mock.conversations[0].messages.push(
      { ...STORED, id: "1", seq: 1, role: "user", content: ASKED },
      { ...STORED, id: "2", seq: 2, role: "assistant", content: "", tool_calls: [asking], provider: "fake", model: "echo" },
      { ...STORED, id: "3", seq: 3, role: "tool", content: "3", tool_call_id: "ts", name: "tool_script", context: JSON.stringify({ calls: [call(), missing, paid], received_chars: 57, printed_chars: 1 }) },
      { ...STORED, id: "4", seq: 4, role: "assistant", content: "Có 3 trang.", provider: "fake", model: "echo" },
    );
    await turn.push(
      { type: "assistant_message", message_id: "4", content: "Có 3 trang.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0.004, unknown_cost_calls: 0 },
    );
    await turn.close();
    await expect(page.getByTestId("message-assistant")).toContainText("Có 3 trang.");

    await page.reload();

    await expect(page.getByTestId("message-assistant")).toContainText("Có 3 trang.");
    await expect(card).toHaveCount(1);
    await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 1));
    await expect(card.getByTestId("script-measures")).toHaveText("Nhận 57 ký tự từ 3 lời gọi, trả về 1 ký tự");
    await expect(calls.first()).toBeHidden();
    await list.locator("summary").click();
    await expect(calls).toHaveCount(3);
    await expect(calls.nth(0)).toContainText("mcp__notion__search");
    await expect(calls.nth(0)).toContainText(vi.stepDuration(120));
    await expect(calls.nth(1)).toHaveAttribute("data-ok", "false");
    await expect(calls.nth(1).locator(".step-state.failed")).toHaveText(vi.toolFailed);
    await expect(calls.nth(2).getByTestId("script-call-cost")).toHaveText(vi.stepToolCost("$0.0040"));
    // The count has a row of its own, a little under the list, with the toggle under it.
    await list.locator("summary").click();
    const rows = await card.evaluate((box) => {
      const edges = (found: Element) => found.getBoundingClientRect();
      const [made, count] = [edges(box.querySelector('[data-testid="script-calls"]')!), edges(box.querySelector('[data-testid="script-measures"]')!)];
      const toggle = edges([...box.querySelectorAll("button.link-button")].pop()!);
      return { under: count.top - made.bottom, toggle: toggle.top - count.bottom, indent: count.left - made.left };
    });
    expect(rows.under).toBeGreaterThan(0);
    expect(rows.toggle).toBeGreaterThanOrEqual(0);
    expect(Math.abs(rows.indent)).toBeLessThanOrEqual(1);
    // What the script printed stays behind the card's own toggle, under the count.
    await expect(card.locator(".tool-output")).toHaveCount(0);
    await card.getByRole("button", { name: vi.showOutput }).click();
    await expect(card.locator(".tool-output")).toHaveText("3");
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    const LONG = "https://selfhostedknowledgebaseofthewholehouseholdandtheneighbours.example.test/workspaces/home/pages";
    const NAME = "mcp__wiki_of_the_whole_household_2026__query_every_data_source_of_the_whole_workspace_at_once";

    test("the list and the count fit the card however long a name or an answer runs", async ({ page }) => {
      const made = [call({ name: NAME, arguments: { url: LONG }, output: LONG.repeat(3), ms: 12_000, cost_usd: 0.0123, metered: true }), call({ name: NAME, ok: false, output: `Không gọi được ${LONG}`, ms: 61_000 })];
      const kept = conversation();
      kept.messages.push(
        { ...STORED, id: "1", seq: 1, role: "user", content: ASKED },
        { ...STORED, id: "2", seq: 2, role: "assistant", content: "", tool_calls: [asking], provider: "fake", model: "echo" },
        { ...STORED, id: "3", seq: 3, role: "tool", content: "2", tool_call_id: "ts", name: "tool_script", context: JSON.stringify({ calls: made, received_chars: 9_876_543_210, printed_chars: 9_876_543_210 }) },
        { ...STORED, id: "4", seq: 4, role: "assistant", content: "Có 2 trang.", provider: "fake", model: "echo" },
      );
      await mockApi(page, { conversations: [kept] });
      await page.goto("/#/chat/c1");

      const card = page.getByTestId("tool-card");
      const list = card.getByTestId("script-calls");
      await expect(list.locator("summary")).toHaveText(vi.scriptCalls(2, 1));
      // Numbers no script reaches: the line is longer than the card is wide, and has to break.
      await expect(card.getByTestId("script-measures")).toHaveText("Nhận 9.876.543.210 ký tự từ 2 lời gọi, trả về 9.876.543.210 ký tự");
      expect(await smallTargets(page, '[data-testid="tool-card"] [data-testid="script-calls"]')).toEqual([]);

      await list.locator("summary").tap();

      await expect(list.getByTestId("script-call").nth(1)).toBeVisible();
      const inside = (await card.boundingBox())!;
      for (const part of [list, card.getByTestId("script-measures"), ...(await list.getByTestId("script-call").all())]) {
        const box = (await part.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(inside.x);
        expect(box.x + box.width).toBeLessThanOrEqual(inside.x + inside.width);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      expect(await spills(page, '[data-testid="tool-card"]')).toEqual([]);
    });
  });
});

test("a run read back from the server still lists what its script called", async ({ page }) => {
  const kept = run({
    id: "kept", agent_id: "coach", title: "Gom ghi chú",
    steps: [
      script({ ok: false, output: "1 trang\nDòng 3: không gọi được công cụ", duration_ms: 2_400, calls: [call(), call({ ok: false, output: "hết giờ" })] }),
      { kind: "tool", name: "workspace_read", tool_call_id: "tc", arguments: { path: "notes.md" }, ok: true, output: "hai dòng", duration_ms: 20 },
    ],
  });
  await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [kept] });
  await page.goto("/#/manage/activity/kept");

  const steps = page.getByTestId("run-replay").getByTestId("run-step");
  await expect(steps).toHaveCount(2);
  const list = steps.first().getByTestId("script-calls");
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(2, 1));
  await expect(steps.nth(1).getByTestId("script-calls")).toHaveCount(0);

  // The link is the run, so loading it again shows the same list.
  await page.reload();
  await expect(list.locator("summary")).toHaveText(vi.scriptCalls(2, 1));
  await list.locator("summary").click();
  await expect(list.getByTestId("script-call")).toHaveCount(2);
  await expect(list.getByTestId("script-call").nth(1)).toContainText("hết giờ");
  // The word for a failure stands before the time without moving it: the words of every
  // time end where the row ends, so the times line up down their right edge.
  const ends = await list.getByTestId("script-call").evaluateAll((rows) =>
    rows.map((row) => {
      const words = document.createRange();
      words.selectNodeContents(row.querySelector(".step-time")!);
      return words.getBoundingClientRect().right - row.querySelector(".script-call-head")!.getBoundingClientRect().right;
    }),
  );
  expect(ends).toHaveLength(2);
  for (const short of ends) expect(Math.abs(short)).toBeLessThanOrEqual(1);

  // A run kept from before scripts were counted says so with a dash, not a nought.
  await expect(steps.first().getByTestId("script-measures")).toHaveText("Nhận — ký tự từ 2 lời gọi, trả về — ký tự");
  await expect(steps.nth(1).getByTestId("script-measures")).toHaveCount(0);

  // The calls come before what the script printed: what was done, then what it said.
  const placed = await steps.first().evaluate((row) => {
    const made = row.querySelector('[data-testid="script-calls"]')!;
    const count = row.querySelector('[data-testid="script-measures"]')!;
    const toggle = [...row.querySelectorAll(":scope > button.link-button")].pop()!;
    const asked = row.querySelector(".tool-arguments")!;
    const after = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const line = made.querySelector("summary")!;
    const words = document.createRange();
    words.selectNodeContents(line);
    return {
      order: [after(asked, made), after(made, count), after(count, toggle)],
      indent: made.getBoundingClientRect().left - asked.getBoundingClientRect().left,
      countIndent: count.getBoundingClientRect().left - asked.getBoundingClientRect().left,
      // The count has a row of its own: under the list, with the toggle under it.
      rows: [count.getBoundingClientRect().top - made.getBoundingClientRect().bottom, toggle.getBoundingClientRect().top - count.getBoundingClientRect().bottom],
      beyondWords: line.getBoundingClientRect().right - words.getBoundingClientRect().right,
      room: made.getBoundingClientRect().right - words.getBoundingClientRect().right,
    };
  });
  expect(placed.order).toEqual([true, true, true]);
  // They line up under what the script was asked, like every other part of the row.
  expect(Math.abs(placed.indent)).toBeLessThanOrEqual(1);
  expect(Math.abs(placed.countIndent)).toBeLessThanOrEqual(1);
  for (const gap of placed.rows) expect(gap).toBeGreaterThanOrEqual(0);
  // The line that opens them is as wide as its words, though the row had room for far more:
  // a click on the empty part of the row opens nothing.
  expect(placed.room).toBeGreaterThan(100);
  expect(Math.abs(placed.beyondWords)).toBeLessThanOrEqual(1);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  // Nothing in these breaks on its own: no space, and no hyphen a line could end after.
  const LONG = "https://selfhostedknowledgebaseofthewholehouseholdandtheneighbours.example.test/workspaces/home/pages";
  const NAME = "mcp__wiki_of_the_whole_household_2026__query_every_data_source_of_the_whole_workspace_at_once";

  test("the calls of a script fit the screen however long a name, an argument or an answer runs", async ({ page }) => {
    const made = [
      call({ name: NAME, arguments: { url: LONG, cursor: LONG }, output: LONG.repeat(3), ms: 12_000, cost_usd: 0.0123, metered: true }),
      call({ name: NAME, ok: false, output: `Không gọi được ${LONG}`, ms: 61_000 }),
      call(),
    ];
    const counted = { received_chars: 9_876_543_210, printed_chars: 9_876_543_210 };
    const kept = run({ id: "kept", agent_id: "coach", title: "Gom ghi chú", steps: [script({ ok: true, output: "Có 3 trang.", duration_ms: 73_000, calls: made, ...counted })] });
    await mockApi(page, { agents: [defaultAgent, coachAgent], runs: [kept] });
    await page.goto("/#/manage/activity/kept");

    const list = page.getByTestId("run-replay").getByTestId("script-calls");
    const calls = list.getByTestId("script-call");
    await expect(list.locator("summary")).toHaveText(vi.scriptCalls(3, 1));
    // The one line that opens the list is a control, and a finger has to land on it.
    expect(await smallTargets(page, '[data-testid="script-calls"]')).toEqual([]);
    // Its words sit in the middle of the strip the finger gets, not along its top edge.
    const offCentre = await list.locator("summary").evaluate((line) => {
      const words = document.createRange();
      words.selectNodeContents(line);
      const [text, strip] = [words.getBoundingClientRect(), line.getBoundingClientRect()];
      return Math.abs((text.top + text.bottom) / 2 - (strip.top + strip.bottom) / 2);
    });
    expect(offCentre).toBeLessThanOrEqual(2);

    await list.locator("summary").tap();

    await expect(calls).toHaveCount(3);
    await expect(calls.nth(2)).toBeVisible();
    await expect(calls.nth(1).locator(".step-state.failed")).toHaveText(vi.toolFailed);
    for (const index of [0, 1, 2]) {
      const box = (await calls.nth(index).boundingBox())!;
      expect(box.x, `call ${index}`).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, `call ${index}`).toBeLessThanOrEqual(390);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    // A long name, address or answer goes onto the next line inside its own row.
    expect(await spills(page, '[data-testid="script-calls"]')).toEqual([]);
    // So does the count under them, with numbers no script reaches.
    const count = page.getByTestId("run-replay").getByTestId("script-measures");
    await expect(count).toHaveText("Nhận 9.876.543.210 ký tự từ 3 lời gọi, trả về 9.876.543.210 ký tự");
    const edge = (await count.boundingBox())!;
    expect(edge.x).toBeGreaterThanOrEqual(0);
    expect(edge.x + edge.width).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="script-measures"]')).toEqual([]);
    // The time and the word for a failure stay whole beside a name that had to wrap.
    const heads = await calls.evaluateAll((rows) =>
      rows.map((row) => {
        const lines = (el: Element | null) => (el ? Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)) : 0);
        return [lines(row.querySelector(".step-time")), lines(row.querySelector(".step-state"))];
      }),
    );
    expect(heads).toEqual([[1, 0], [1, 1], [1, 0]]);
  });
});
