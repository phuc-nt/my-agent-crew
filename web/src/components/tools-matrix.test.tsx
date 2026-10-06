import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { ToolsMatrix } from "./tools-matrix";
import type { AgentInfo, RegistryTool } from "../api/types";
import { fakeAgent } from "../test/fake-backend";
import { scriptTool, searchTool } from "../test/fake-mcp";

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

    it("say of one opened for scripts that it is found like the rest, and called from a script when it only reads", () => {
      render(<ToolsMatrix tools={[{ ...search, exposure: "codemode" }]} agents={[fakeAgent]} />);

      const badge = within(screen.getByTestId("tool-row")).getByText("gọi qua script");
      expect(badge).toHaveClass("badge");
      expect(badge).toHaveAttribute(
        "title",
        "Không khai sẵn; agent tìm và nạp bằng tool_search như mức nạp khi cần. Công cụ nằm trong read_only thì còn gọi được từ script (tool_script).",
      );
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
      expect(legend()).not.toHaveTextContent(vi.tools.legendMcpNone);
      expect(within(legend()).getAllByRole("definition")).toHaveLength(5);
    });
  });

  describe("the search for the MCP tools that are not declared up front", () => {
    const find = searchTool(["default"]);
    const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false };
    const cell = (row: HTMLElement, column: number) => within(row).getAllByRole("cell")[column];

    it("is held by the agents with such tools, and marked as not needed for the rest", () => {
      render(<ToolsMatrix tools={[find]} agents={[fakeAgent, coach]} />);

      const row = screen.getByTestId("tool-row");
      expect(within(cell(row, 0)).getByText(vi.tools.never)).toBeInTheDocument();
      expect(within(cell(row, 1)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
      expect(within(cell(row, 2)).getByText("·")).toHaveAttribute("aria-label", vi.tools.legendMcpNone);
      expect(cell(row, 2)).toHaveClass("cell", "mcp-none");
      expect(cell(row, 2)).toHaveAttribute("title", vi.tools.legendMcpNone);
    });

    it("is not explained by the allow-list, a key or the mode, which have no say over it", () => {
      // An agent whose allow-list leaves it out, in the mode that lacks tools; and the
      // same row marked as needing a key, which nothing the server sends would do.
      const picky: AgentInfo = { ...coach, tools: ["write_file"], mode: "assistant" };
      const open: AgentInfo = { ...coach, id: "open", tools: [] };
      render(<ToolsMatrix tools={[{ ...find, agents: [], optional: true }]} agents={[picky, open]} />);

      const row = within(screen.getByTestId("tool-row"));
      expect(row.getAllByText("·")).toHaveLength(2);
      for (const mark of ["–", "○", "▫", "◇"]) expect(row.queryByText(mark)).not.toBeInTheDocument();
    });

    it("says it comes with the servers and not with the allow-list", () => {
      render(<ToolsMatrix tools={[find]} agents={[fakeAgent]} />);

      const head = within(screen.getByTestId("tool-row")).getByRole("rowheader");
      expect(within(head).getByText(vi.tools.withMcp)).toHaveClass("badge");
      expect(within(head).getByText(vi.tools.withMcp)).toHaveAttribute("title", vi.tools.withMcpTitle);
      expect(within(head).queryByText(/^MCP /)).not.toBeInTheDocument();
    });

    it("adds its mark to the legend, which a crew with nothing to find never sees", () => {
      const own: RegistryTool = { name: "shell_run", description: "Run", requires_approval: false, optional: false, agents: ["default"] };
      const direct: RegistryTool = { ...own, name: "mcp__wiki__read", server: "wiki", exposure: "direct" };
      const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;

      const nothing = render(<ToolsMatrix tools={[own, direct]} agents={[fakeAgent]} />);
      expect(legend()).not.toHaveTextContent(vi.tools.legendMcpNone);
      expect(within(legend()).getAllByRole("definition")).toHaveLength(5);
      expect(screen.queryByText(vi.tools.withMcp)).not.toBeInTheDocument();
      nothing.unmount();

      const both = render(<ToolsMatrix tools={[own, direct, find]} agents={[fakeAgent]} />);
      const marks = within(legend()).getAllByRole("definition");
      expect(marks).toHaveLength(6);
      expect(marks[5]).toHaveTextContent(`·${vi.tools.legendMcpNone}`);
      expect(marks[5].querySelector(".legend-mark")).toHaveClass("mcp-none");
      // Without a server's tool on the page, its own mark stays and the server's goes.
      both.unmount();
      render(<ToolsMatrix tools={[own, find]} agents={[fakeAgent]} />);
      expect(legend()).toHaveTextContent(vi.tools.legendMcpNone);
      expect(legend()).not.toHaveTextContent(vi.tools.legendMcpOff);
    });
  });

  describe("the script that calls the MCP tools opened for scripts", () => {
    const coach: AgentInfo = { ...fakeAgent, id: "coach", name: "HLV", is_master: false };
    const find = searchTool(["coach", "default"]);
    const script = scriptTool(["default"]);
    const cell = (row: HTMLElement, column: number) => within(row).getAllByRole("cell")[column];

    it("is held only by the agents with such a tool, whatever else they can find", () => {
      render(<ToolsMatrix tools={[find, script]} agents={[fakeAgent, coach]} />);

      const [finding, scripting] = screen.getAllByTestId("tool-row");
      expect(within(scripting).getByRole("rowheader")).toHaveTextContent(/^tool_script/);
      expect(within(cell(scripting, 0)).getByText(vi.tools.never)).toBeInTheDocument();
      expect(within(cell(scripting, 1)).getByText("✓")).toHaveAttribute("aria-label", vi.tools.legendOn);
      // The coach has tools to find and none a script may call.
      expect(within(cell(finding, 2)).getByText("✓")).toBeInTheDocument();
      expect(within(cell(scripting, 2)).getByText("·")).toHaveAttribute("aria-label", vi.tools.legendMcpNone);
      expect(cell(scripting, 2)).toHaveClass("cell", "mcp-none");
      expect(cell(scripting, 2)).toHaveAttribute("title", vi.tools.legendMcpNone);
    });

    it("is not explained by the allow-list, a key or the mode, which have no say over it", () => {
      const picky: AgentInfo = { ...coach, tools: ["write_file"], mode: "assistant" };
      render(<ToolsMatrix tools={[{ ...script, agents: [], optional: true }]} agents={[picky]} />);

      const row = within(screen.getByTestId("tool-row"));
      expect(row.getByText("·")).toBeInTheDocument();
      for (const mark of ["–", "○", "▫", "◇"]) expect(row.queryByText(mark)).not.toBeInTheDocument();
    });

    it("wears the badge of the search, whose title says when an agent holds each of the two", () => {
      render(<ToolsMatrix tools={[find, script]} agents={[fakeAgent]} />);

      const badges = screen.getAllByTestId("tool-row").map((row) => within(row).getByText("đi kèm MCP"));
      expect(badges).toHaveLength(2);
      for (const badge of badges) {
        expect(badge).toHaveClass("badge");
        expect(badge).toHaveAttribute(
          "title",
          "Không thuộc danh sách công cụ của agent. Agent có tool_search khi được giao công cụ MCP không khai sẵn, và có tool_script khi một công cụ MCP chỉ đọc được mở cho script.",
        );
      }
    });

    it("shares the one line the legend has for a tool that comes with MCP tools", () => {
      const legend = () => screen.getByText(vi.tools.legend).parentElement as HTMLElement;
      const lines = () => within(legend()).getAllByRole("definition").filter((line) => line.querySelector(".mcp-none"));

      const alone = render(<ToolsMatrix tools={[script]} agents={[fakeAgent, coach]} />);
      expect(lines()).toHaveLength(1);
      expect(lines()[0]).toHaveTextContent(/^·agent không có công cụ MCP nào cần tới công cụ này$/);
      alone.unmount();

      render(<ToolsMatrix tools={[find, script]} agents={[fakeAgent, coach]} />);
      expect(lines()).toHaveLength(1);
      expect(within(legend()).getAllByRole("definition")).toHaveLength(5);
    });
  });
});
