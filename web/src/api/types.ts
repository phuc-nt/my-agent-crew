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

export type ApprovalStatus = "pending" | "approved" | "denied" | "expired";

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
  persona_files: string[];
  schedules: ScheduleInfo[];
  /** "assistant" chats; "work" carries the coding tools and can hand off to `delegates`. */
  mode: string;
  /** Agents this one can hand work to; for the master that is everyone else. */
  delegates: string[];
  tools: string[];
  skills: string[];
  /** The one agent the person talks to; it does the work or delegates it. */
  is_master: boolean;
  /** Set when a Telegram bot also talks to this agent; the token stays on the server. */
  telegram: { token_env: string; chat_id: number } | null;
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
  /** A schedule or a Telegram bot only starts at boot. */
  needs_restart: boolean;
}

export interface AgentDetail extends Omit<AgentInfo, "tools" | "skills"> {
  tools: ToolInfo[];
  skills: SkillInfo[];
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

export type ProposalKind = "user_fact" | "user_forget" | "agent_memory" | "agent_memory_rewrite";
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

export type * from "./activity-types";
