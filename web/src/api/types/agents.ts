export interface ToolInfo {
  name: string;
  description: string;
  requires_approval: boolean;
}

export interface SkillInfo {
  name: string;
  description: string;
  always: boolean;
  /** Command-line programs the skill drives. */
  requires_bins?: string[];
  /** The one command that prints the real syntax, shown so a person can run it too. */
  cli_help?: string;
  /** Of `requires_bins`, the ones this machine cannot find. */
  missing_bins?: string[];
}

export interface RouteInfo {
  provider: string;
  model: string;
}

/** A bundled agent profile the crew tab can install in one click through the install API. */
export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
  mode: string;
  /** Empty means no allow-list: the role keeps every tool its mode grants. */
  tools: string[];
  delegates: string[];
}

/** What running a schedule does: ask the agent, run a shell command, or rewrite memory. */
export type JobKind = "prompt" | "command" | "script" | "consolidate";

export interface ScheduleInfo {
  id: string;
  name: string;
  kind: JobKind;
  cron: string | null;
  every: string | null;
  prompt: string | null;
  command: string | null;
  /** The source of a script the job runs with no model call, held character for character:
   * Python reads its indentation. Absent from a server older than script jobs, as
   * `then_prompt` is. */
  script?: string | null;
  /** Beside `script` only: when the script prints something, a turn is opened with this
   * prompt and what was printed. */
  then_prompt?: string | null;
  enabled: boolean;
  /** Skills attached in full to the conversation this schedule opens. */
  skills: string[];
  /** How long an approval in the conversation this schedule opens waits, in seconds; null
   * is the crew's setting. Set in `agent.yaml` only: the form has no box for it, and a row
   * sent back without it would drop it, so the form carries it through untouched. */
  approval_ttl_seconds?: number | null;
}

/** A slash command from a kit (`.agents/commands/*.md`): `/name` expands to its template. */
export interface CommandInfo {
  name: string;
  description: string;
  path: string;
}

/**
 * The subset of a profile where what the file says and what the crew runs differ.
 *
 * `delegates` is empty on the master that reaches everyone, and `schedules` omits the
 * consolidation job, which is generated from `memory_consolidate` rather than written
 * out. Both are what an edit has to start from.
 */
export interface DeclaredProfile {
  delegates: string[];
  /** Without `kind`, which is derived — the parser refuses a row that carries it back. */
  schedules: Omit<ScheduleInfo, "kind">[];
  /** The allow-list as the file writes it: empty for an agent that lists nothing and so
   * gets every tool its mode grants. */
  tools: string[];
}

/** The `telegram:` block of an agent's file. It names the variable holding the token. */
export interface TelegramBlock {
  token_env: string;
  chat_id: number;
  /** How long an approval in a conversation opened from this chat waits, in seconds. Set in
   * `agent.yaml` only; the form keeps it through every edit of the other two. */
  approval_ttl_seconds?: number;
}

/** Why a turn moved to its escalation route. Must match `LOOP` and `ERROR` in the
 * backend's `agent/escalation.py`. */
export type EscalationReason = "loop" | "error";

/** What an agent's scripts may call. `none` takes the script tool away from the agent (a
 * schedule's own script still runs, reading only); `read_only` lets a script call the tools
 * that read; `gated` adds the tools that change things, each call through the approval
 * gate. Must match the values `script_calls` takes in the backend's agent profile. */
export type ScriptCalls = "none" | "read_only" | "gated";
