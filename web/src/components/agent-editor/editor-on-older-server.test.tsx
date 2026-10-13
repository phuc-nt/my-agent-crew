// The page is served by the crew that is running, and from an update until the restart that
// is still the release before. It reports an agent without the keys this page reads for its
// scripts, for the rows of its tool list and for its browser, and has no route for a browser.
// The editor opens on what that server does send, and offers the tools the page of that
// release offered.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import type { FakeBackend } from "../../test/fake-backend";
import { agent, box, open, radio, rows, saved, section, tick, ticked } from "../../test/tool-picker-screen";

const t = vi.editor;
/** What the catalogue itself does not mark as handed outside any list, in its order. */
const UNMARKED = ["ask_user", "delegate", "web_search", "write_file"];
const KEYS = ["script_calls", "script_llm", "listable_tools", "browser", "browser_hosts"];

/** The agent as the release before reports it: with none of the keys added since. */
function released(shown: AgentInfo = agent()): AgentInfo {
  const { script_calls: _calls, script_llm: _llm, listable_tools: _listable, browser: _browser, browser_hosts: _hosts, ...rest } = shown;
  return rest;
}

/** That release's server has no browser route either. */
const withoutBrowser = (server: FakeBackend) => {
  server.browser.old = true;
};

const marked = () => rows().filter((name) => box(name as string).closest("li")?.textContent?.includes(t.toolNotGiven));

describe("the editor of an agent on a server that reports none of the keys this release added", () => {
  it("opens whole, on every tool, with the script settings the crew runs the agent as", () => {
    const shown = released();
    for (const key of KEYS) expect(shown).not.toHaveProperty(key);
    open(shown);

    expect(screen.getByTestId("agent-editor")).toBeInTheDocument();
    expect(screen.getByLabelText(t.name)).toHaveValue(shown.name);
    expect(radio(t.toolsAll)).toBeChecked();
    // A row for each tool the catalogue does not mark, and for no tool it does.
    expect(rows()).toEqual(UNMARKED);
    expect(section().getByRole("combobox", { name: t.scriptCalls })).toHaveValue("read_only");
    expect(section().getByRole("checkbox", { name: t.scriptLlm })).toBeChecked();
    expect(within(screen.getByTestId("section-schedules")).getByRole("heading", { name: t.sectionSchedules })).toBeInTheDocument();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("has nothing of a browser: no setting, no word under the tool list, and no card of what runs", async () => {
    const server = open(released(), undefined, withoutBrowser);

    // The route is asked once and answers that it is not there.
    await waitFor(() => expect(server.requests.map((r) => r.path)).toContain("/agents/coach/browser"));
    await waitFor(() => expect(screen.getByTestId("agent-editor")).toBeInTheDocument());
    expect(section().queryByRole("combobox", { name: vi.browser.mode })).not.toBeInTheDocument();
    expect(section().queryByRole("textbox", { name: vi.browser.hosts })).not.toBeInTheDocument();
    expect(section().queryByRole("heading", { name: vi.browser.title })).not.toBeInTheDocument();
    expect(section().queryByText(vi.browser.outsideList)).not.toBeInTheDocument();
    expect(screen.queryByTestId("browser-card")).not.toBeInTheDocument();
    expect(screen.queryByText(vi.browser.title)).not.toBeInTheDocument();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("sends no browser key with a save of something else", async () => {
    open(released(), undefined, withoutBrowser);

    await userEvent.selectOptions(section().getByRole("combobox", { name: t.scriptCalls }), "gated");

    expect(await saved()).toEqual([{ script_calls: "gated" }]);
  });

  it("switches the list on from what the agent holds among those rows, and saves that list alone", async () => {
    open(released());

    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["web_search", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["web_search", "write_file"] }]);
    // The answer says no more than the list did: the form goes on from the rows it had.
    expect(radio(t.toolsPick)).toBeChecked();
    expect(rows()).toEqual(UNMARKED);
    expect(ticked()).toEqual(["web_search", "write_file"]);
  });

  it("writes a row ticked after that with the others", async () => {
    open(released());
    await userEvent.click(radio(t.toolsPick));

    await tick("ask_user");

    // The file lists none: the names are written as the rows stand.
    expect(await saved()).toEqual([{ tools: ["ask_user", "web_search", "write_file"] }]);
  });

  it("starts from every row for an agent that holds none of them", async () => {
    open(released(agent({ tools: ["tool_script"] })));

    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(UNMARKED);
    expect(await saved()).toEqual([{ tools: UNMARKED }]);
  });

  it("opens on the list the file writes, and going back to it after “every tool” leaves nothing to save", async () => {
    open(released(agent({ listed: ["write_file", "image_read", "tool_script"] })));

    expect(radio(t.toolsPick)).toBeChecked();
    // A name the catalogue has no unmarked row for keeps a row of its own, said to bring nothing.
    expect(rows()).toEqual([...UNMARKED, "image_read", "tool_script"]);
    expect(ticked()).toEqual(["write_file", "image_read", "tool_script"]);
    expect(marked()).toEqual(["image_read", "tool_script"]);

    await userEvent.click(radio(t.toolsAll));
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["write_file", "image_read", "tool_script"]);
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  // The catalogue is read after the crew: until it lands there is no row to start a list from.
  it("offers no row while the catalogue is not read yet, and “pick” switches no list on", async () => {
    open(released(), []);

    expect(section().getByTestId("tool-picker").querySelectorAll("input")).toHaveLength(0);
    await userEvent.click(radio(t.toolsPick));

    // An empty list is no list: the form says so, and has nothing to save.
    expect(radio(t.toolsAll)).toBeChecked();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });
});
