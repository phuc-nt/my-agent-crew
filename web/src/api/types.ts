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
}

export interface Approval {
  id: string;
  conversation_id: string;
  message_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "pending" | "approved" | "denied";
  created_at: string;
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

export interface ScheduleInfo {
  id: string;
  name: string;
  cron: string | null;
  every: string | null;
  prompt: string | null;
  command: string | null;
  enabled: boolean;
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
  tools: string[];
  skills: string[];
}

export interface AgentDetail extends Omit<AgentInfo, "tools" | "skills"> {
  tools: ToolInfo[];
  skills: SkillInfo[];
}

export interface SettingsInfo {
  home: string;
  workspace_dir: string;
  routes: RouteInfo[];
  providers: string[];
  language: string;
  cost_cap_usd: number;
  max_steps: number;
  autonomous_default: boolean;
  keys: { openrouter: boolean; brave: boolean; tavily: boolean };
  tools: ToolInfo[];
  skills: SkillInfo[];
  agents: AgentInfo[];
}

export type * from "./activity-types";
