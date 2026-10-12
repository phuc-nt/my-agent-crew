import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { coachAgent, defaultAgent, devAgent, mockApi } from "./mock-api";
import { spills } from "./spills";

const t = vi.editor;
const tool = (name: string, agents: string[]) => ({ name, description: `Công cụ ${name}`, requires_approval: false, optional: false, agents });
/** The crew's own tools as the registry lists them: by name, with the agents that hold each. */
const CREW = [
  tool("ask_user", ["dev"]),
  tool("delegate", ["default", "dev"]),
  tool("shell_run", ["dev"]),
  tool("web_search", ["default", "coach"]),
  tool("write_file", ["default", "coach", "dev"]),
];
const master = { ...defaultAgent, name: "Trợ lý", tools: ["delegate", "web_search", "write_file"] };
// Not the master, in the mode that only chats, naming no delegate: it hands no work out.
const coach = { ...coachAgent, tools: ["web_search", "write_file"], declared: { delegates: [], schedules: [], tools: [] as string[] } };
// A file written by hand, or by the picker as it was: beside the person's two choices it
// names `delegate`, a tool handed whatever the list says, and a tool of a server long gone.
const OLD = ["web_search", "delegate", "tool_script", "mcp__gone__fetch", "image_read"];

const pageWidth = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth);

async function opens(page: Page, id: string, agents: object[], tools = CREW) {
  await mockApi(page, { agents, tools });
  await page.goto(`/#/manage/crew/${id}`);
  const editor = page.getByTestId("agent-editor");
  const section = editor.getByTestId("section-tools");
  const picker = section.getByTestId("tool-picker");
  const save = editor.getByRole("button", { name: t.save, exact: true });
  /** Saves, and returns what was sent once the server has answered. */
  const saved = async () => {
    const patch = page.waitForRequest((r) => r.method() === "PATCH" && new RegExp(`/api/agents/${id}$`).test(r.url()));
    await save.click();
    const sent = (await patch).postDataJSON();
    await expect(editor.getByText(t.clean)).toBeVisible();
    return sent;
  };
  return {
    editor,
    picker,
    save,
    saved,
    all: section.getByRole("radio", { name: t.toolsAll }),
    pick: section.getByRole("radio", { name: t.toolsPick }),
    rows: picker.locator("li code"),
    ticked: picker.locator("li:has(input:checked) code"),
    box: (name: string) => picker.getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) }).getByRole("checkbox"),
  };
}

/** Switch the list on for an agent that hands no work out, save, and load the page again. */
async function switchesOn(page: Page) {
  const form = await opens(page, "coach", [master, coach, devAgent]);
  await expect(form.all).toBeChecked();
  // No row for the tool it would get nothing from, whoever else in the crew holds it.
  await expect(form.rows).toHaveText(["ask_user", "shell_run", "web_search", "write_file"]);

  await form.pick.check();
  // What it holds today, and not what only the rest of the crew holds.
  await expect(form.ticked).toHaveText(["web_search", "write_file"]);
  expect(await form.saved()).toEqual({ profile: { tools: ["web_search", "write_file"] } });

  await page.reload();
  await expect(form.pick).toBeChecked();
  await expect(form.ticked).toHaveText(["web_search", "write_file"]);
  await expect(form.save).toBeDisabled();
  return form;
}

/** Open a file whose list names what no list gives, save another field, then change the list. */
async function opensOld(page: Page) {
  const old = { ...coach, tools: ["web_search"], declared: { ...coach.declared, tools: OLD } };
  const form = await opens(page, "coach", [master, old, devAgent]);
  await expect(form.pick).toBeChecked();
  await expect(form.rows).toHaveText(["ask_user", "shell_run", "web_search", "write_file"]);
  await expect(form.ticked).toHaveText(["web_search"]);
  await expect(form.save).toBeDisabled();

  // Another field saved: the list is not sent, so the file keeps it as it was written.
  await form.editor.getByLabel(t.name, { exact: true }).fill("HLV");
  expect(await form.saved()).toEqual({ profile: { name: "HLV" } });
  await expect(form.ticked).toHaveText(["web_search"]);

  // The list changed: the names it has no say over go, every other choice stays.
  await form.box("write_file").check();
  expect(await form.saved()).toEqual({ profile: { tools: ["web_search", "image_read", "write_file"] } });

  await page.reload();
  await expect(form.ticked).toHaveText(["web_search", "write_file"]);
  await expect(form.save).toBeDisabled();
  return form;
}

/** Tick `delegate` back on the master, whose list left it out so that no agent holds it. */
async function ticksBack(page: Page) {
  const lead = { ...master, tools: ["write_file"], declared: { ...master.declared, tools: ["write_file"] } };
  const nobody = CREW.filter((row) => row.name !== "delegate");
  const form = await opens(page, "default", [lead, coach, devAgent], nobody);
  await expect(form.rows).toHaveText(["ask_user", "delegate", "shell_run", "web_search", "write_file"]);
  await expect(form.ticked).toHaveText(["write_file"]);
  // The registry has no row for it, so the page says what the tool is by itself.
  await expect(form.picker.getByText(t.toolDelegate)).toBeVisible();

  await form.box("delegate").check();
  expect(await form.saved()).toEqual({ profile: { tools: ["write_file", "delegate"] } });
  await page.reload();
  await expect(form.ticked).toHaveText(["delegate", "write_file"]);
  return form;
}

test("the chosen list starts from what the agent holds, and is still there after a reload", async ({ page }) => {
  await switchesOn(page);
});

test("an old file's list opens with the person's choices, and loses none of them to a save", async ({ page }) => {
  await opensOld(page);
});

test("the master's list offers `delegate` while no agent holds it, and writes it once ticked", async ({ page }) => {
  await ticksBack(page);
});

test.describe("on a phone", () => {
  // A touch screen at the width people hold: the pointer is coarse, as on an iPhone.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  for (const [what, flow] of [["switched on", switchesOn], ["opened on an old file", opensOld], ["with `delegate` ticked back", ticksBack]] as const) {
    test(`the chosen list ${what} stays inside the page`, async ({ page }) => {
      await flow(page);
      expect(await pageWidth(page)).toBeLessThanOrEqual(390);
      expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
    });
  }
});
