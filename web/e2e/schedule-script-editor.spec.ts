import { expect, type Locator, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";
import { spills } from "./spills";

const t = vi.editor;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
const { kind: _kind, ...briefRow } = coachAgent.schedules[0];
const brief = { ...briefRow, script: null, then_prompt: null };
const sync = { ...brief, id: "sync", name: "Đồng bộ đơn", cron: "40 6 * * *", prompt: null, script: "print(1)\n", skills: [] };
/** Coach, with the schedules its profile file declares. */
const declaring = (...schedules: object[]) => ({ ...coachAgent, declared: { delegates: [], schedules, tools: [] } });

// Two levels of indentation, typed as spaces: the form does not indent for the person.
const SCRIPT = ['orders = tools.workspace_read(path="orders.json")', "for order in orders:", '    if order["new"]:', '        print(order["id"])'].join("\n");
const THEN = "Tóm tắt các đơn mới cho chủ";
const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
];

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);
const rows = (page: Page) => page.getByTestId("agent-editor").getByTestId("schedule-row");
const box = (row: Locator, label: string) => row.getByLabel(label, { exact: true });
const pick = (row: Locator, kind: string) => row.getByRole("group", { name: t.scheduleAction }).getByRole("button", { name: kind, exact: true }).click();
const save = (page: Page) => page.getByTestId("agent-editor").getByRole("button", { name: t.save, exact: true });

