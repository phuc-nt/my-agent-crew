import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});

const tool = (name: string, agents: string[], marks: Partial<RegistryTool> = {}): RegistryTool => ({ name, description: `Công cụ ${name}`, requires_approval: false, optional: false, agents, ...marks });
/** The crew's registry as the server lists it: every tool some agent holds, by name. */
const CREW = [
  tool("ask_user", ["dev"]),
  tool("delegate", ["default", "dev"]),
  tool("mcp__notion__search", ["coach"], { server: "notion", exposure: "direct" }),
  tool("tool_script", ["coach"], { with_reads: true }),
  tool("tool_search", ["coach"], { with_mcp: true }),
  tool("web_search", ["default", "coach"]),
  tool("write_file", ["default", "coach", "dev"]),
];
/** The registry once the last agent that handed work out has a list without the tool. */
const NOBODY_DELEGATES = CREW.filter((row) => row.name !== "delegate");
/** What an agent is handed whatever its list says. */
const HANDED = ["tool_script", "tool_search", "mcp__notion__search"];

type Shown = Partial<AgentInfo> & { listed?: string[]; names?: string[] };
/** An agent whose file lists `listed` and names the delegates `names`. Not the master, and
 * in the mode that only chats: unless it is said otherwise, it hands no work out. */
const agent = ({ listed = [], names = [], ...rest }: Shown = {}): AgentInfo =>
  ({ ...fakeAgent, id: "coach", is_master: false, tools: ["web_search", "write_file", ...HANDED], delegates: names, declared: { ...fakeAgent.declared, tools: listed, delegates: names }, ...rest });
const dev: AgentInfo = { ...agent(), id: "dev", name: "Dev" };
/** The three kinds of agent that hand work out, each holding the tool while no list stops it. */
const LEADS: [string, Shown][] = [
  ["the master", { id: "default", is_master: true }],
  ["a work agent", { mode: "work" }],
  ["an agent that names a delegate", { names: ["dev"] }],
];

function open(shown: AgentInfo, tools: RegistryTool[] = CREW) {
  backend.agents = [shown, dev];
  render(<AgentEditor agent={shown} agents={[shown, dev]} tools={tools} mcpServers={[]} providers={["fake"]} onBack={() => {}} onChanged={() => {}} />);
}

const section = () => within(screen.getByTestId("section-tools"));
const picker = () => within(section().getByTestId("tool-picker"));
const radio = (name: string) => section().getByRole("radio", { name });
const named = (boxes: HTMLElement[]) => boxes.map((box) => box.closest("li")?.querySelector("code")?.textContent);
const rows = () => named(picker().getAllByRole("checkbox"));
const ticked = () => named(picker().queryAllByRole("checkbox", { checked: true }));
const tick = (name: string) => userEvent.click(picker().getByRole("checkbox", { name: new RegExp(`^${name}`) }));
/** Saves, and returns the profile of every save sent, once the server has answered. */
async function saved() {
  await userEvent.click(screen.getByRole("button", { name: t.save }));
  await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
  return backend.requests.filter((r) => r.method === "PATCH").map((r) => (r.body as { profile: Record<string, unknown> }).profile);
}

describe("the chosen list, when it is switched on", () => {
  // A list gives no tool the agent's mode does not build: a name only the rest of the crew
  // holds would be one the server warns about at every start.
  it("starts from what this agent holds, not from what the rest of the crew holds", async () => {
    open(agent());
    await userEvent.click(radio(t.toolsPick));

    expect(rows()).toEqual(["ask_user", "web_search", "write_file"]);
    expect(ticked()).toEqual(["web_search", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["web_search", "write_file"] }]);
  });

  // Left out, the list would take from the agent the one thing that makes it a lead. The
  // last holds the tool by no rule this page knows: the server is believed over the copy.
  it.each([...LEADS, ["an agent only the server knows to hand work out", {}]])("starts with `delegate` for %s, which holds it", async (_who, lead) => {
    open(agent({ ...lead, tools: ["delegate", "write_file", ...HANDED] }));
    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["delegate", "write_file"]);
    expect(await saved()).toEqual([{ tools: ["delegate", "write_file"] }]);
  });

  it("starts from every tool a list can give when nothing is known of what the agent holds", async () => {
    open(agent({ tools: [] }));
    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["ask_user", "web_search", "write_file"]);
  });

  it("goes back to the list the file has, as it is written, after a detour through every tool", async () => {
    open(agent({ listed: ["write_file", "tool_script", "ask_user"], tools: ["write_file"] }));
    await userEvent.click(radio(t.toolsAll));
    expect(screen.getByText(t.dirty(1))).toBeInTheDocument();
    await userEvent.click(radio(t.toolsPick));

    expect(ticked()).toEqual(["ask_user", "write_file"]);
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });
});

