import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { coachAgent, defaultAgent, mockApi, run } from "./mock-api";
import { spills } from "./spills";

// A touch screen at the width people hold: the pointer is coarse, as on an iPhone.
test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const { kind: _kind, ...briefRow } = coachAgent.schedules[0];
// As a script is: more lines than a row can spend, and a first line whose path has nowhere
// to break, an underscore being no place a line may end.
const SOURCE = [
  `orders = tools.workspace_read(path="${"thu_muc_rat_dai_".repeat(8)}orders.json")`,
  "new = [order for order in orders if order['status'] == 'new']",
  "if new:",
  "    for order in new:",
  "        print(order['id'], order['shop'], order['total'])",
  "    print(len(new), 'đơn mới')",
  "else:",
  "    pass",
  "",
].join("\n");
const THEN = `Tóm tắt các đơn mới cho chủ, nêu tổng tiền từng cửa hàng và đơn nào còn chờ giao. ${"khong_co_cho_ngat_".repeat(8)}`;
const syncRow = { id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", every: null, prompt: null, command: null, script: SOURCE, then_prompt: THEN, enabled: true, skills: [] };
const coach = { ...coachAgent, declared: { delegates: [], schedules: [syncRow, { ...briefRow, script: null, then_prompt: null }], tools: [] } };
const listed = { agent_id: "coach", next_run: null, last_run: null, running: false, paused: false };
const jobs = [
  { ...syncRow, kind: "script", id: "coach/sync", schedule_id: "sync", ...listed },
  { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", ...listed },
];

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);
/** The list and the form fade in; a box is measured once it has stopped moving. The pulse
 *  of a run still going never ends, and is no part of where a box stands. */
const settled = (page: Page) =>
  page.evaluate(() => {
    const ends = (animation: Animation) => Number.isFinite(Number(animation.effect?.getComputedTiming().endTime));
    return Promise.all(document.getAnimations().filter(ends).map((animation) => animation.finished));
  });

test("a script job's row shows the start of its script and stays inside the page", async ({ page }) => {
  await mockApi(page, { agents: [master, coach], jobs });
  await page.goto("/#/manage/jobs");
  const row = page.getByTestId("job").filter({ hasText: "Đồng bộ đơn" });
  await expect(row).toContainText(`40 6 * * * · ${vi.jobKindScript}`);
  await expect(row.getByTestId("job-script")).toBeVisible();
  await expect(row.getByTestId("job-then-prompt")).toContainText(vi.jobThenPrompt);
  await settled(page);

  expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  expect(await spills(page, '[data-testid="job-script"]')).toEqual([]);
  expect(await spills(page, '[data-testid="job-then-prompt"]')).toEqual([]);
  // Cut to its first lines, with more below: at full length one row would be a page.
  const heights = await row.evaluate((el) => {
    const lines = (box: HTMLElement) => {
      const probe = box.appendChild(document.createElement("span"));
      probe.style.cssText = "display:block;height:1lh";
      const line = probe.getBoundingClientRect().height;
      probe.remove();
      return { shown: box.clientHeight / line, whole: box.scrollHeight / line };
    };
    return { script: lines(el.querySelector(".job-script-source")!), then: lines(el.querySelector(".job-then-prompt")!) };
  });
  expect(heights.script.shown).toBeLessThanOrEqual(6.1);
  expect(heights.script.whole).toBeGreaterThan(heights.script.shown);
  expect(heights.then.shown).toBeLessThanOrEqual(2.1);
  // The job beside it runs no script and has neither line.
  const other = page.getByTestId("job").filter({ hasText: "Bản tin sáng" });
  await expect(other.getByTestId("job-script")).toHaveCount(0);
  await expect(other.getByTestId("job-then-prompt")).toHaveCount(0);
});

test("a script row in the editor is typed in where it stands, and what is typed is what is saved", async ({ page }) => {
  await mockApi(page, { agents: [master, coach], jobs });
  await page.goto("/#/manage/crew/coach/schedules");
  const editor = page.getByTestId("agent-editor");
  const [row, other] = [editor.getByTestId("schedule-row").nth(0), editor.getByTestId("schedule-row").nth(1)];
  const kinds = (of: Locator) => of.getByRole("group", { name: vi.editor.scheduleAction }).getByRole("button");
  // Every row chooses among the three, and the one it is, is the one pressed.
  for (const each of [row, other]) await expect(kinds(each)).toHaveText([vi.editor.schedulePrompt, vi.editor.scheduleCommand, vi.editor.scheduleScript]);
  await expect(kinds(row).nth(2)).toHaveAttribute("aria-pressed", "true");
  await expect(kinds(other).nth(0)).toHaveAttribute("aria-pressed", "true");
  await expect(row.getByText(vi.editor.scheduleScriptHint)).toBeVisible();
  await expect(row.getByText(vi.editor.scheduleThenPromptHint)).toBeVisible();
  await settled(page);

  const script = row.getByLabel(vi.editor.scheduleScript, { exact: true });
  for (const [box, text] of [[script, SOURCE], [row.getByLabel(vi.editor.scheduleThenPrompt, { exact: true }), THEN]] as const) {
    await expect(box).toHaveValue(text);
    await expect(box).toHaveJSProperty("readOnly", false);
    // At the size a phone does not zoom the page into when the box takes focus.
    expect(await box.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  }
  // Three choices on one track: each still a target a thumb can hit, none pushed off the row.
  for (const button of await kinds(row).all()) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(40);
  expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  expect(await spills(page, '[data-testid="schedule-row"]')).toEqual([]);
  await expect(editor.getByRole("button", { name: vi.editor.save, exact: true })).toBeDisabled();

  // Typed at the script's end, the second line indented as Python reads it.
  const ADDED = "if not new:\n    print('không có đơn mới')\n";
  await script.tap();
  await script.evaluate((el: HTMLTextAreaElement) => el.setSelectionRange(el.value.length, el.value.length));
  await page.keyboard.type(ADDED);
  await expect(script).toHaveValue(SOURCE + ADDED);
  expect(await pageWidth(page)).toBeLessThanOrEqual(390);

  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", { name: vi.editor.save, exact: true }).click();
  const sent = (await patch).postDataJSON() as { profile: { schedules: Record<string, unknown>[] } };
  expect(sent.profile.schedules).toEqual([
    { id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", script: SOURCE + ADDED, then_prompt: THEN, enabled: true, skills: [] },
    { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", prompt: "Tóm tắt", enabled: true, skills: ["goodreads"] },
  ]);
  // Taken by the parser's rules, and a reload reads back what the file now holds.
  await expect(editor.getByTestId("restart-banner")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("schedule-row").nth(0).getByLabel(vi.editor.scheduleScript, { exact: true })).toHaveValue(SOURCE + ADDED);
});

test("a call let through the approval gate says so on its own line of the run, beside its time", async ({ page }) => {
  const call = (overrides: Record<string, unknown>) => ({ arguments: { title: "Kế hoạch tuần" }, ok: true, output: "đã tạo", ms: 340, cost_usd: null, metered: false, ...overrides });
  const calls = [
    call({ name: "mcp__notion__search", ms: 120 }),
    call({ name: "mcp__notion__create_page", gated: true }),
    // Both words at once, on the longest name a server is likely to give a tool.
    call({ name: "mcp__google_workspace__calendar_update_recurring_event", ok: false, output: "hết hạn mức", ms: 12_000, gated: true }),
  ];
  const step = { kind: "tool", name: "tool_script", tool_call_id: "ts", arguments: { script: "…" }, ok: true, output: "đã tạo", duration_ms: 12_600, calls };
  const scripting = run({ id: "live", agent_id: "coach", source: "job:coach/sync", status: "running", finished_at: null, spent_usd: 0, summary: "", steps: [step] });
  await mockApi(page, { agents: [defaultAgent, coachAgent], stream: [{ type: "snapshot", runs: [scripting] }] });
  await page.goto("/#/manage/activity");

  const list = page.getByTestId("run-card").filter({ hasText: "HLV sức khoẻ" }).getByTestId("script-calls");
  await list.locator("summary").tap();
  const rows = list.getByTestId("script-call");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0).getByTestId("script-call-gated")).toHaveCount(0);
  await expect(rows.nth(1).getByTestId("script-call-gated")).toHaveText(vi.scriptCallGated);
  await expect(rows.nth(2).getByTestId("script-call-gated")).toBeVisible();
  await settled(page);

  expect(await pageWidth(page)).toBeLessThanOrEqual(390);
  expect(await spills(page, '[data-testid="script-calls"]')).toEqual([]);
  // Where each part of a head stands: the times share a right edge down the list, and the
  // mark sits whole between the name and the time, after the word for a failure.
  const heads = await list.evaluate((el) =>
    [...el.querySelectorAll(".script-call-head")].map((head) => {
      const box = (selector: string) => head.querySelector(selector)?.getBoundingClientRect();
      const [name, failed, gated, time] = [box(".script-call-name")!, box(".step-state.failed"), box(".step-state.gated"), box(".step-time")!];
      return { timeRight: Math.round(time.right), headRight: Math.round(head.getBoundingClientRect().right), nameRight: name.right, failedRight: failed?.right, gatedLeft: gated?.left, gatedRight: gated?.right, timeLeft: time.left, gatedLines: gated ? gated.height : 0, timeLines: time.height };
    }),
  );
  expect(new Set(heads.map((head) => head.timeRight)).size).toBe(1);
  for (const head of heads) expect(head.timeRight).toBeLessThanOrEqual(head.headRight);
  for (const head of heads.slice(1)) {
    expect(head.gatedLeft!).toBeGreaterThanOrEqual(head.nameRight - 1);
    expect(head.gatedRight!).toBeLessThanOrEqual(head.timeLeft + 1);
    // On one line: a mark broken over two would read as two marks.
    expect(head.gatedLines).toBeLessThanOrEqual(head.timeLines * 1.5);
  }
  expect(heads[2].failedRight!).toBeLessThanOrEqual(heads[2].gatedLeft! + 1);
  // As near the time on a call that failed as on one that did not: the mark has a column
  // of its own, and does not move into the one the word for a failure left empty.
  const [alone, withFailure] = heads.slice(1).map((head) => head.timeLeft - head.gatedRight!);
  expect(Math.abs(alone - withFailure)).toBeLessThanOrEqual(1);
});
