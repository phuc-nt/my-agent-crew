import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentInfo, RegistryTool } from "../api/types";
import { vi } from "../i18n/vi";
import { fakeAgent } from "../test/fake-backend";
import { BROWSER_ACT_TOOLS, BROWSER_READ_TOOLS, FakeBrowser, browserMachine } from "../test/fake-browser";
import { ToolsMatrix } from "./tools-matrix";

// The browser's eight tools are handed by the agent's own `browser` key and by no list. A cell
// that misses one says which level the agent is at, never that the tool was left off a list.
const actor: AgentInfo = { ...fakeAgent, id: "actor", name: "Thao tác", is_master: false, browser: "act" };
const reader: AgentInfo = { ...fakeAgent, id: "reader", name: "Đọc", is_master: false, browser: "read" };
const none: AgentInfo = { ...fakeAgent, id: "none", name: "Không", is_master: false, browser: "off" };
const own: RegistryTool = { name: "write_file", description: "Write", requires_approval: true, optional: false, agents: ["default"] };
const EIGHT = [...BROWSER_READ_TOOLS, ...BROWSER_ACT_TOOLS];

/** The rows the server adds for this crew, on a machine that has a browser to start. */
function browserRows(agents: AgentInfo[]): RegistryTool[] {
  return Object.assign(new FakeBrowser(), { crew: () => agents, machine: browserMachine({ enabled: true }) }).registryTools();
}

/** The grid of a crew, the master first as the page puts it. */
function show(agents: AgentInfo[], tools: RegistryTool[] = [own, ...browserRows(agents)]) {
  return render(<ToolsMatrix tools={tools} agents={agents} />);
}

const row = (name: string) => within(screen.getAllByTestId("tool-row").find((r) => within(r).queryByText(name)) as HTMLElement);
/** Column 0 is the approval cell; the agents follow, master first. */
const cell = (name: string, column: number) => row(name).getAllByRole("cell")[column];
const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;
const lines = (mark: string) => within(legend()).getAllByRole("definition").filter((line) => line.querySelector(`.${mark}`));

