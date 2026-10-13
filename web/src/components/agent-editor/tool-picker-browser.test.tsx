// The browser's tools are handed by the agent's `browser` key and by no list, so the list of
// an agent never has a row for one, whichever way its rows are found.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgentInfo, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";
import { BROWSER_ACT_TOOL, BROWSER_READ_TOOLS, FakeBrowser, browserMachine } from "../../test/fake-browser";
import { CHATS, CREW, HANDED, agent, open, picker, radio, rows, saved, section, ticked } from "../../test/tool-picker-screen";

const t = vi.editor;
const SIX = [...BROWSER_READ_TOOLS, BROWSER_ACT_TOOL];
/** The six rows as the server lists them for a crew whose coach acts on pages. */
const BROWSER_ROWS: RegistryTool[] = Object.assign(new FakeBrowser(), {
  crew: () => [{ id: "coach", browser: "act" as const }],
  machine: browserMachine({ enabled: true }),
}).registryTools();
const CATALOGUE = [...CREW, ...BROWSER_ROWS];
/** What the catalogue itself does not mark as handed outside any list, in its order. */
const UNMARKED = ["ask_user", "delegate", "web_search", "write_file"];

/** The coach with a browser it acts in, holding the six tools that brings. */
const acting = (rest: Partial<AgentInfo> = {}) =>
  agent({ browser: "act", tools: ["write_file", "web_search", ...HANDED, ...SIX], ...rest });

/** The same agent as a server reports it that says nothing of which rows a list has. */
function unreported(): AgentInfo {
  const { listable_tools: _listable, ...rest } = acting();
  return rest;
}

describe("the tool list of an agent that has a browser", () => {
  it("is offered the catalogue the server sends, six browser rows and all", () => {
    expect(BROWSER_ROWS.map((row) => row.name).sort()).toEqual([...SIX].sort());
    expect(BROWSER_ROWS.every((row) => row.with_browser === true && row.agents.includes("coach"))).toBe(true);
  });

  it("has no row for a browser tool where the server says which rows a list has", () => {
    open(acting(), CATALOGUE);

    expect(rows()).toEqual(CHATS);
    expect(rows().filter((name) => name?.startsWith("browser_"))).toEqual([]);
  });

  it("has none either where the server says nothing of the rows, and the catalogue's marks decide", () => {
    open(unreported(), CATALOGUE);

    expect(rows()).toEqual(UNMARKED);
    for (const name of SIX) expect(picker().queryByRole("checkbox", { name: new RegExp(`^${name}`) })).not.toBeInTheDocument();
  });

  it.each([
    ["the server's rows", acting, ["web_search", "write_file"]],
    ["the catalogue's marks", unreported, ["web_search", "write_file"]],
  ])("starts a list, by %s, from what the agent holds among them, and writes no browser tool into it", async (_by, shown, held) => {
    open(shown(), CATALOGUE);

    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(held);
    expect(await saved()).toEqual([{ tools: held }]);
  });

  it("is told, right under the list, that the browser's tools come with the browser setting", () => {
    open(acting(), CATALOGUE);

    const said = section().getByText("Các công cụ browser_* không có ô chọn ở đây: chúng đi kèm mục Trình duyệt của agent.");
    const list = section().getByTestId("tool-picker");
    expect(list.compareDocumentPosition(said) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // And before the setting it points at.
    const setting = section().getByRole("combobox", { name: vi.browser.mode });
    expect(said.compareDocumentPosition(setting) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("is told so whatever the agent's level, off included", () => {
    open(agent(), CREW);

    expect(screen.getByText(vi.browser.outsideList)).toBeInTheDocument();
  });
});
