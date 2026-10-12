import type { ScriptWork } from "../lib/nested-calls";
import type {
  AgentEvent,
  Approval,
  ApprovalKind,
  ConversationDetail,
  EscalationReason,
  QueuedMessage,
} from "../api/types";
import type { WritingPreview } from "./writing-previews";

/** `stopped`: the turn ended before the call answered — stopped here, cut off, or left
 *  behind by a run that is no longer going. Nothing is running it any more. */
export type ToolStatus = "running" | "done" | "failed" | "awaiting" | "denied" | "stopped";

export type ThreadItem =
  /** `context`: the canvas note the message was stored with, when the person's canvas came along. */
  | { kind: "user"; id: string; text: string; context?: string }
  | { kind: "assistant"; id: string; text: string; model: string | null }
  /** A script's card also holds what the script called on its own and its two measures:
   *  heard call by call while it runs, then as its result says them, live or stored. */
  | ({
      kind: "tool";
      id: string;
      name: string;
      arguments: Record<string, unknown>;
      output: string | null;
      status: ToolStatus;
    } & ScriptWork)
  /** The agent saying what it is about to do. It arrives as a tool call but is not shown
   *  as one: it has no output to wait for and no status to resolve, so a tool card would
   *  sit spinning next to a sentence that had already finished being said. */
  | { kind: "note"; id: string; text: string };

export interface PendingApproval {
  approvalId: string;
  toolCallId: string;
  name: string;
  arguments: Record<string, unknown>;
  /** Which ask pattern stopped the call, for a command that pauses even when the
   *  conversation is autonomous. */
  reason?: string;
  /** When the request closes as refused if nobody answers. */
  expiresAt?: string;
  /** A question is answered, not approved. The two close by different routes, so a card
   *  that shows the wrong one gives the person only buttons the server refuses. */
  kind: ApprovalKind;
  /** The choices the question offered. Empty means any words will do. */
  options: string[];
}

/** A stored pending request in the shape the cards take. Old rows carry no kind: tools. */
export function pendingFromApproval(a: Approval): PendingApproval {
  const pending: PendingApproval = {
    approvalId: a.id,
    toolCallId: a.tool_call_id,
    name: a.tool_name,
    arguments: a.arguments,
    kind: a.kind ?? "tool",
    options: a.options ?? [],
  };
  if (a.expires_at) pending.expiresAt = a.expires_at;
  if (a.reason) pending.reason = a.reason;
  return pending;
}

/** What the agent asked, for a question. Empty for a tool call. */
export function questionText(pending: PendingApproval): string {
  const asked = pending.arguments.question;
  return typeof asked === "string" ? asked : "";
}

export interface ThreadState {
  /** The conversation whose stored thread is on screen: none from the moment one is opened
   *  until what the server holds of it has landed, by a load or with a turn read along. */
  conversationId: string | null;
  items: ThreadItem[];
  streaming: string | null;
  /** The model is thinking before its first word: a long silence that is not a hang. */
  thinking: boolean;
  busy: boolean;
  pending: PendingApproval | null;
  spentUsd: number;
  unknownCostCalls: number;
  /** `reason` is set on "escalated" only: why the turn moved, beside the route it moved to.
   *  `ofTurn` is set on an "error" the turn itself ended in. One without it is of a request
   *  this tab made, a load or a send, that failed. */
  notice: {
    kind: "error" | "halted" | "fallback" | "escalated" | "stopped" | "handled" | "elsewhere";
    text: string;
    reason?: EscalationReason;
    ofTurn?: true;
  } | null;
  /** Messages that found this conversation busy and wait: a chip each, confirmation only. */
  waiting: QueuedMessage[];
  /** The canvases the model is writing in the turn that is going. None outlives its turn. */
  previews: WritingPreview[];
  /** The last key a preview was given. It outlives the thread, so no key comes twice in a tab. */
  previewSeq: number;
  /** The person put one of them away: none comes up by itself for the rest of the turn. */
  previewsMuted: boolean;
}

export type ThreadAction =
  /** Another conversation was opened: nothing of the one before carries over. */
  | { type: "opened" }
  | { type: "loaded"; detail: ConversationDetail }
  | { type: "user_sent"; text: string }
  /** The server never took the message `user_sent` showed — it refused it, or the request
   *  never got through — so the bubble goes, and the words go back where they were typed
   *  rather than showing twice. */
  | { type: "user_unsent"; text: string }
  | { type: "turn_started" }
  | { type: "turn_finished" }
  /** The person pressed Stop: whatever the stream still had to say is not coming. */
  | { type: "turn_stopped" }
  /** No run is going for this conversation, here or elsewhere, so nothing is running. */
  | { type: "settled" }
  | { type: "failed"; message: string }
  /** A decision met a request already closed elsewhere. Nothing failed, and the run that
   *  other channel resumed may still be carrying out its calls: a note, not a settle. */
  | { type: "handled" }
  /** A message just found this conversation busy and waits: add its chip. */
  | { type: "queued"; item: QueuedMessage }
  /** Stop took every waiting message back out of the queue; the server has confirmed it. */
  | { type: "queue_cleared" }
  /** Stop reached a run this tab cannot touch — another channel's, a job's, another tab's. */
  | { type: "elsewhere" }
  /** A busy-send's own POST failed — the queue is full, or the text itself was refused.
   *  Unlike `failed`, this says nothing about the turn already running: that stream's
   *  `busy`, `streaming` and `items` are untouched, since the queueing attempt beside it
   *  is the only thing that went wrong. */
  | { type: "queue_failed"; message: string }
  /** The person put away a canvas being written. */
  | { type: "previews_muted" }
  | { type: "event"; event: AgentEvent };

export const emptyThread: ThreadState = {
  conversationId: null,
  items: [],
  streaming: null,
  thinking: false,
  busy: false,
  pending: null,
  spentUsd: 0,
  unknownCostCalls: 0,
  notice: null,
  waiting: [],
  previews: [],
  previewSeq: 0,
  previewsMuted: false,
};
