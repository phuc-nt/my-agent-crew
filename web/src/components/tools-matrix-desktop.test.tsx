import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentInfo, RegistryTool } from "../api/types";
import { vi } from "../i18n/vi";
import { fakeAgent } from "../test/fake-backend";
import { DESKTOP_TOOLS, FakeDesktop } from "../test/fake-desktop";
import { ToolsMatrix } from "./tools-matrix";

// The desktop's four tools are handed by the agent's own `computer` key and by no list. A cell
// that misses one says the agent's desktop is off, never that the tool was left off a list.
const on: AgentInfo = { ...fakeAgent, id: "on", name: "Bật", is_master: false, computer: "on", computer_apps: [] };
const off: AgentInfo = { ...fakeAgent, id: "off", name: "Tắt", is_master: false, computer: "off", computer_apps: [] };
const own: RegistryTool = { name: "write_file", description: "Write", requires_approval: true, optional: false, agents: ["default"] };

/** The rows the server adds for this crew, with or without a helper on the machine. */
function desktopRows(agents: AgentInfo[]): RegistryTool[] {
  return Object.assign(new FakeDesktop(), { crew: () => agents }).registryTools();
}

function show(agents: AgentInfo[]) {
  return render(<ToolsMatrix tools={[own, ...desktopRows(agents)]} agents={agents} />);
}

const row = (name: string) => within(screen.getAllByTestId("tool-row").find((r) => within(r).queryByText(name)) as HTMLElement);
/** Column 0 is the approval cell; the agents follow, master first. */
const cell = (name: string, column: number) => row(name).getAllByRole("cell")[column];
const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;
const lines = (mark: string) => within(legend()).getAllByRole("definition").filter((line) => line.querySelector(`.${mark}`));

describe("the desktop's tools in the grid", () => {
  it("are each marked as coming with the desktop, with why on hover, and not as a tool of a list", () => {
    show([fakeAgent, on]);

    expect(DESKTOP_TOOLS).toHaveLength(4);
    for (const name of DESKTOP_TOOLS) {
      const badge = row(name).getByText("đi kèm desktop");
      expect(badge).toHaveClass("badge");
      expect(badge).toHaveAttribute("title", vi.desktop.withDesktopTitle);
      expect(row(name).queryByText(vi.tools.optional)).not.toBeInTheDocument();
    }
    expect(row("write_file").queryByText(vi.desktop.withDesktop)).not.toBeInTheDocument();
  });

  it("say that only the one that acts waits for a person", () => {
    show([fakeAgent, on]);

    expect(cell("computer_act", 0)).toHaveTextContent(vi.tools.whenNotAutonomous);
    for (const name of ["computer_observe", "computer_screenshot", "computer_state"]) expect(cell(name, 0)).toHaveTextContent(vi.tools.never);
  });

  it("are a plain yes for the agents the server says hold them", () => {
    show([fakeAgent, on]);

    for (const name of DESKTOP_TOOLS) expect(within(cell(name, 2)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
  });

  it("are explained, for an agent that is off, by its setting, never by its list, mode or a key", () => {
    const listed: AgentInfo = { ...off, declared: { ...off.declared, tools: ["write_file"] } };
    show([fakeAgent, on, listed]);

    for (const name of DESKTOP_TOOLS) {
      // The master has none either, and is told the same.
      for (const column of [1, 3]) {
        const missed = cell(name, column);
        expect(within(missed).getByText("▭")).toHaveAttribute("aria-label", "Agent đặt Desktop ở Tắt.");
        expect(missed).toHaveClass("cell", "desktop-off");
        expect(missed).toHaveAttribute("title", vi.desktop.cellOff);
        for (const wrong of ["excluded", "missing-key", "work-mode", "browser-off"]) expect(missed).not.toHaveClass(wrong);
      }
    }
    expect(cell("write_file", 3)).toHaveClass("work-mode");
  });

  it("have a legend line for the off mark where somebody is on", () => {
    show([fakeAgent, on]);
    expect(lines("desktop-off")).toHaveLength(1);
    expect(lines("desktop-off")[0]).toHaveTextContent(/^▭Agent đặt Desktop ở Tắt\.$/);
  });

  it("have no row and no legend line where nobody is on", () => {
    show([fakeAgent, off]);

    expect(screen.getAllByTestId("tool-row")).toHaveLength(1);
    expect(lines("desktop-off")).toHaveLength(0);
  });
});
