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
  /** The note a user message was stored with when the person's canvas came along: the passage
   *  they selected, or what they changed since the agent last saw it. Absent or empty when
   *  there was none. On the result of a script it is what the script called and its two
   *  measures, as JSON (`lib/nested-calls.ts`); the model was sent none of it. */
  context?: string;
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
  /** The conversation this one was forked from, when it is a fork; "" otherwise. Optional
   *  so every existing fixture that predates forking stays a valid `Conversation`. */
  forked_from?: string;
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
  /** Which ask pattern stopped the call, or empty. Only on a conversation's open request:
   *  the server works it out again on each read rather than storing it. */
  reason?: string;
}

/** One row of GET /api/approvals: the request plus the agent it belonged to. */
export interface ApprovalInfo extends Approval {
  agent_id: string;
}

/** A message that found its conversation busy: a follow-up waits for the turn to end, a
 *  steer is handed to it before its next model call. */
export interface QueuedMessage {
  /** The server's own integer id, not a string like the other ids in this file. */
  id: number;
  kind: "follow_up" | "steer";
  text: string;
}

/** What `POST /conversations/{id}/stop` answers: the texts it took back out of the queue,
 *  and whether it also stopped a turn the queue runs for this conversation. */
export interface StopResult {
  cleared: QueuedMessage[];
  cancelled: boolean;
}

export interface ConversationDetail extends Conversation {
  messages: StoredMessage[];
  pending_approval: Approval | null;
  /** Read, not taken: what still waits for the running turn. Absent on an old server. */
  queued?: QueuedMessage[];
}

/** What `POST /conversations/{id}/fork` answers: the new conversation, plus the cut
 *  message's own text so the composer can open pre-filled with it. */
export interface ForkResult extends Conversation {
  draft: string;
}

export interface ConversationPatch {
  title?: string;
  autonomous?: boolean;
  cost_cap_usd?: number;
  skills?: string[];
  auto_approve?: string[];
}
