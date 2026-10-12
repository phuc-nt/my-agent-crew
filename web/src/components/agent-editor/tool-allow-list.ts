// What an agent's tool allow-list has a say over: the rows the picker offers, the list it
// starts from, and the names it leaves out of every list it writes.
import type { AgentInfo, AgentPatch, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";

/** The tool an agent hands work out with. Must match `DELEGATE_TOOL_NAME` in the backend's
 * `agents/roster.py`. */
export const DELEGATE = "delegate";
/** The tools an agent is handed whatever its list says: the search for a server's tools and
 * the script tool, then every tool of an MCP server by its prefix. Must match `SEARCH_TOOL`
 * in the backend's `mcp/tool_search.py`, `SCRIPT_TOOL` in `script/scope.py` and `PREFIX` in
 * `mcp/tools.py`. The registry marks them too, but only while some agent holds them. */
const HANDED = ["tool_search", "tool_script"];
const MCP_PREFIX = "mcp__";
/** Must match `WORK` in the backend's `agents/profile.py`. */
const WORK = "work";

export interface AllowList {
  /** The tools the picker offers a tick for. */
  rows: RegistryTool[];
  /** The list the picker holds once it is switched on. Empty only when there is no row. */
  start: string[];
  /** A list as the form writes it: the same names in the same order, short of those the
   * list has no say over. */
  written: (names: string[]) => string[];
}

/**
 * Whether the agent hands work out when its list lets it: the master, a work agent, and
 * any agent that names delegates. Must match `Runtime.delegates` in the backend's
 * `server/runtime.py`. An agent that holds the tool hands work out whatever this copy of
 * the rule says, so a rule the backend has since widened takes nothing away here.
 */
function handsWorkOut(agent: AgentInfo | null, draft: AgentPatch): boolean {
  const held = agent?.tools.includes(DELEGATE) ?? false;
  return held || (agent?.is_master ?? false) || draft.mode === WORK || (draft.delegates ?? []).length > 0;
}

/**
 * The allow-list of one agent, as the form may show and write it.
 *
 * A list only takes away: it gives an agent no tool its mode does not build, and the
 * server warns at every start about each name it lists that was not built. So the picker
 * never puts in a list, by itself, a name this agent gets no tool from.
 *
 * The tools of an MCP server, the search that finds them and the script tool are handed
 * whatever the list says: they get no row, and are left out of every list written here.
 * `delegate` is the one handed tool a list does have a say over. An agent that hands work
 * out loses it to a list that does not name it, so for that agent it is a row like any
 * other; on any other agent the name gives nothing, and is treated as the first kind.
 *
 * Every other name stays as the person put it, a tool this crew does not know included:
 * it may be one that needs a key the machine does not have yet.
 */
export function allowList(tools: RegistryTool[], agent: AgentInfo | null, draft: AgentPatch): AllowList {
  const delegating = handsWorkOut(agent, draft);
  const marked = new Set(tools.filter((tool) => tool.server || tool.with_mcp || tool.with_reads).map((tool) => tool.name));
  const given = (name: string) =>
    !marked.has(name) && !HANDED.includes(name) && !name.startsWith(MCP_PREFIX) && (name !== DELEGATE || delegating);

  const rows = tools.filter((tool) => given(tool.name));
  const listed = agent?.declared.tools ?? [];
  // The registry lists what some agent holds, and nobody may hold this tool once this
  // agent's own list leaves it out. Without a row here it could then never be ticked
  // back. An agent with no list is handed the tool, so for it the registry is believed.
  if (delegating && listed.length > 0 && !rows.some((tool) => tool.name === DELEGATE)) {
    const after = rows.findIndex((tool) => tool.name > DELEGATE);
    const row = { name: DELEGATE, description: vi.editor.toolDelegate, requires_approval: false, optional: false, agents: [] };
    rows.splice(after < 0 ? rows.length : after, 0, row);
  }

  const names = rows.map((tool) => tool.name);
  const held = names.filter((name) => agent?.tools.includes(name));
  // The list the file has, as it is written, when this session set it aside: going back to
  // it is no change. Else what the agent holds today, so that switching the list on takes
  // nothing away and adds no name; else, with nothing known of what it holds, every row.
  const start = listed.length > 0 ? listed : held.length > 0 ? held : names;

  return { rows, start, written: (list) => list.filter(given) };
}
