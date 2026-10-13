// The page is served by the crew that is running, and from an update until its restart that
// is the release before: it reports an agent without the keys this page has gained since.
import { expect, type Page, test } from "@playwright/test";
import { vi } from "../src/i18n/vi";
import { FakeBrowser } from "../src/test/fake-browser";
import { coachAgent, defaultAgent, mockApi } from "./mock-api";

const t = vi.editor;
const tool = (name: string, agents: string[], marks: object = {}) => ({ name, description: `Công cụ ${name}`, requires_approval: false, optional: false, agents, ...marks });
/** The catalogue as that release lists it: it marks what an agent is handed outside any list. */
const CATALOGUE = [
  tool("ask_user", []),
  tool("mcp__notion__search", ["coach"], { server: "notion", exposure: "direct" }),
  tool("tool_script", ["default", "coach"], { with_reads: true }),
  tool("tool_search", ["coach"], { with_mcp: true }),
  tool("web_search", ["default", "coach"]),
  tool("write_file", ["default", "coach"]),
];
const UNMARKED = ["ask_user", "web_search", "write_file"];

/** An agent as that release reports it: with none of the keys added since. */
function released<A extends object>(agent: A) {
  const { script_calls: _calls, script_llm: _llm, listable_tools: _listable, browser: _browser, browser_hosts: _hosts, ...rest } = agent as Record<string, unknown>;
  return rest;
}
const master = released({ ...defaultAgent, name: "Trợ lý", tools: ["tool_script", "web_search", "write_file"] });
const coach = released({ ...coachAgent, tools: ["tool_script", "tool_search", "web_search", "write_file"], declared: { delegates: [], schedules: [], tools: [] } });
/** That release knows no browser: nothing of one among the connections, and no route for one. */
const noBrowser = () => Object.assign(new FakeBrowser(), { old: true });

const crashed = (page: Page) => page.locator(".crash");

test("an agent's editor opens on the release before, and its tool list is chosen and saved", async ({ page }) => {
  await mockApi(page, { agents: [master, coach], tools: CATALOGUE, browser: noBrowser() });
  await page.goto("/#/manage/crew/coach");
  const editor = page.getByTestId("agent-editor");
  const section = editor.getByTestId("section-tools");
  const picker = section.getByTestId("tool-picker");
  const save = editor.getByRole("button", { name: t.save, exact: true });

  await expect(editor.getByTestId("section-identity")).toBeVisible();
  await expect(crashed(page)).toHaveCount(0);
  // What the page of that release offered: the catalogue's tools it does not mark.
  await expect(section.getByRole("radio", { name: t.toolsAll })).toBeChecked();
  await expect(picker.locator("li code")).toHaveText(UNMARKED);
  // As that crew runs every agent.
  await expect(section.getByRole("combobox", { name: t.scriptCalls })).toHaveValue("read_only");
  await expect(section.getByRole("checkbox", { name: t.scriptLlm })).toBeChecked();
  await expect(editor.getByTestId("section-schedules")).toBeVisible();
  await expect(save).toBeDisabled();

  await section.getByRole("radio", { name: t.toolsPick }).check();
  await expect(picker.locator("li:has(input:checked) code")).toHaveText(["web_search", "write_file"]);
  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await save.click();
  expect((await patch).postDataJSON()).toEqual({ profile: { tools: ["web_search", "write_file"] } });
  await expect(editor.getByText(t.clean)).toBeVisible();

  await page.reload();
  await expect(section.getByRole("radio", { name: t.toolsPick })).toBeChecked();
  await expect(picker.locator("li:has(input:checked) code")).toHaveText(["web_search", "write_file"]);
  await expect(crashed(page)).toHaveCount(0);
});

test("the crew and the table of tools open on the release before", async ({ page }) => {
  await mockApi(page, { agents: [master, coach], tools: CATALOGUE, browser: noBrowser() });

  await page.goto("/#/manage/crew");
  await expect(page.getByTestId("crew-agent")).toHaveCount(2);
  await expect(crashed(page)).toHaveCount(0);

  await page.goto("/#/manage/tools");
  await expect(page.getByTestId("tools-matrix").getByTestId("tool-row")).toHaveCount(CATALOGUE.length);
  await expect(crashed(page)).toHaveCount(0);
});

test("nothing of a browser is drawn on the release before: no setting, no card, no mark, and no key in a save", async ({ page }) => {
  for (const agent of [master, coach]) {
    expect(agent).not.toHaveProperty("browser");
    expect(agent).not.toHaveProperty("browser_hosts");
  }
  await mockApi(page, { agents: [master, coach], tools: CATALOGUE, browser: noBrowser() });
  // The page asks what the agent's browser runs, and that server has no such route.
  const refused = page.waitForResponse((r) => r.status() === 404 && /\/api\/agents\/coach\/browser$/.test(r.url()));
  await page.goto("/#/manage/crew/coach");
  await refused;
  const editor = page.getByTestId("agent-editor");
  const section = editor.getByTestId("section-tools");

  await expect(section.getByRole("combobox", { name: t.scriptCalls })).toHaveValue("read_only");
  await expect(section.getByRole("combobox", { name: vi.browser.mode })).toHaveCount(0);
  await expect(section.getByRole("textbox", { name: vi.browser.hosts })).toHaveCount(0);
  await expect(section.getByText(vi.browser.outsideList)).toHaveCount(0);
  await expect(page.getByTestId("browser-card")).toHaveCount(0);
  await expect(page.getByText(vi.browser.title, { exact: true })).toHaveCount(0);
  await expect(crashed(page)).toHaveCount(0);

  // A save of something else is that key alone.
  await section.getByRole("combobox", { name: t.scriptCalls }).selectOption("gated");
  const patch = page.waitForRequest((r) => r.method() === "PATCH" && /\/api\/agents\/coach$/.test(r.url()));
  await editor.getByRole("button", { name: t.save, exact: true }).click();
  expect((await patch).postDataJSON()).toEqual({ profile: { script_calls: "gated" } });
  await expect(editor.getByText(t.clean)).toBeVisible();
  await expect(page.getByTestId("browser-card")).toHaveCount(0);

  await page.goto("/#/manage/connections");
  await expect(page.getByTestId("providers")).toBeVisible();
  await expect(page.getByTestId("browser-machine")).toHaveCount(0);
  await expect(page.getByText(vi.browser.title, { exact: true })).toHaveCount(0);
  await expect(crashed(page)).toHaveCount(0);

  await page.goto("/#/manage/tools");
  const matrix = page.getByTestId("tools-matrix");
  await expect(matrix.getByTestId("tool-row")).toHaveCount(CATALOGUE.length);
  await expect(matrix.getByText(/^browser_/)).toHaveCount(0);
  await expect(page.getByText(vi.browser.withBrowser)).toHaveCount(0);
  await expect(page.getByText(vi.browser.cellOff)).toHaveCount(0);
  await expect(crashed(page)).toHaveCount(0);
});
