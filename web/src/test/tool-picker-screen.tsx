// The agent editor opened on one agent of a small crew, and the ways the tests of its tool
// picker read it and act on it.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, vi as vitest } from "vitest";
import type { AgentInfo, RegistryTool } from "../api/types";
import { AgentEditor } from "../components/agent-editor/agent-editor";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeAgent } from "./fake-backend";

const t = vi.editor;

export const tool = (name: string, agents: string[], marks: Partial<RegistryTool> = {}): RegistryTool => ({ name, description: `Công cụ ${name}`, requires_approval: false, optional: false, agents, ...marks });
/** The crew's catalogue as the server lists it: every tool some agent holds, by name. */
export const CREW = [
  tool("ask_user", ["dev"]),
  tool("delegate", ["default", "dev"]),
  tool("mcp__notion__search", ["coach"], { server: "notion", exposure: "direct" }),
  tool("tool_script", ["coach"], { with_reads: true }),
  tool("tool_search", ["coach"], { with_mcp: true }),
  tool("web_search", ["default", "coach"]),
  tool("write_file", ["default", "coach", "dev"]),
];
/** What an agent is handed whatever its list says. */
export const HANDED = ["tool_script", "tool_search", "mcp__notion__search"];
/** What the server says a list has a say over, for an agent that only chats and for one that
 * hands work out. Nobody holds `memory_save`, so the catalogue has no row for it. */
export const CHATS = ["memory_save", "web_search", "write_file"];
export const LEADS = ["delegate", ...CHATS];

export type Shown = Partial<AgentInfo> & { listed?: string[] };
/** An agent whose file lists `listed`. Not the master, in the mode that only chats, naming
 * no delegate, and holding two of the three tools a list has a say over. */
export const agent = ({ listed = [], ...rest }: Shown = {}): AgentInfo =>
  ({ ...fakeAgent, id: "coach", is_master: false, tools: ["write_file", "web_search", ...HANDED], listable_tools: CHATS, declared: { ...fakeAgent.declared, tools: listed }, ...rest });
export const dev: AgentInfo = { ...agent(), id: "dev", name: "Dev" };

let backend: FakeBackend;

/** Opens the editor on `shown`, in a crew of it and `dev`, against a server of its own. */
export function open(shown: AgentInfo, tools: RegistryTool[] = CREW): FakeBackend {
  backend = new FakeBackend();
  backend.agents = [shown, dev];
  vitest.stubGlobal("fetch", backend.fetch);
  render(<AgentEditor agent={shown} agents={[shown, dev]} tools={tools} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
  return backend;
}

export const section = () => within(screen.getByTestId("section-tools"));
export const picker = () => within(section().getByTestId("tool-picker"));
export const radio = (name: string) => section().getByRole("radio", { name });
const named = (boxes: HTMLElement[]) => boxes.map((box) => box.closest("li")?.querySelector("code")?.textContent);
/** The names the picker has a row for, and those of them that are ticked, top to bottom. */
export const rows = () => named(picker().getAllByRole("checkbox"));
export const ticked = () => named(picker().queryAllByRole("checkbox", { checked: true }));
export const box = (name: string) => picker().getByRole("checkbox", { name: new RegExp(`^${name}`) });
export const tick = (name: string) => userEvent.click(box(name));

/** Saves, and returns the profile of every save sent, once the server has answered. */
export async function saved() {
  await userEvent.click(screen.getByRole("button", { name: t.save }));
  await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
  return backend.requests.filter((r) => r.method === "PATCH").map((r) => (r.body as { profile: Record<string, unknown> }).profile);
}
