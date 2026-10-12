// What the agent form holds: the keys it may change, and the values it starts from.
import type { AgentInfo, AgentPatch } from "../api/types";

/** The keys the form can change. `id`, `dir` and everything derived stay out of it. */
export type DraftKey = keyof AgentPatch;

export const EDITABLE: DraftKey[] = [
  "name",
  "description",
  "mode",
  "workspace",
  "routes",
  "escalation_route",
  "cost_cap_usd",
  "max_steps",
  "autonomous",
  "shell_ask_patterns",
  "tool_output_chars",
  "memory_consolidate",
  "delegates",
  "tools",
  "mcp",
  "script_calls",
  "script_llm",
  "schedules",
  "telegram",
];

/** Scripts that may change things, on an agent the form has running by itself: each such
 * call goes through and nobody is asked. The form says so at both of the settings. */
export const scriptsAskNobody = (draft: AgentPatch): boolean => draft.script_calls === "gated" && draft.autonomous === true;

/** The keys `mode: work` supplies a default for when the manifest stays silent. */
export const MODE_DEFAULTED: DraftKey[] = ["cost_cap_usd", "max_steps", "autonomous"];

/** A schedule's two script keys say the same null as absent: a server older than script
 * jobs declares its rows without them, and a row switched to a script and back holds them
 * as null. Left as they are, that row would count as changed with nothing in it changed. */
const unsaid = (key: string, value: unknown) =>
  value === null && (key === "script" || key === "then_prompt") ? undefined : value;

/** Deep equality by serialisation: the values here are JSON already, and a route list or
 * a tool allow-list has to compare by content rather than by identity. */
export function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null, unsaid) === JSON.stringify(b ?? null, unsaid);
}

/**
 * The form's starting point.
 *
 * `delegates` and `schedules` come from `declared` rather than from the effective
 * profile: the master with no delegates of its own reaches every agent, and writing that
 * computed list back would pin it to today's crew, leaving agents added later
 * unreachable. The consolidation job is likewise generated from `memory_consolidate`,
 * and saving it as an ordinary schedule would run it twice. `tools` is the same seam:
 * the profile reports what the agent holds, and saving that would turn an agent with no
 * allow-list into one capped at today's toolbox, naming tools no list gives.
 */
export function toDraft(agent: AgentInfo): AgentPatch {
  return {
    name: agent.name,
    description: agent.description,
    mode: agent.mode,
    workspace: agent.workspace,
    routes: agent.routes,
    escalation_route: agent.escalation_route,
    cost_cap_usd: agent.cost_cap_usd,
    max_steps: agent.max_steps,
    autonomous: agent.autonomous,
    shell_ask_patterns: agent.shell_ask_patterns,
    tool_output_chars: agent.tool_output_chars,
    memory_consolidate: agent.memory_consolidate,
    delegates: agent.declared.delegates,
    tools: agent.declared.tools,
    // A crew still running the code from before MCP reports none: an empty list, so that
    // ticking a box and unticking it leaves nothing to save.
    mcp: agent.mcp ?? [],
    // A crew older than the two script switches reports neither. It runs as these two
    // values say, so they are what the form shows, and choosing one and choosing back
    // leaves nothing to save.
    script_calls: agent.script_calls ?? "read_only",
    script_llm: agent.script_llm ?? true,
    schedules: agent.declared.schedules,
    telegram: agent.telegram,
  };
}
