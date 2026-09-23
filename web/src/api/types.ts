// Mirrors the JSON shapes produced by my_agent_crew.server.

export type Role = "system" | "user" | "assistant" | "tool";
export type ConversationStatus = "idle" | "awaiting_approval";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface StoredMessage {
  id: string;
  seq: number;
  role: Role;
  content: string;
  tool_calls: ToolCall[];
  tool_call_id: string | null;
  name: string | null;
  provider: string | null;
  model: string | null;
  cost_usd: number | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  agent_id: string;
  /** "" for the web UI, else the delivery channel, e.g. "telegram:<chat_id>". */
  channel: string;
  title: string;
  created_at: string;
  updated_at: string;
  autonomous: boolean;
  cost_cap_usd: number;
  skills: string[];
  spent_usd: number;
  unknown_cost_calls: number;
  status: ConversationStatus;
  over_budget: boolean;
  /** Short recap, written when the next conversation opens on the same channel. */
  summary: string;
  /** Tools the person chose to always allow in this conversation. */
  auto_approve: string[];
  /** The parent's tool call, when another agent delegated this conversation; "" otherwise. */
  parent_call_id: string;
}

export type ApprovalStatus = "pending" | "approved" | "denied" | "expired" | "answered";

/** "question" is the agent asking the person something; "tool" is a call waiting to run.
 *  They close by different routes, so a card that confuses them cannot be resolved. */
export type ApprovalKind = "tool" | "question";

export interface Approval {
  id: string;
  conversation_id: string;
  message_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: ApprovalStatus;
  created_at: string;
  /** When a pending request closes as expired if nobody answers; null on old rows. */
  expires_at: string | null;
  resolved_at: string | null;
  /** Rows written before questions existed have no kind; they are tools. */
  kind?: ApprovalKind;
  /** The choices a question offered, if any. Never set for a tool. */
  options?: string[];
  /** What the person replied, once a question is answered. */
  answer?: string | null;
}

/** One row of GET /api/approvals: the request plus the agent it belonged to. */
export interface ApprovalInfo extends Approval {
  agent_id: string;
}

export interface ConversationDetail extends Conversation {
  messages: StoredMessage[];
  pending_approval: Approval | null;
}

export interface ConversationPatch {
  title?: string;
  autonomous?: boolean;
  cost_cap_usd?: number;
  skills?: string[];
  auto_approve?: string[];
}

export type AgentEvent =
  | { type: "text_delta"; text: string }
  | {
      type: "assistant_message";
      message_id: string;
      content: string;
      tool_calls: ToolCall[];
      provider: string | null;
      model: string | null;
      cost_usd: number | null;
    }
  | { type: "tool_call"; tool_call_id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; tool_call_id: string; name: string; ok: boolean; output: string }
  | {
      type: "approval_required";
      approval_id: string;
      tool_call_id: string;
      name: string;
      arguments: Record<string, unknown>;
      reason: string;
      expires_at: string;
      kind?: ApprovalKind;
      options?: string[];
    }
  | { type: "done"; spent_usd: number; unknown_cost_calls: number }
  | { type: "halted"; reason: "budget" | "max_steps"; spent_usd: number }
  | { type: "error"; message: string }
  | { type: "route_fallback"; provider: string; model: string; error: string };

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
export type JobKind = "prompt" | "command" | "consolidate";

export interface ScheduleInfo {
  id: string;
  name: string;
  kind: JobKind;
  cron: string | null;
  every: string | null;
  prompt: string | null;
  command: string | null;
  enabled: boolean;
  /** Skills attached in full to the conversation this schedule opens. */
  skills: string[];
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
}

/** One agent profile as listed by GET /api/agents. */
export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  dir: string;
  workspace: string;
  routes: RouteInfo[];
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
  tools: string[];
  skills: string[];
  /** The one agent the person talks to; it does the work or delegates it. */
  is_master: boolean;
  /** False for an agent a kit defines: there is no manifest to patch, so a write to it
   * is refused and the editor shows where the definition actually lives instead. */
  editable: boolean;
  /** Set on the master when a Telegram bot also talks to it; the token stays on the server. */
  telegram: { token_env: string; chat_id: number } | null;
  /** What the agent's own file says, where that differs from what the crew computed.
   * An editor diffs against these: saving a computed value back would write the
   * computation into the file and freeze it there. */
  declared: DeclaredProfile;
  /** What the agent's kits (`.agents/`, `.claude/`, `.opencode/`) add: slash commands, the
   * number of tool hooks, and the kit directories they came from. */
  commands: CommandInfo[];
  hooks: number;
  kits: string[];
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
  /** A schedule only starts at boot. */
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
  workspace?: string | null;
  persona_files?: string[] | null;
  skills_dirs?: string[] | null;
  cost_cap_usd?: number | null;
  max_steps?: number | null;
  autonomous?: boolean | null;
  shell_ask_patterns?: string[] | null;
  tool_output_chars?: number | null;
  schedules?: unknown[] | null;
  telegram?: { token_env: string; chat_id: number } | null;
  memory_consolidate?: string | null;
  mode?: string;
  delegates?: string[] | null;
  tools?: string[] | null;
}

/**
 * What a write to an agent's profile produced: the agent as it is now, and the parts of
 * the change that only take effect at the next boot. An empty `restart_required` means
 * the edit is fully live already.
 */
export interface AgentSaved {
  profile: AgentInfo;
  restart_required: string[];
}

