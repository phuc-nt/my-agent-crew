// The desktop's four tools are handed by the agent's `computer` key and by no list, so the list
// of an agent never has a row for one, whichever way its rows are found, and a line under it
// says why.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgentInfo, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";
import { DESKTOP_TOOLS, FakeDesktop } from "../../test/fake-desktop";
import { CHATS, CREW, HANDED, agent, open, picker, radio, rows, saved, section, ticked } from "../../test/tool-picker-screen";

const t = vi.editor;
/** The four rows as the server lists them for a crew whose coach is on. */
const DESKTOP_ROWS: RegistryTool[] = Object.assign(new FakeDesktop(), {
  crew: () => [{ id: "coach", computer: "on" as const }],
}).registryTools();
const CATALOGUE = [...CREW, ...DESKTOP_ROWS];
/** What the catalogue itself does not mark as handed outside any list, in its order. */
const UNMARKED = ["ask_user", "delegate", "web_search", "write_file"];

/** The coach on, holding the four tools that brings. */
const on = (rest: Partial<AgentInfo> = {}) =>
  agent({ computer: "on", computer_apps: [], tools: ["write_file", "web_search", ...HANDED, ...DESKTOP_TOOLS], ...rest });

/** The same agent as a server reports it that says nothing of which rows a list has. */
function unreported(): AgentInfo {
  const { listable_tools: _listable, ...rest } = on();
  return rest;
}

describe("the tool list of an agent that has the desktop", () => {
  it("is offered the catalogue the server sends, four desktop rows and all", () => {
    expect(DESKTOP_ROWS.map((row) => row.name)).toEqual(DESKTOP_TOOLS);
    expect(DESKTOP_ROWS.every((row) => row.with_desktop === true && row.agents.includes("coach"))).toBe(true);
  });

  it("has no row for a desktop tool where the server says which rows a list has", () => {
    open(on(), CATALOGUE);

    expect(rows()).toEqual(CHATS);
    expect(rows().filter((name) => name?.startsWith("computer_"))).toEqual([]);
  });

  it("has none either where the server says nothing of the rows, and the catalogue's marks decide", () => {
    open(unreported(), CATALOGUE);

    expect(rows()).toEqual(UNMARKED);
    for (const name of DESKTOP_TOOLS) expect(picker().queryByRole("checkbox", { name: new RegExp(`^${name}`) })).not.toBeInTheDocument();
  });

  it.each([
    ["the server's rows", on],
    ["the catalogue's marks", unreported],
  ])("starts a list, by %s, from what the agent holds among them, and writes no desktop tool into it", async (_by, shown) => {
    open(shown(), CATALOGUE);

    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["web_search", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["web_search", "write_file"] }]);
  });

  it("is told, right under the list and before the setting, that the four come with the desktop", () => {
    open(on(), CATALOGUE);

    const said = section().getByText(vi.desktop.outsideList);
    expect(vi.desktop.outsideList).toContain("computer_*");
    const list = section().getByTestId("tool-picker");
    expect(list.compareDocumentPosition(said) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const setting = section().getByRole("combobox", { name: vi.desktop.editor.mode });
    expect(said.compareDocumentPosition(setting) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("is told so with the desktop off too, and not at all for a server that knows no desktop", () => {
    open(agent({ computer: "off", computer_apps: [] }), CREW);
    expect(screen.getByText(vi.desktop.outsideList)).toBeInTheDocument();
  });

  it("says nothing of the desktop for an agent of a server older than it", () => {
    open(agent(), CREW);
    expect(screen.queryByText(vi.desktop.outsideList)).not.toBeInTheDocument();
  });
});