describe("`delegate` in the picker", () => {
  it.each(LEADS)("is offered to %s whose list leaves it out, and is written once ticked", async (_who, lead) => {
    open(agent({ ...lead, listed: ["write_file"], tools: ["write_file"] }));
    expect(rows()).toEqual(["ask_user", "delegate", "web_search", "write_file"]);
    expect(ticked()).toEqual(["write_file"]);

    await tick("delegate");
    expect(await saved()).toEqual([{ tools: ["write_file", "delegate"] }]);
  });

  // The registry lists what some agent holds: with this list saved, nobody holds the tool.
  it("keeps its row when no agent holds it any more, so it can be ticked back", async () => {
    open(agent({ id: "default", is_master: true, listed: ["write_file"], tools: ["write_file"] }), NOBODY_DELEGATES);
    expect(rows()).toEqual(["ask_user", "delegate", "web_search", "write_file"]);
    expect(picker().getByText(t.toolDelegate)).toBeInTheDocument();
    await tick("delegate");
    expect(await saved()).toEqual([{ tools: ["write_file", "delegate"] }]);
  });

  it("has no row on an agent that hands no work out, whatever the rest of the crew holds", () => {
    open(agent({ listed: ["write_file"] }));
    expect(rows()).toEqual(["ask_user", "web_search", "write_file"]);
  });

  it("gets its row as the form makes the agent one that hands work out, and loses it again", async () => {
    open(agent({ listed: ["write_file"] }));
    const hands = within(screen.getByTestId("delegate-picker")).getByRole("checkbox", { name: /Dev/ });

    await userEvent.click(hands);
    expect(rows()).toContain("delegate");
    expect(ticked()).toEqual(["write_file"]);
    await userEvent.click(hands);
    expect(rows()).not.toContain("delegate");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: t.mode }), "work");
    expect(rows()).toContain("delegate");
  });
});

describe("a file whose list names what no list gives", () => {
  // Handed tools that go by a name this page does not know: only the registry's mark tells.
  const MARKED: [string, Partial<RegistryTool>][] = [["tool_program", { with_reads: true }], ["tool_lookup", { with_mcp: true }], ["notion_fetch", { server: "notion" }]];
  // A crew where no agent holds the search for a server's tools: the registry has no row to mark.
  const REGISTRY = [...CREW.filter((row) => row.name !== "tool_search"), ...MARKED.map(([name, marks]) => tool(name, ["coach"], marks))];
  // `delegate` on an agent that hands no work out, the handed tools by name and by mark,
  // and a tool of a server the crew no longer has.
  const NOTHING_FROM = ["delegate", "tool_script", "tool_search", "mcp__gone__fetch", ...MARKED.map(([name]) => name)];
  // A tool this crew does not hold: it may need a key the machine does not have yet.
  const old = () => agent({ listed: ["web_search", ...NOTHING_FROM, "image_read"] });

  it("opens on the list, with the person's choices ticked and nothing to save", () => {
    open(old(), REGISTRY);
    expect(radio(t.toolsPick)).toBeChecked();
    expect(rows()).toEqual(["ask_user", "web_search", "write_file"]);
    expect(ticked()).toEqual(["web_search"]);
    expect(screen.getByRole("button", { name: t.save })).toBeDisabled();
  });

  it("leaves those names out once the list is changed, and keeps every other choice", async () => {
    open(old(), REGISTRY);
    await tick("write_file");

    expect(await saved()).toEqual([{ tools: ["web_search", "image_read", "write_file"] }]);
    expect(ticked()).toEqual(["web_search", "write_file"]);
  });

  // The list is rewritten only by a change to the list: a hand-written file keeps its own.
  it("sends no list at all when another field is what was changed", async () => {
    open(old(), REGISTRY);
    await userEvent.type(screen.getByLabelText(t.name), " mới");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: t.scriptCalls }), "gated");

    const [sent] = await saved();
    expect(sent).toEqual({ name: "Agent mới", script_calls: "gated" });
    expect(sent).not.toHaveProperty("tools");
    expect(backend.agents[0].declared.tools).toEqual(["web_search", ...NOTHING_FROM, "image_read"]);
  });

  it("keeps `delegate` beside the other choices for an agent that hands work out", async () => {
    open(agent({ id: "default", is_master: true, listed: ["web_search", "delegate", "tool_script"], tools: ["delegate", "web_search", ...HANDED] }));
    expect(ticked()).toEqual(["delegate", "web_search"]);

    await tick("write_file");
    expect(await saved()).toEqual([{ tools: ["web_search", "delegate", "write_file"] }]);
  });

  // The server reads any list as a cap, so the form does too: nothing ticked, not "all".
  it("reads a list of nothing but such names as a list still, and writes the first tick alone", async () => {
    open(agent({ listed: ["delegate", "tool_script"] }));
    expect(radio(t.toolsPick)).toBeChecked();
    expect(ticked()).toEqual([]);

    await tick("web_search");
    expect(await saved()).toEqual([{ tools: ["web_search"] }]);
  });
});
