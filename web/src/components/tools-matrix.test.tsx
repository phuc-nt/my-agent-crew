import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { ToolsMatrix } from "./tools-matrix";
import type { AgentInfo, RegistryTool } from "../api/types";
import { fakeAgent } from "../test/fake-backend";

describe("ToolsMatrix", () => {
  it("shows the empty state when there are no tools", () => {
    render(<ToolsMatrix tools={[]} agents={[fakeAgent]} />);

    expect(screen.getByText(vi.tools.empty)).toBeInTheDocument();
  });

  it("renders a table with tools as rows and agents as columns", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run shell", requires_approval: false, optional: false, agents: ["default"] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    expect(screen.getByTestId("tools-matrix")).toBeInTheDocument();
    expect(screen.getByText("shell_run")).toBeInTheDocument();
  });

  it("marks tools with the 'on' symbol when an agent holds them", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    const cells = screen.getAllByText("✓");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute("aria-label", vi.tools.legendOn);
  });

  it("marks tools with the 'excluded' symbol when an agent has an allow-list that omits the tool", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "selective",
      tools: ["shell_run"],
    };
    const tools: RegistryTool[] = [
      { name: "workspace_write", description: "Write", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const cells = screen.getAllByText("–");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute("aria-label", vi.tools.legendExcluded);
  });

  it("marks tools with the 'missing-key' symbol when optional and not listed", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "agent1",
      tools: [],
    };
    const tools: RegistryTool[] = [
      { name: "web_search", description: "Search", requires_approval: false, optional: true, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const cells = screen.getAllByText("○");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute("aria-label", vi.tools.legendMissingKey);
  });

  it("marks tools with the 'work-mode' symbol when required but agent does not have them", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "assistant",
      mode: "assistant",
      tools: [],
    };
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const cells = screen.getAllByText("▫");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute("aria-label", vi.tools.legendWorkMode);
  });

  it("correctly applies cellFor precedence: 'on' wins", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      tools: ["shell_run"],
    };
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    expect(screen.getAllByText("✓")[0]).toHaveAttribute("aria-label", vi.tools.legendOn);
  });

  it("correctly applies cellFor precedence: 'excluded' beats 'missing-key'", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "selective",
      tools: ["shell_run"],
    };
    const tools: RegistryTool[] = [
      { name: "web_search", description: "Search", requires_approval: false, optional: true, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const cells = screen.getAllByText("–");
    expect(cells.length).toBeGreaterThan(0);
    expect(cells[0]).toHaveAttribute("aria-label", vi.tools.legendExcluded);
  });

  it("correctly applies cellFor precedence: 'missing-key' beats 'work-mode'", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "agent1",
      tools: [],
    };
    const tools: RegistryTool[] = [
      { name: "web_search", description: "Search", requires_approval: false, optional: true, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const cells = screen.getAllByText("○");
    expect(cells.length).toBeGreaterThan(0);
  });

  it("shows the master first, then other agents", () => {
    const master: AgentInfo = {
      ...fakeAgent,
      id: "default",
      is_master: true,
    };
    const member: AgentInfo = {
      ...fakeAgent,
      id: "coach",
      is_master: false,
    };
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[member, master]} />);

    const headers = screen.getAllByRole("columnheader");
    const masterHeader = headers.find((h) => h.textContent?.includes("Agent"));
    expect(masterHeader).toBeInTheDocument();
  });

  it("shows the approval requirement for each tool", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: true, optional: false, agents: [] },
      { name: "read_file", description: "Read", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    expect(screen.getByText(vi.tools.whenNotAutonomous)).toBeInTheDocument();
    expect(screen.getByText(vi.tools.never)).toBeInTheDocument();
  });

  it("marks optional tools with a badge", () => {
    const tools: RegistryTool[] = [
      { name: "web_search", description: "Search", requires_approval: false, optional: true, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    expect(screen.getByText(vi.tools.optional)).toBeInTheDocument();
  });

  it("shows the legend with all cell types", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    expect(screen.getByText(vi.tools.legend)).toBeInTheDocument();
    expect(screen.getByText(vi.tools.legendOn)).toBeInTheDocument();
    expect(screen.getByText(vi.tools.legendExcluded)).toBeInTheDocument();
    expect(screen.getByText(vi.tools.legendMissingKey)).toBeInTheDocument();
    expect(screen.getByText(vi.tools.legendWorkMode)).toBeInTheDocument();
  });

  // The mark is drawn beside its meaning, and the meaning is also what a cell announces,
  // so neither may carry the mark a second time.
  it("draws each mark once, beside a meaning that is words only", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] },
    ];
    const { container } = render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);
    const marks = /[✓–○▫]/gu;

    const entries = screen.getAllByRole("definition");
    expect(entries.map((entry) => entry.textContent?.match(marks)?.length)).toEqual([1, 1, 1, 1]);
    expect(container.querySelector("td.cell span")?.getAttribute("aria-label")).not.toMatch(marks);
  });

  it("includes the tool description in the table", () => {
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Execute shell commands", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[fakeAgent]} />);

    expect(screen.getByText("Execute shell commands")).toBeInTheDocument();
  });

  it("shows an agent id as the column title tooltip", () => {
    const agent: AgentInfo = {
      ...fakeAgent,
      id: "coach",
      name: "HLV",
    };
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: [] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent]} />);

    const headers = screen.getAllByRole("columnheader");
    const coachHeader = headers.find((h) => h.getAttribute("title") === "coach");
    expect(coachHeader).toBeInTheDocument();
  });

  it("handles multiple agents correctly", () => {
    const agent1: AgentInfo = { ...fakeAgent, id: "agent1" };
    const agent2: AgentInfo = { ...fakeAgent, id: "agent2" };
    const tools: RegistryTool[] = [
      { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["agent1"] },
    ];
    render(<ToolsMatrix tools={tools} agents={[agent1, agent2]} />);

    const cells = screen.getAllByText("✓");
    expect(cells.length).toBeGreaterThan(0);
  });

  describe("the tools of an MCP server", () => {
    const search: RegistryTool = {
      name: "mcp__notion__search",
      description: "Tìm trang",
      requires_approval: true,
      optional: false,
      agents: ["default"],
      server: "notion",
      exposure: "deferred",
    };
    const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false };
    const cell = (row: HTMLElement, column: number) => within(row).getAllByRole("cell")[column];

    it("are held by the agents the server is switched on for, and marked off for the rest", () => {
      render(<ToolsMatrix tools={[search]} agents={[fakeAgent, coach]} />);

      const row = screen.getByTestId("tool-row");
      expect(within(cell(row, 1)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
      expect(within(cell(row, 2)).getByText("◇")).toHaveAttribute("aria-label", vi.tools.legendMcpOff);
      expect(cell(row, 2)).toHaveClass("cell", "mcp-off");
    });

    it("are not explained by the allow-list or the mode, which have no say over them", () => {
      // An agent with an allow-list that leaves the tool out, in the mode that lacks tools.
      const picky: AgentInfo = { ...coach, tools: ["write_file"], mode: "assistant" };
      render(<ToolsMatrix tools={[{ ...search, agents: [] }]} agents={[picky]} />);

      const row = within(screen.getByTestId("tool-row"));
      expect(row.getByText("◇")).toHaveAttribute("aria-label", vi.tools.legendMcpOff);
      expect(row.queryByText("–")).not.toBeInTheDocument();
      expect(row.queryByText("▫")).not.toBeInTheDocument();
    });

    it("name their server and how they reach an agent", () => {
      render(<ToolsMatrix tools={[search]} agents={[fakeAgent]} />);

      const head = within(screen.getByTestId("tool-row")).getByRole("rowheader");
      expect(within(head).getByText(vi.tools.fromServer("notion"))).toHaveClass("badge");
      expect(within(head).getByText(vi.mcp.exposure.deferred)).toHaveAttribute("title", vi.mcp.exposureTitle.deferred);
    });

    it("add their mark to the legend, which a crew without MCP never sees", () => {
      const own: RegistryTool = { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] };
      const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;

      const { unmount } = render(<ToolsMatrix tools={[own]} agents={[fakeAgent]} />);
      expect(legend()).not.toHaveTextContent(vi.tools.legendMcpOff);
      expect(within(legend()).getAllByRole("definition")).toHaveLength(4);
      expect(within(screen.getByTestId("tool-row")).queryByText(/^MCP /)).not.toBeInTheDocument();
      unmount();

      render(<ToolsMatrix tools={[own, search]} agents={[fakeAgent]} />);
      expect(legend()).toHaveTextContent(vi.tools.legendMcpOff);
      expect(within(legend()).getAllByRole("definition")).toHaveLength(5);
    });
  });
});
