// An MCP server the file no longer declares has a row only while it is ticked. Unticked, the
// row is gone under the keyboard that unticked it, which is then on no row at all.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, McpServerInfo, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { mcpServer } from "../../test/fake-mcp";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const OWN: RegistryTool[] = [{ name: "write_file", description: "Ghi tệp", requires_approval: true, optional: false, agents: ["default"] }];
const notion = mcpServer();
const wiki = mcpServer({ name: "wiki", url: "https://wiki.example.test/mcp" });

/** Opens the editor on an agent handed `mcp`, in a file that declares `servers`. */
function open(mcp: string[], servers: McpServerInfo[] = [], rest: Partial<AgentInfo> = {}) {
  const shown: AgentInfo = { ...fakeAgent, mcp, ...rest };
  const backend = new FakeBackend();
  backend.agents = [shown];
  backend.mcp.servers = servers;
  vitest.stubGlobal("fetch", backend.fetch);
  render(<AgentEditor agent={shown} agents={[shown]} tools={OWN} mcpServers={servers} providers={[]} onBack={() => {}} onChanged={() => {}} />);
}

const section = () => within(screen.getByTestId("section-tools"));
const rows = () => within(section().getByTestId("mcp-picker")).getAllByRole("listitem");
const named = (row: HTMLElement) => row.querySelector("code")?.textContent;
const servers = () => rows().map(named);
/** The box of the server by that very name: one name here begins with another. */
function box(name: string) {
  const row = rows().find((it) => named(it) === name);
  if (!row) throw new Error(`no row for the server ${name}`);
  return within(row).getByRole("checkbox");
}
const radio = (name: string) => section().getByRole("radio", { name });

describe("the keyboard once a server the file dropped is unticked", () => {
  it("is on the row that took its place", async () => {
    open(["old", "older"], [notion]);
    expect(servers()).toEqual(["notion", "old", "older"]);

    await userEvent.click(box("old"));

    expect(servers()).toEqual(["notion", "older"]);
    await waitFor(() => expect(box("older")).toHaveFocus());
  });

  it("is on the last row when it stood last itself", async () => {
    open(["old", "older"], [notion]);

    await userEvent.click(box("older"));

    expect(servers()).toEqual(["notion", "old"]);
    await waitFor(() => expect(box("old")).toHaveFocus());
  });

  it("is on the last server the file declares when no dropped one is left", async () => {
    open(["old"], [notion, wiki]);

    await userEvent.click(box("old"));

    expect(servers()).toEqual(["notion", "wiki"]);
    await waitFor(() => expect(box("wiki")).toHaveFocus());
    // Landing on a box ticks nothing.
    expect(box("wiki")).not.toBeChecked();
  });

  it("is on “every tool”, the radio that is on, when the list of servers went with the row", async () => {
    open(["old"]);

    await userEvent.click(box("old"));

    expect(section().queryByTestId("mcp-picker")).not.toBeInTheDocument();
    expect(section().getByText(t.mcpNone)).toBeInTheDocument();
    await waitFor(() => expect(radio(t.toolsAll)).toHaveFocus());
    expect(radio(t.toolsAll)).toBeChecked();
  });

  // The radio that is off would be one Space away from emptying the list of tools.
  it("is on “pick”, the radio that is on, when the agent's file lists its tools", async () => {
    open(["old"], [], { declared: { ...fakeAgent.declared, tools: ["write_file"] } });
    expect(radio(t.toolsPick)).toBeChecked();

    await userEvent.click(box("old"));

    await waitFor(() => expect(radio(t.toolsPick)).toHaveFocus());
    expect(radio(t.toolsPick)).toBeChecked();
    // One change to save: the server taken off. The list of tools is as the file has it.
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
  });

  // A tap unticks without taking the keyboard: it stays in the field the person is typing in.
  it("stays where it is when it was not on the row", () => {
    open(["old", "older"], [notion]);
    screen.getByLabelText(t.name).focus();

    fireEvent.click(box("old"));

    expect(servers()).toEqual(["notion", "older"]);
    expect(screen.getByLabelText(t.name)).toHaveFocus();
  });

  it("stays on the box of a server the file declares: its row does not go", async () => {
    open(["notion", "old"], [notion]);

    await userEvent.click(box("notion"));

    expect(servers()).toEqual(["notion", "old"]);
    expect(box("notion")).not.toBeChecked();
    expect(box("notion")).toHaveFocus();
  });
});
