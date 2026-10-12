// What an agent's tool allow-list has a say over, as the server judges it: the rows the
// picker offers, the names its list holds beyond them, and the list it starts from.
import type { AgentInfo, AgentPatch, RegistryTool } from "../../api/types";
import { vi } from "../../i18n/vi";

export interface AllowList {
  /** The tools a list has a say over: the picker offers a tick for each. */
  rows: RegistryTool[];
  /** The names the form's list holds that it has no say over, each once, in its order. */
  stray: string[];
  /** The list the picker holds once it is switched on. Empty only when there is no row. */
  start: string[];
}

/** A row for a name the catalogue does not describe. The catalogue lists what some agent
 * holds, and `delegate` is held by nobody once every list leaves it out, so it keeps a
 * description of its own. */
function bare(name: string): RegistryTool {
  const description = name === "delegate" ? vi.editor.toolDelegate : "";
  return { name, description, requires_approval: false, optional: false, agents: [] };
}

/**
 * The allow-list of one agent, as the form may show and write it.
 *
 * Which names a list has a say over is the server's to tell, agent by agent: it reports
 * them as `listable_tools`, for the agent as it is saved now. This page keeps no copy of
 * that rule. A name the form's list holds that the server does not report is shown apart
 * and stays where the person put it: it may be a tool the machine cannot run today.
 *
 * An agent that is not saved yet has no such report. It is offered every tool of the
 * catalogue that the catalogue itself does not mark as handed outside any list.
 */
export function allowList(tools: RegistryTool[], agent: AgentInfo | null, draft: AgentPatch): AllowList {
  if (agent === null) {
    const rows = tools.filter((tool) => !tool.server && !tool.with_mcp && !tool.with_reads);
    return { rows, stray: [], start: rows.map((tool) => tool.name) };
  }
  const listable = agent.listable_tools;
  const described = new Map(tools.map((tool) => [tool.name, tool]));
  const rows = listable.map((name) => described.get(name) ?? bare(name));
  const stray = [...new Set(draft.tools ?? [])].filter((name) => !listable.includes(name));

  const listed = agent.declared.tools;
  const held = listable.filter((name) => agent.tools.includes(name));
  // The list the file has, as it is written, when this session set it aside: going back to
  // it is no change. Else what the agent holds today, so that switching the list on takes
  // nothing away and adds no name; else, when it holds none of them, every row.
  const start = listed.length > 0 ? listed : held.length > 0 ? held : listable;

  return { rows, stray, start };
}