describe("the browser's tools in the grid", () => {
  it("are each marked as coming with the browser, with why on hover, and not as a tool of a list", () => {
    show([fakeAgent, actor]);

    expect(EIGHT).toHaveLength(8);
    for (const name of EIGHT) {
      const badge = row(name).getByText("đi kèm trình duyệt");
      expect(badge).toHaveClass("badge");
      expect(badge).toHaveAttribute("title", vi.browser.withBrowserTitle);
      expect(row(name).queryByText(vi.tools.optional)).not.toBeInTheDocument();
    }
    expect(vi.browser.withBrowserTitle).toContain("Không thuộc danh sách công cụ của agent");
    expect(row("write_file").queryByText(vi.browser.withBrowser)).not.toBeInTheDocument();
  });

  it("say which of them wait for a person", () => {
    show([fakeAgent, actor]);

    for (const name of ["browser_navigate", "browser_act", "browser_download"]) expect(cell(name, 0)).toHaveTextContent(vi.tools.whenNotAutonomous);
    for (const name of ["browser_snapshot", "browser_text", "browser_tabs", "browser_screenshot", "browser_pdf"]) {
      expect(cell(name, 0)).toHaveTextContent(vi.tools.never);
    }
  });

  it("are a plain yes for the agents the server says hold them", () => {
    show([fakeAgent, actor, reader]);

    // Columns: the approval cell, then master, actor, reader.
    for (const name of EIGHT) expect(within(cell(name, 2)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
    for (const name of BROWSER_READ_TOOLS) expect(within(cell(name, 3)).getByText("✓")).toBeInTheDocument();
  });
});

describe("a browser tool an agent does not hold", () => {
  it.each(BROWSER_ACT_TOOLS)("is explained, for an agent that only reads pages, by the level %s needs", (name) => {
    show([fakeAgent, actor, reader]);

    const missed = cell(name, 3);
    expect(within(missed).getByText("◐")).toHaveAttribute("aria-label", "Agent chỉ đọc trang; công cụ này cần mức Thao tác.");
    expect(missed).toHaveClass("cell", "browser-read");
    expect(missed).not.toHaveClass("browser-off");
    expect(missed).toHaveAttribute("title", vi.browser.cellReadOnly);
  });

  it("is not put down to the level for the page saved as a file, which an agent that reads holds", () => {
    show([fakeAgent, actor, reader]);

    expect(within(cell("browser_pdf", 3)).getByText("✓")).toBeInTheDocument();
    expect(cell("browser_pdf", 3)).not.toHaveClass("browser-read");
  });

  it("is explained, for an agent with no browser, by its setting being off", () => {
    show([fakeAgent, actor, none]);

    for (const name of EIGHT) {
      // The master has none either, and is told the same.
      for (const column of [1, 3]) {
        const missed = cell(name, column);
        expect(within(missed).getByText("◌")).toHaveAttribute("aria-label", "Agent đặt Trình duyệt ở Tắt.");
        expect(missed).toHaveClass("cell", "browser-off");
        expect(missed).toHaveAttribute("title", vi.browser.cellOff);
      }
    }
  });

  it("is never put down to the agent's list, its mode or a key", () => {
    // A list of its own that names none of the eight: any other tool would read as left out.
    const listed: AgentInfo = { ...none, declared: { ...none.declared, tools: ["write_file"] } };
    const reading: AgentInfo = { ...reader, declared: { ...reader.declared, tools: ["write_file"] } };
    show([fakeAgent, actor, listed, reading]);

    for (const name of EIGHT) {
      expect(cell(name, 3)).toHaveClass("browser-off");
      for (const wrong of ["excluded", "missing-key", "work-mode"]) expect(cell(name, 3)).not.toHaveClass(wrong);
    }
    for (const name of BROWSER_ACT_TOOLS) {
      expect(cell(name, 4)).toHaveClass("browser-read");
      for (const wrong of ["excluded", "missing-key", "work-mode"]) expect(cell(name, 4)).not.toHaveClass(wrong);
    }
    // The same agents on a tool a list does decide.
    expect(cell("write_file", 3)).toHaveClass("work-mode");
  });

  it("reads an agent of a server that reports no such key as one with no browser", () => {
    const { browser: _mode, browser_hosts: _hosts, ...older } = none;
    show([fakeAgent, actor, older]);

    expect(cell("browser_act", 3)).toHaveClass("browser-off");
    expect(cell("browser_text", 3)).toHaveClass("browser-off");
  });
});

describe("the legend's lines for the browser's marks", () => {
  it("are not there for a crew with no browser tool on the page", () => {
    // Nobody asks for a browser, so the server adds no row, whatever the files say.
    show([fakeAgent, none]);
    expect(screen.getAllByTestId("tool-row")).toHaveLength(1);

    expect(lines("browser-off")).toHaveLength(0);
    expect(lines("browser-read")).toHaveLength(0);
    expect(legend()).not.toHaveTextContent(vi.browser.cellOff);
  });

  it("have the off mark alone for a crew where nobody only reads", () => {
    show([fakeAgent, actor]);

    expect(lines("browser-off")).toHaveLength(1);
    expect(lines("browser-off")[0]).toHaveTextContent(/^◌Agent đặt Trình duyệt ở Tắt\.$/);
    expect(lines("browser-read")).toHaveLength(0);
  });

  it("have both where one agent acts and another only reads, after the marks that were there before", () => {
    show([fakeAgent, actor, reader]);

    expect(lines("browser-read")).toHaveLength(1);
    expect(lines("browser-read")[0]).toHaveTextContent(/^◐Agent chỉ đọc trang; công cụ này cần mức Thao tác\.$/);
    const marks = within(legend()).getAllByRole("definition");
    expect(marks[marks.length - 2]).toBe(lines("browser-off")[0]);
    expect(marks[marks.length - 1]).toBe(lines("browser-read")[0]);
  });

  it("have no line for the reading mark while the page has no acting tool to miss", () => {
    // Nobody acts, so the server has no row for an acting tool and no cell can carry the mark.
    show([fakeAgent, reader]);
    expect(screen.getAllByTestId("tool-row")).toHaveLength(7);

    expect(lines("browser-off")).toHaveLength(1);
    expect(lines("browser-read")).toHaveLength(0);
  });
});
