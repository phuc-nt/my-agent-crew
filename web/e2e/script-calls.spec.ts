import { expect, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";
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

  // The calls come before what the script printed: what was done, then what it said.
  const placed = await steps.first().evaluate((row) => {
    const made = row.querySelector('[data-testid="script-calls"]')!;
    const toggle = [...row.querySelectorAll(":scope > button.link-button")].pop()!;
    const asked = row.querySelector(".tool-arguments")!;
    const after = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const line = made.querySelector("summary")!;
    const words = document.createRange();
    words.selectNodeContents(line);
    return {
      order: [after(asked, made), after(made, toggle)],
      indent: made.getBoundingClientRect().left - asked.getBoundingClientRect().left,
      beyondWords: line.getBoundingClientRect().right - words.getBoundingClientRect().right,
      room: made.getBoundingClientRect().right - words.getBoundingClientRect().right,
    };
  });
  expect(placed.order).toEqual([true, true]);
  // They line up under what the script was asked, like every other part of the row.
  expect(Math.abs(placed.indent)).toBeLessThanOrEqual(1);
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
    const kept = run({ id: "kept", agent_id: "coach", title: "Gom ghi chú", steps: [script({ ok: true, output: "Có 3 trang.", duration_ms: 73_000, calls: made })] });
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
