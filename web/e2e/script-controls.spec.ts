import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
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
  // Both are read as a turn or a job starts: nothing waits for a restart.
  await expect(editor.getByTestId("restart-banner")).toHaveCount(0);

  await page.reload();
  await expect(calls).toHaveValue("gated");
  await expect(llm).not.toBeChecked();
  await expect(save).toBeDisabled();
  return { tools, calls, llm };
}

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
    const { calls, llm } = await setsBoth(page);

    // Safari zooms the page into any field under 16px when it takes focus.
    expect(await calls.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    expect((await calls.boundingBox())!.height).toBeGreaterThanOrEqual(40);
    // The whole line of the checkbox is the target, not the box alone.
    const line = (await llm.locator("xpath=..").boundingBox())!;
    expect(line.height).toBeGreaterThanOrEqual(40);
    // The longest of the lines under the select is on the page, wrapped inside it.
    await expect(page.getByText(t.scriptCallsGatedAutonomous)).toBeVisible();
    expect(await pageWidth(page)).toBeLessThanOrEqual(390);
    expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
  });
});
