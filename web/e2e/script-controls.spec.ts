import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeScriptStore } from "../src/test/fake-script-store";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";
import { spills } from "./spills";

const t = vi.editor;
const master = { ...defaultAgent, name: "Trợ lý", delegates: ["coach"] };
// The coach runs by itself: what `gated` means for it is that nobody is asked.
const coach = { ...coachAgent, declared: { delegates: [], schedules: [], tools: [] } };

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);

/** Choose `gated`, switch the model off for scripts, save, and load the page again. */
async function setsBoth(page: Page) {
  await mockApi(page, { agents: [master, coach] });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const tools = editor.getByTestId("section-tools");
  const calls = tools.getByRole("combobox", { name: t.scriptCalls });
  const llm = tools.getByRole("checkbox", { name: t.scriptLlm });
  const save = editor.getByRole("button", { name: t.save, exact: true });

  // As the crew runs an agent whose file says neither.
  await expect(calls).toHaveValue("read_only");
  await expect(calls).toHaveAccessibleDescription(t.scriptCallsHint.read_only);
  await expect(llm).toBeChecked();
  await expect(llm).toHaveAccessibleDescription(t.scriptLlmHint);
  await expect(save).toBeDisabled();

  await calls.selectOption("gated");
  // Said of this agent, where the choice is made: it runs by itself, so nobody is asked.
  await expect(calls).toHaveAccessibleDescription(t.scriptCallsGatedAutonomous);
  await expect(tools.getByText(t.scriptCallsGatedAutonomous)).toBeVisible();
  await llm.uncheck();

  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await save.click();
  expect((await patch).postDataJSON()).toEqual({ profile: { script_calls: "gated", script_llm: false } });
  await expect(editor.getByText(t.clean)).toBeVisible();
  // Both are read as a turn or a job starts, and neither moves a schedule: the note that
  // a saved schedule is live says nothing here.
  await expect(editor.getByTestId("schedule-live")).toHaveCount(0);

  await page.reload();
  await expect(calls).toHaveValue("gated");
  await expect(llm).not.toBeChecked();
  await expect(save).toBeDisabled();
  return { tools, calls, llm };
}

/** Follow the link under the script settings to what this agent's scripts keep, and come back. */
async function followsToStore(page: Page, press: "click" | "tap") {
  // Each agent keeps a key of its own, to tell whose store is on screen.
  const scriptStore = new FakeScriptStore().keep("default", "job:lead", "seen", 1).keep("coach", "job:brief", "seen", 2);
  await mockApi(page, { agents: [master, coach], scriptStore });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const link = editor.getByTestId("section-tools").getByRole("link", { name: t.scriptStoreLink });
  await link.scrollIntoViewIfNeeded();
  const box = (await link.boundingBox())!;
  expect(await pageWidth(page)).toBeLessThanOrEqual(page.viewportSize()!.width);
  expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);

  await link[press]();
  await expect(page).toHaveURL(/#\/manage\/memory\/scripts\/coach$/);
  const store = page.getByTestId("script-store");
  await expect(store.getByRole("combobox", { name: vi.agents })).toHaveValue("coach");
  await expect(store.locator('[data-namespace="job:brief"]')).toBeVisible();
  await expect(store.locator('[data-namespace="job:lead"]')).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/#\/manage\/crew\/coach$/);
  await expect(editor.getByLabel(t.name, { exact: true })).toHaveValue(coach.name);
  await expect(link).toBeVisible();
  return box;
}

test.describe("on a wide screen", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the link under the script settings opens what this agent's scripts keep, and Back returns to the editor", async ({ page }) => {
    await followsToStore(page, "click");
  });
});

test("what an agent's scripts may call and whether they ask a model are set, saved and still there after a reload", async ({ page }) => {
  const { calls } = await setsBoth(page);

  // Back to no script tool at all, which says what still runs.
  await calls.selectOption("none");
  await expect(calls).toHaveAccessibleDescription(t.scriptCallsHint.none);
});

test.describe("on a phone", () => {
  // A touch screen at the width people hold: the pointer is coarse, as on an iPhone.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the two script settings are set by touch and stay inside the page", async ({ page }) => {
    const { tools, calls, llm } = await setsBoth(page);

    // Safari zooms the page into any field under 16px when it takes focus.
    expect(await calls.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    expect((await calls.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    // The whole line of the checkbox is the target, not the box alone.
    const line = (await llm.locator("xpath=..").boundingBox())!;
    expect(line.height).toBeGreaterThanOrEqual(40);
    // The longest of the lines under the select is on the page, wrapped inside it.
    await expect(tools.getByText(t.scriptCallsGatedAutonomous)).toBeVisible();
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
  });

  // The tick is at the top of the form and the script settings far below it: what the two
  // mean together is said right under the tick that was tapped, inside the page's width.
  test("ticking autonomy on an agent whose scripts may change things says under the tick that nobody is asked", async ({ page }) => {
    await mockApi(page, { agents: [master, { ...coach, autonomous: false, script_calls: "gated" }] });
    await page.goto("/#/manage/crew/coach");
    const editor = page.getByTestId("agent-editor");
    const identity = editor.getByTestId("section-identity");
    const tick = identity.getByRole("checkbox", { name: t.autonomous });
    const line = identity.getByText(t.scriptCallsGatedAutonomous);
    await expect(tick).not.toBeChecked();
    await expect(line).toHaveCount(0);

    await tick.tap();
    await expect(tick).toBeChecked();
    await expect(tick).toHaveAccessibleDescription(t.scriptCallsGatedAutonomous);
    await expect(line).toBeVisible();
    await line.scrollIntoViewIfNeeded();
    // Under the tick's own line, wrapped inside the page.
    const [box, said] = [(await tick.locator("xpath=..").boundingBox())!, (await line.boundingBox())!];
    expect(said.y).toBeGreaterThanOrEqual(box.y + box.height - 1);
    expect(said.x).toBeGreaterThanOrEqual(0);
    expect(said.x + said.width).toBeLessThanOrEqual(390);
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-identity"]')).toEqual([]);
    // The same words stand under the select, in the tools section.
    await expect(editor.getByTestId("section-tools").getByRole("combobox", { name: t.scriptCalls })).toHaveAccessibleDescription(t.scriptCallsGatedAutonomous);

    await tick.tap();
    await expect(line).toHaveCount(0);
    await expect(tick).not.toHaveAccessibleDescription(t.scriptCallsGatedAutonomous);
  });

  test("the link under the script settings is tall enough to tap, opens this agent's store, and Back returns", async ({ page }) => {
    const box = await followsToStore(page, "tap");
    expect(box.height).toBeGreaterThanOrEqual(40);
  });
});