/** One tool in the crew's registry, with the agents whose toolbox actually holds it. */
export interface RegistryTool extends ToolInfo {
  agents: string[];
  /** Needs an API key: absent without one, even for an agent that names it. */
  optional: boolean;
}

/** An API key by the name of its environment variable. The value never leaves the server. */
export interface KeyStatus {
  name: string;
  present: boolean;
}

/** One agent's Telegram block. `configured` is that agent's own token variable. */
export interface TelegramConnection {
  agent_id: string;
  token_env: string;
  configured: boolean;
  /** Only the master's block opens a channel; anyone else's is read and skipped at boot. */
  ignored: boolean;
}

/** Everything the crew talks to on the outside, with no secret among it. */
export interface ConnectionsInfo {
  providers: { name: string; built: boolean }[];
  routes: RouteInfo[];
  vision_routes: RouteInfo[];
  keys: KeyStatus[];
  /** Search backends in priority order, best first. Never empty. */
  search_backends: string[];
  firecrawl_base_url: string;
  ollama_base_url?: string;
  telegram: TelegramConnection[];
}

/** Which card of the connections page an environment variable sits on. */
export type CredentialGroup = "model" | "search" | "telegram" | "other";

/**
 * One environment variable the connections page can set. A secret's value never comes
 * back from the server: only whether one is set and where from. A host address does.
 */
export interface CredentialInfo {
  name: string;
  group: CredentialGroup;
  secret: boolean;
  /** Must be an http(s) address. */
  url: boolean;
  present: boolean;
  /** "file": saved in the env file. "process": given to the server when it started, so
   * removing it from here is not possible and a restart may bring the old value back. */
  source: "file" | "process" | null;
  /** A free check can run now: there is a value, or a default to try. */
  checkable: boolean;
  /** Non-secrets only: the value in use and what applies when none is set. */
  value?: string;
  default?: string;
  /** Telegram only: the agents whose profile names this token. */
  agents?: string[];
}

export interface CredentialsInfo {
  /** Where the values are kept, for the person who wants to look at it themselves. */
  file: string;
  items: CredentialInfo[];
  /** Saved, but the crew could not be rebuilt from it: why, and a restart will apply it. */
  restart_required: string | null;
}

export interface CredentialCheck {
  ok: boolean;
  detail: string;
}

export interface SettingsInfo {
  home: string;
  workspace_dir: string;
  users_dir: string;
  routes: RouteInfo[];
  providers: string[];
  language: string;
  /** IANA zone from config (`""` = machine zone) and the zone actually in use. */
  timezone: string;
  zone: string;
  cost_cap_usd: number;
  max_steps: number;
  autonomous_default: boolean;
  keys: { openrouter: boolean; brave: boolean; tavily: boolean };
  tools: ToolInfo[];
  skills: SkillInfo[];
  agents: AgentInfo[];
}

/** One remembered fact about the person, shared by every agent. */
export interface FactInfo {
  name: string;
  description: string;
  type: FactType;
  written_by: string;
  source: string;
  updated: string;
  body: string;
}

export type FactType = "profile" | "preference" | "feedback" | "project" | "reference";

export const FACT_TYPES: FactType[] = [
  "profile",
  "preference",
  "feedback",
  "project",
  "reference",
];

export interface UserMemory {
  user_md: string;
  facts: FactInfo[];
  index_md: string;
}

/** A dated note beside one agent's MEMORY.md; the body is fetched on demand. */
export interface MemoryNote {
  /** The file name without `.md`: a date, sometimes with a suffix (`2026-09-19-1030`). */
  day: string;
  chars: number;
  /** The calendar day alone, shared by every note written that day. */
  date: string;
}

export interface AgentMemory {
  memory_md: string;
  notes: MemoryNote[];
  note_count: number;
}

export interface MemoryHit {
  scope: "user" | "agent";
  /** "" for a shared fact, else the agent whose file matched. */
  agent_id: string;
  file: string;
  text: string;
}

export type ProposalKind =
  | "user_fact"
  | "user_forget"
  | "agent_memory"
  | "agent_memory_rewrite"
  /** A whole batch of wiki pages, decided in one approval; the body is JSON. */
  | "wiki_compile";
export type ProposalStatus = "pending" | "approved" | "rejected";

/** A memory write a scheduled job asked for and cannot perform on its own. */
export interface MemoryProposal {
  id: string;
  agent_id: string;
  kind: ProposalKind;
  name: string;
  description: string;
  type: string;
  body: string;
  /** What a rewrite replaces, kept so one step back is always possible. */
  previous_body: string;
  status: ProposalStatus;
  source: string;
  created_at: string;
  resolved_at: string | null;
}

export interface FactBody {
  description: string;
  type: FactType;
  body: string;
}

/** A page as the list shows it: enough to choose one, without its body. */
export interface WikiPageSummary {
  slug: string;
  kind: string;
  title: string;
  status: string;
  updated: string;
  sources: string[];
  question_count: number;
}

export interface WikiPage extends Omit<WikiPageSummary, "question_count"> {
  body: string;
  questions: string[];
}

/** Only the fields being changed; what is left out keeps its current value. */
export interface WikiPageEdit {
  title?: string;
  body?: string;
  sources?: string[];
  questions?: string[];
  status?: string;
}

export interface WikiList {
  pages: WikiPageSummary[];
  kinds: string[];
  count: number;
}

export interface WikiProblem {
  slug: string;
  kind: string;
  detail: string;
}

export interface WikiReport {
  problems: WikiProblem[];
  questions: { slug: string; question: string }[];
}

export type * from "./activity-types";
