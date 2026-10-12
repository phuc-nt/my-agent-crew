import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentInfo, RegistryTool } from "../api/types";
import { vi } from "../i18n/vi";
import { fakeAgent } from "../test/fake-backend";
import { scriptTool } from "../test/fake-mcp";
import { ToolsMatrix } from "./tools-matrix";

// An agent whose file says `script_calls: none` is handed no script tool however many
// reading tools it holds. The grid used to explain every missing script tool as "holds no
// tool that only reads", which is false of such an agent.
const reader: AgentInfo = { ...fakeAgent, id: "reader", name: "Đọc", is_master: false, tools: ["workspace_read"] };
const off: AgentInfo = { ...reader, id: "off", name: "Tắt", script_calls: "none" };
const bare: AgentInfo = { ...reader, id: "bare", name: "Trống", tools: [] };
const own: RegistryTool = { name: "workspace_read", description: "Read", requires_approval: false, optional: false, agents: ["default", "reader", "off"] };
const script = scriptTool(["default", "reader"]);

const row = () => within(screen.getAllByTestId("tool-row").find((r) => within(r).queryByText("tool_script")) as HTMLElement);
const cell = (column: number) => row().getAllByRole("cell")[column];
const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;
const lines = (mark: string) => within(legend()).getAllByRole("definition").filter((line) => line.querySelector(`.${mark}`));

describe("the script tool of an agent whose file takes it away", () => {
  it("is marked as switched off, not as an agent with nothing for a script to call", () => {
    render(<ToolsMatrix tools={[own, script]} agents={[fakeAgent, reader, off, bare]} />);

    // Columns: the approval cell, then master, reader, off, bare.
    expect(within(cell(2)).getByText("✓")).toBeInTheDocument();
    expect(within(cell(3)).getByText("⊘")).toHaveAttribute("aria-label", vi.tools.legendScriptOff);
    expect(cell(3)).toHaveClass("cell", "script-off");
    expect(cell(3)).not.toHaveClass("no-reads");
    expect(cell(3)).toHaveAttribute("title", "agent được đặt “Không dùng script”");
    // An agent with no reading tool is still told so.
    expect(within(cell(4)).getByText("∅")).toHaveAttribute("aria-label", vi.tools.legendNoReads);
    expect(cell(4)).toHaveClass("cell", "no-reads");
  });

  it("is the reason given even when the agent holds nothing a script could call", () => {
    render(<ToolsMatrix tools={[own, script]} agents={[fakeAgent, { ...off, tools: [] }]} />);

    expect(cell(2)).toHaveClass("script-off");
    expect(row().queryByText("∅")).not.toBeInTheDocument();
  });

  it("is still a plain yes where the server says the agent holds the tool", () => {
    // A crew older than the switch reports the key and hands the tool all the same.
    render(<ToolsMatrix tools={[own, scriptTool(["default", "off"])]} agents={[fakeAgent, off]} />);

    expect(within(cell(2)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
  });

  it("has a line in the legend only for a crew where an agent is set so", () => {
    const without = render(<ToolsMatrix tools={[own, script]} agents={[fakeAgent, reader, bare]} />);
    expect(lines("script-off")).toHaveLength(0);
    expect(lines("no-reads")).toHaveLength(1);
    without.unmount();

    const withOne = render(<ToolsMatrix tools={[own, script]} agents={[fakeAgent, reader, off]} />);
    expect(lines("script-off")).toHaveLength(1);
    expect(lines("script-off")[0]).toHaveTextContent(/^⊘agent được đặt “Không dùng script”$/);
    // After the mark for an agent with nothing to call, as the marks are listed.
    const marks = within(legend()).getAllByRole("definition");
    expect(marks[marks.length - 1]).toBe(lines("script-off")[0]);
    expect(marks[marks.length - 2]).toBe(lines("no-reads")[0]);
    withOne.unmount();

    // No script tool on the page: nothing to explain, whatever the agents' files say.
    render(<ToolsMatrix tools={[own]} agents={[fakeAgent, off]} />);
    expect(lines("script-off")).toHaveLength(0);
  });

  it("reads an agent of a server that reports no such key as one that never switched it off", () => {
    const { script_calls: _calls, script_llm: _llm, ...older } = bare;
    render(<ToolsMatrix tools={[own, script]} agents={[fakeAgent, older]} />);

    expect(cell(2)).toHaveClass("no-reads");
    expect(lines("script-off")).toHaveLength(0);
  });
});
