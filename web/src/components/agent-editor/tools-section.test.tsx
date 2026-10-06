import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, McpServerInfo, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { mcpServer, mcpTool, unknownServer } from "../../test/fake-mcp";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
let backend: FakeBackend;

const OWN: RegistryTool[] = [
  { name: "write_file", description: "Ghi tệp", requires_approval: true, optional: false, agents: ["default"] },
  { name: "web_search", description: "Tìm trên web", requires_approval: false, optional: true, agents: [] },
];

function open(shown: AgentInfo, servers: McpServerInfo[] = [], declared = servers) {
  backend = new FakeBackend();
  backend.agents = [shown];
  backend.mcp.servers = declared;
  vitest.stubGlobal("fetch", backend.fetch);
  const tools = [...OWN, ...backend.mcp.registryTools()];
  render(
    <AgentEditor agent={shown} agents={[shown]} tools={tools} mcpServers={servers} providers={[]} onBack={() => {}} onChanged={() => {}} />,
  );
}

const section = () => within(screen.getByTestId("section-tools"));
const picker = () => within(section().getByTestId("mcp-picker"));
const box = (name: string) => picker().getByRole("checkbox", { name: new RegExp(`^${name}`) });
const saveButton = () => screen.getByRole("button", { name: t.save });
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

const notion = mcpServer({ description: "Ghi chú của nhà", tools: [mcpTool("notion", "search"), mcpTool("notion", "fetch")] });
const wiki = mcpServer({ name: "wiki", url: "https://wiki.example.test/mcp", status: "signed_out" });

describe("the MCP servers of an agent", () => {
  it("says the file declares none, with no boxes to tick", () => {
    open(fakeAgent);

    expect(section().getByRole("heading", { name: t.mcp })).toBeInTheDocument();
    expect(section().getByText(t.mcpHint)).toBeInTheDocument();
    expect(section().getByText(t.mcpNone)).toBeInTheDocument();
    expect(section().queryByTestId("mcp-picker")).not.toBeInTheDocument();
  });

  it("lists every server the file declares, with its state and what it is", () => {
    open(fakeAgent, [notion, wiki]);

    expect(section().queryByText(t.mcpNone)).not.toBeInTheDocument();
    const rows = picker().getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("notion");
    expect(within(rows[0]).getByText(vi.mcp.status.connected)).toHaveClass("badge", "ok");
    expect(rows[0]).toHaveTextContent("Ghi chú của nhà");
    expect(rows[0]).toHaveTextContent(vi.mcp.tools(2));
    // With no description the address stands in for it, and no tools are counted.
    expect(within(rows[1]).getByText(vi.mcp.status.signed_out)).toHaveClass("badge", "warn");
    expect(rows[1]).toHaveTextContent("https://wiki.example.test/mcp");
    expect(rows[1]).not.toHaveTextContent(vi.mcp.tools(0));
    expect(box("notion")).not.toBeChecked();
    expect(box("wiki")).not.toBeChecked();
  });

  it("hands a server to the agent with one tick and a save, and nothing else changes", async () => {
    open(fakeAgent, [notion, wiki]);

    await userEvent.click(box("wiki"));
    await userEvent.click(box("notion"));
    expect(box("notion")).toBeChecked();
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { mcp: ["wiki", "notion"] } }]);
    expect(box("notion")).toBeChecked();
    expect(box("wiki")).toBeChecked();
  });

  it("takes a server away with one tick, and is clean again once ticked back", async () => {
    open({ ...fakeAgent, mcp: ["notion", "wiki"] }, [notion, wiki]);
    expect(box("notion")).toBeChecked();

    await userEvent.click(box("notion"));
    expect(box("notion")).not.toBeChecked();
    expect(box("wiki")).toBeChecked();
    await userEvent.click(saveButton());
    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { mcp: ["wiki"] } }]);

    await userEvent.click(box("wiki"));
    await userEvent.click(box("wiki"));
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("keeps a row for a server the file no longer declares, so it can be taken off", async () => {
    open({ ...fakeAgent, mcp: ["old", "notion"] }, [notion]);

    const rows = picker().getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("old");
    expect(rows[1]).toHaveTextContent(t.mcpGone);
    expect(rows[0]).not.toHaveTextContent(t.mcpGone);
    expect(box("old")).toBeChecked();

    await userEvent.click(box("old"));
    // Unticked, it has no row to come back to: the file does not declare it.
    expect(picker().getAllByRole("listitem")).toHaveLength(1);
    await userEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { mcp: ["notion"] } }]);
  });

  it("shows a dropped server's row even when the file declares no server at all", () => {
    open({ ...fakeAgent, mcp: ["old"] });

    expect(section().queryByText(t.mcpNone)).not.toBeInTheDocument();
    expect(box("old")).toBeChecked();
  });

  it("shows the server's reason when a save still names a server the file dropped", async () => {
    open({ ...fakeAgent, mcp: ["old"] }, [notion]);

    await userEvent.click(box("notion"));
    await userEvent.click(saveButton());

    expect(await screen.findByText(t.saveFailed(unknownServer("old")))).toBeInTheDocument();
    expect(box("notion")).toBeChecked();
    expect(box("old")).toBeChecked();
  });

  it("cannot be changed on an agent that is not edited here", () => {
    open({ ...fakeAgent, editable: false, mcp: ["old"] }, [notion]);

    expect(box("notion")).toBeDisabled();
    expect(box("old")).toBeDisabled();
  });
});

describe("the allow-list beside a server's tools", () => {
  const handed = { ...fakeAgent, tools: [], mcp: ["notion"] };
  const names = () =>
    within(section().getByTestId("tool-picker"))
      .getAllByRole("listitem")
      .map((row) => row.querySelector("code")?.textContent);

  it("lists the crew's own tools only: a server's tools come with the server", () => {
    open(handed, [notion]);

    // The agent holds the server's tools and the search that finds them; neither is the
    // allow-list's to give.
    expect(backend.mcp.registryTools().map((tool) => tool.name)).toEqual(["tool_search", "mcp__notion__search", "mcp__notion__fetch"]);
    expect(names()).toEqual(["write_file", "web_search"]);
  });

  it("starts from the crew's own tools when it is switched on, never a server's", async () => {
    open(handed, [notion]);
    expect(backend.mcp.registryTools()[0]).toMatchObject({ name: "tool_search", agents: ["default"] });

    await userEvent.click(section().getByRole("radio", { name: t.toolsPick }));
    await userEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { tools: ["write_file", "web_search"] } }]);
  });
});
