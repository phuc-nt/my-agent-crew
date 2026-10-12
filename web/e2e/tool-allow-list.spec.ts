import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { coachAgent, defaultAgent, devAgent, mockApi } from "./mock-api";
import { spills } from "./spills";

const t = vi.editor;
const tool = (name: string, agents: string[]) => ({ name, description: `Công cụ ${name}`, requires_approval: false, optional: false, agents });
/** The crew's own tools as the catalogue lists them: by name, with the agents that hold each. */
const CREW = [
  tool("ask_user", ["dev"]),
  tool("delegate", ["default", "dev"]),
  tool("shell_run", ["dev"]),
  tool("web_search", ["default", "coach"]),
  tool("write_file", ["default", "coach", "dev"]),
];
/** What the server says a list has a say over, for an agent that only chats and for one that
 * hands work out. Nobody holds `memory_save`, so the catalogue has no row for it. */
const CHATS = ["memory_save", "web_search", "write_file"];
const LEADS = ["delegate", ...CHATS];
const master = { ...defaultAgent, name: "Trợ lý", tools: ["delegate", "web_search", "write_file"], listable_tools: LEADS };
// Not the master, in the mode that only chats, naming no delegate: it hands no work out.
const coach = { ...coachAgent, tools: ["web_search", "write_file"], listable_tools: CHATS, declared: { delegates: [], schedules: [], tools: [] as string[] } };
const listing = (...tools: string[]) => ({ ...coach, declared: { ...coach.declared, tools } });
// What a file written by hand names beside the person's own choice: `delegate` on an agent
// that hands no work out, a tool handed whatever the list says, a tool of a server long
// gone, and a tool this machine cannot run today.
const NOTHING_FROM = ["delegate", "tool_script", "mcp__gone__fetch", "image_read"];

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
    /** The rows said to bring the agent nothing, and the line about saving first. */
    marked: picker.locator("li", { hasText: t.toolNotGiven }).locator("code"),
    saveFirst: section.getByText(t.toolsFollowSaved),
    box: (name: string) => picker.getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) }).getByRole("checkbox"),
  };
}

/** Switch the list on for an agent that hands no work out, save, and load the page again. */
async function switchesOn(page: Page) {
  const form = await opens(page, "coach", [master, coach, devAgent]);
  await expect(form.all).toBeChecked();
  // The names the server lists for this agent, whatever the rest of the crew holds.
  await expect(form.rows).toHaveText(CHATS);

  await form.pick.check();
  // What it holds today among them, and no name more.
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
  const form = await opens(page, "coach", [master, listing("web_search", ...NOTHING_FROM), devAgent]);
  await expect(form.pick).toBeChecked();
  // Each such name has a row after the others, ticked, and said to bring nothing.
  await expect(form.rows).toHaveText([...CHATS, ...NOTHING_FROM]);
  await expect(form.ticked).toHaveText(["web_search", ...NOTHING_FROM]);
  await expect(form.marked).toHaveText(NOTHING_FROM);
  await expect(form.save).toBeDisabled();

  // Another field saved: the list is not sent, so the file keeps it as it was written.
  await form.editor.getByLabel(t.name, { exact: true }).fill("HLV");
  expect(await form.saved()).toEqual({ profile: { name: "HLV" } });
  await expect(form.ticked).toHaveText(["web_search", ...NOTHING_FROM]);

  // The list changed: it is written as it is ticked, those names with it.
  await form.box("write_file").check();
  expect(await form.saved()).toEqual({ profile: { tools: ["web_search", ...NOTHING_FROM, "write_file"] } });

  // Only the person takes a name off. Its row goes with it, and the keyboard that was on
  // it is on the row that took its place.
  await form.box("tool_script").click();
  await expect(form.rows).toHaveText([...CHATS, "delegate", "mcp__gone__fetch", "image_read"]);
  await expect(form.box("mcp__gone__fetch")).toBeFocused();
  expect(await form.saved()).toEqual({ profile: { tools: ["web_search", "delegate", "mcp__gone__fetch", "image_read", "write_file"] } });

  await page.reload();
  await expect(form.ticked).toHaveText(["web_search", "write_file", "delegate", "mcp__gone__fetch", "image_read"]);
  await expect(form.save).toBeDisabled();
  return form;
}

/** Tick `delegate` back on the master, whose list left it out so that no agent holds it. */
async function ticksBack(page: Page) {
  const lead = { ...master, tools: ["write_file"], declared: { ...master.declared, tools: ["write_file"] } };
  const nobody = CREW.filter((row) => row.name !== "delegate");
  const form = await opens(page, "default", [lead, coach, devAgent], nobody);
  await expect(form.rows).toHaveText(LEADS);
  await expect(form.ticked).toHaveText(["write_file"]);
  // The catalogue has no row for it, so the page says what the tool is by itself.
  await expect(form.picker.getByText(t.toolDelegate)).toBeVisible();

  await form.box("delegate").check();
  expect(await form.saved()).toEqual({ profile: { tools: ["write_file", "delegate"] } });
  await page.reload();
  await expect(form.ticked).toHaveText(["delegate", "write_file"]);
  return form;
}

/** Make an agent one that hands work out, and only then give its list the tool it does so with. */
async function savesFirst(page: Page) {
  const form = await opens(page, "coach", [master, listing("write_file"), devAgent]);
  await expect(form.rows).toHaveText(CHATS);
  await expect(form.saveFirst).toBeHidden();

  // Not saved yet: the rows are still those of the agent as saved, and a line says so.
  await form.editor.getByTestId("delegate-picker").getByRole("checkbox", { name: /Dev/ }).check();
  await expect(form.saveFirst).toBeVisible();
  expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
  await expect(form.rows).toHaveText(CHATS);

  // The answer to the save names the tools of the agent it made: the row is there at once.
  expect(await form.saved()).toEqual({ profile: { delegates: ["dev"] } });
  await expect(form.saveFirst).toBeHidden();
  await expect(form.rows).toHaveText(LEADS);
  await form.box("delegate").check();
  expect(await form.saved()).toEqual({ profile: { tools: ["write_file", "delegate"] } });

  await page.reload();
  await expect(form.ticked).toHaveText(["delegate", "write_file"]);
  return form;
}

const FLOWS = [
  ["starts from what the agent holds, and is still there after a reload", switchesOn],
  ["of a file written by hand keeps every name until the person unticks it", opensOld],
  ["of the master offers `delegate` while no agent holds it, and writes it once ticked", ticksBack],
  ["follows the agent as saved: a delegate is saved first, then `delegate` is chosen", savesFirst],
] as const;

for (const [what, flow] of FLOWS) {
  test(`the chosen list ${what}`, async ({ page }) => {
    await flow(page);
  });
}

test.describe("on a phone", () => {
  // A touch screen at the width people hold: the pointer is coarse, as on an iPhone.
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  for (const [what, flow] of FLOWS) {
    test(`the chosen list ${what}, inside the page`, async ({ page }) => {
      await flow(page);
      expect(await pageWidth(page)).toBeLessThanOrEqual(390);
      expect(await spills(page, '[data-testid="section-tools"]')).toEqual([]);
    });
  }
});
