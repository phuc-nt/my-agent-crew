import type {
  CommandInfo,
  DeclaredProfile,
  RouteInfo,
  ScheduleInfo,
  ScriptCalls,
  SkillInfo,
  TelegramBlock,
  ToolInfo,
} from "./agents";

/** One agent profile as listed by GET /api/agents. */
export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  dir: string;
  workspace: string;
  routes: RouteInfo[];
  /** The one route a stuck turn moves to, as the agent's file names it; null when it names
   * none, which is how every agent starts. */
  escalation_route: RouteInfo | null;
  cost_cap_usd: number;
  max_steps: number;
  autonomous: boolean;
  /** Command shapes that pause for approval even when the agent is autonomous. */
  shell_ask_patterns: string[];
  tool_output_chars: number;
  /** Cron for the nightly memory pass; "" when the agent does not consolidate. */
  memory_consolidate: string;
  /** The persona files that exist on disk, so the editor can mark which have content. */
  persona_files: string[];
  /** Every persona file this agent would read, written or not. An editor offers all of
   * them: a new agent has none, and listing only what exists could never create one. */
  persona_names: string[];
  /** Folders the agent's skills are loaded from, its own first then the shared one. */
  skills_dirs: string[];
  schedules: ScheduleInfo[];
  /** "assistant" chats; "work" carries the coding tools and can hand off to `delegates`. */
  mode: string;
  /** Agents this one can hand work to; for the master that is everyone else. */
  delegates: string[];
  /** The names of the tools the agent holds, those no list gives among them. Never the
   * allow-list: that is `declared.tools`. */
  tools: string[];
  /** The MCP servers whose tools the agent is handed, by the names `config.yaml` gives
   * them. One the file no longer declares stays listed until an edit takes it out. */
  mcp: string[];
  skills: string[];
  /** The one agent the person talks to; it does the work or delegates it. */
  is_master: boolean;
  /** False for an agent a kit defines: there is no manifest to patch, so a write to it
   * is refused and the editor shows where the definition actually lives instead. */
  editable: boolean;
  /** Set on the master when a Telegram bot also talks to it; the token stays on the server. */
  telegram: TelegramBlock | null;
  /** What the agent's own file says, where that differs from what the crew computed.
   * An editor diffs against these: saving a computed value back would write the
   * computation into the file and freeze it there. */
  declared: DeclaredProfile;
  /** What the agent's kits (`.agents/`, `.claude/`, `.opencode/`) add: slash commands, the
   * number of tool hooks, and the kit directories they came from. */
  commands: CommandInfo[];
  hooks: number;
  kits: string[];
  /** What the agent's scripts may call. Absent from a server older than the key, which
   * runs every agent as `read_only`. */
  script_calls?: ScriptCalls;
  /** Whether the agent's scripts, in a turn and in a scheduled job, may ask a model: the
   * only part of a script that costs money. Absent from a server older than the key, which
   * lets them. */
  script_llm?: boolean;
  /** The names a `tools:` list takes effect for, for this agent as it is saved now, sorted:
   * the server's own judgement, which the tool picker follows. A tool the agent is handed
   * whatever its list says is never among them. Absent from a server older than the key:
   * the page it serves between an update and its restart is this one. */
  listable_tools?: string[];
}

export interface InstallRequest {
  template: string;
  agent_id?: string;
  workspace?: string;
  force?: boolean;
}

/** What `POST /agents/install` did: which agents were written, which are already live. */
export interface InstallResult {
  installed: string[];
  live: string[];
  /** An agent in `installed` is missing from `live`: it could not join the running crew
   *  and will be there after a restart. */
  needs_restart: boolean;
}

export interface AgentDetail extends Omit<AgentInfo, "tools" | "skills"> {
  tools: ToolInfo[];
  skills: SkillInfo[];
}

/**
 * The keys an edit may name. It is the same whitelist the server enforces, written out
 * here so a typo is a type error rather than a 422 the person has to read.
 *
 * Everything is optional because a patch names only what changed; `null` on a key clears
 * it back to the default rather than setting it to nothing.
 */
export interface AgentPatch {
  name?: string;
  description?: string;
  routes?: RouteInfo[] | null;
  escalation_route?: RouteInfo | null;
  workspace?: string | null;
  persona_files?: string[] | null;
  skills_dirs?: string[] | null;
  cost_cap_usd?: number | null;
  max_steps?: number | null;
  autonomous?: boolean | null;
  shell_ask_patterns?: string[] | null;
  tool_output_chars?: number | null;
  schedules?: unknown[] | null;
  telegram?: TelegramBlock | null;
  memory_consolidate?: string | null;
  mode?: string;
  delegates?: string[] | null;
  tools?: string[] | null;
  mcp?: string[] | null;
  script_calls?: ScriptCalls;
  script_llm?: boolean;
}

/**
 * What a write to an agent's profile produced: the agent as it is now. Every edit is live
 * once it is saved, schedules included, so `restart_required` is always empty now. The key
 * is kept for pages loaded from an older bundle, which read it; a server from before
 * schedules went live still names a reason there, and a save it answers is not said to be
 * live.
 */
export interface AgentSaved {
  profile: AgentInfo;
  restart_required: string[];
}