for (const viewport of VIEWPORTS) {
  test(`a schedule that runs a script is written, saved and read back at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page, { agents: [master, declaring(brief)] });
    await page.goto("/#/manage/crew/coach/schedules");
    await page.getByTestId("agent-editor").getByRole("button", { name: t.addSchedule }).click();
    const row = rows(page).nth(1);
    await box(row, t.scheduleName).fill("Đồng bộ đơn");
    await box(row, t.scheduleCron).fill("40 6 * * *");

    // Words meant as a prompt, then the row is made a script: its box opens empty, since a
    // prompt carried over would be run as code.
    await box(row, t.schedulePrompt).fill("Chào buổi sáng");
    await pick(row, t.scheduleScript);
    const script = box(row, t.scheduleScript);
    await expect(script).toHaveValue("");
    await expect(box(row, t.schedulePrompt)).toHaveCount(0);
    await expect(script).toHaveAccessibleDescription(t.scheduleScriptHint);
    await expect(box(row, t.scheduleThenPrompt)).toHaveAccessibleDescription(t.scheduleThenPromptHint);

    await script.click();
    await page.keyboard.type(SCRIPT);
    await expect(script).toHaveValue(SCRIPT);
    // Tab leaves the box, as it leaves every other, and puts nothing in the script.
    await page.keyboard.press("Tab");
    await expect(box(row, t.scheduleThenPrompt)).toBeFocused();
    await page.keyboard.type(THEN);
    await expect(script).toHaveValue(SCRIPT);

    // Tapping another kind by mistake loses nothing: each kind finds its own words again.
    await pick(row, t.schedulePrompt);
    await expect(box(row, t.schedulePrompt)).toHaveValue("Chào buổi sáng");
    await expect(box(row, t.scheduleScript)).toHaveCount(0);
    await pick(row, t.scheduleScript);
    await expect(script).toHaveValue(SCRIPT);
    await expect(box(row, t.scheduleThenPrompt)).toHaveValue(THEN);

    expect(await pageWidth(page)).toBeLessThanOrEqual(viewport.width);
    expect(await spills(page, '[data-testid="schedule-row"]')).toEqual([]);

    const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
    await save(page).click();
    const sent = (await patch).postDataJSON() as { profile: { schedules: Record<string, unknown>[] } };
    // The script alone, of the three: the prompt the row once held is not written.
    expect(sent.profile.schedules).toEqual([
      { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", prompt: "Tóm tắt", enabled: true, skills: ["goodreads"] },
      { name: "Đồng bộ đơn", cron: "40 6 * * *", script: SCRIPT, then_prompt: THEN, enabled: true, skills: [] },
    ]);
    await expect(page.getByTestId("restart-banner")).toBeVisible();

    // Reloading shows what the server kept: the script as typed, under the id it was given.
    await page.reload();
    await expect(box(rows(page).nth(1), t.scheduleScript)).toHaveValue(SCRIPT);
    await expect(box(rows(page).nth(1), t.scheduleThenPrompt)).toHaveValue(THEN);
    await expect(box(rows(page).nth(1), t.scheduleId)).toHaveValue("job-1");
    await expect(save(page)).toBeDisabled();
  });

  // Several rows look alike, and the section is far down the form: the row whose link was
  // pressed is the one brought into view, clear of the sticky bar, and a reload keeps it.
  test(`Sửa lịch of a script job lands on that job's row, not the first, at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const listed = { agent_id: "coach", next_run: null, last_run: null, running: false, paused: false };
    const jobs = [
      { ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", ...listed },
      { ...sync, kind: "script", id: "coach/sync", schedule_id: "sync", ...listed },
    ];
    await mockApi(page, { agents: [master, declaring(brief, sync)], jobs });
    await page.goto("/#/manage/jobs");
    await page.getByTestId("job").getByRole("button", { name: vi.jobRow.editOf("Đồng bộ đơn") }).click();
    await expect(page).toHaveURL(/#\/manage\/crew\/coach\/schedules\?job=coach%2Fsync$/);

    for (const arrival of ["by the link", "by a reload"]) {
      if (arrival === "by a reload") await page.reload();
      const row = rows(page).nth(1);
      await expect(row, arrival).toBeFocused();
      await expect(box(row, t.scheduleScript)).toHaveValue("print(1)\n");
      await expect(rows(page).nth(0)).not.toBeFocused();
      const tops = await row.evaluate((el) => ({ row: el.getBoundingClientRect().top, bar: document.querySelector(".editor-bar")!.getBoundingClientRect().bottom }));
      expect(tops.row, arrival).toBeGreaterThanOrEqual(tops.bar);
      expect(tops.row, arrival).toBeLessThan(viewport.height);
    }
    await expect(page.getByTestId("agent-editor").getByRole("button", { name: vi.jobRow.back })).toBeVisible();
  });
}

test("a script the server refuses is said in its own words, and nothing typed is lost", async ({ page }) => {
  const refusal = "agent coach: schedule sync: script: Dòng 2: `import` không dùng được trong script.";
  await mockApi(page, { agents: [master, declaring(brief, sync)] });
  // Whether Python reads a script is the server's to say. Registered after the mock, so it
  // answers the save first; every other call falls through to the mock.
  await page.route(/\/api\/agents\/coach$/, (route) =>
    route.request().method() === "PATCH" ? route.fulfill({ status: 422, json: { detail: refusal } }) : route.fallback(),
  );
  await page.goto("/#/manage/crew/coach/schedules");
  const script = box(rows(page).nth(1), t.scheduleScript);
  await script.fill("print(1)\nimport os\n");
  await save(page).click();

  await expect(page.getByTestId("agent-editor").getByText(t.saveFailed(refusal))).toBeVisible();
  await expect(script).toHaveValue("print(1)\nimport os\n");
  await expect(save(page)).toBeEnabled();
  await expect(page.getByTestId("restart-banner")).toHaveCount(0);
});

test("a script left empty, or grown past the parser's bound, holds the save and says why", async ({ page }) => {
  await mockApi(page, { agents: [master, declaring(brief, sync)] });
  let saves = 0;
  page.on("request", (r) => {
    if (r.method() === "PATCH") saves += 1;
  });
  await page.goto("/#/manage/crew/coach/schedules");
  const row = rows(page).nth(1);
  const script = box(row, t.scheduleScript);

  await script.fill("#".repeat(20_001));
  await expect(row.getByText(t.scriptTooLong(20_000))).toBeVisible();
  await expect(script).toHaveAttribute("aria-invalid", "true");
  await expect(save(page)).toBeDisabled();

  // Empty is not said to be wrong until a save is tried.
  await script.fill("");
  await expect(row.getByText(t.scriptMissing)).toHaveCount(0);
  await save(page).click();
  await expect(row.getByText(t.scriptMissing)).toBeVisible();
  await expect(script).toHaveAccessibleDescription(`${t.scheduleScriptHint} ${t.scriptMissing}`);
  expect(saves).toBe(0);
});
