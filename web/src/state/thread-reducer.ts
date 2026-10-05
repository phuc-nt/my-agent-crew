import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import { isDenied, storedStatus } from "../lib/tool-reply";
import type {
  AgentEvent,
  Approval,
  ApprovalKind,
  ConversationDetail,
  QueuedMessage,
  StoredMessage,
  ToolCall,
} from "../api/types";
import { applyDelta, betweenStreams, bindCalls, noPreviews, type WritingPreview } from "./writing-previews";

/** `stopped`: the turn ended before the call answered — stopped here, cut off, or left
 *  behind by a run that is no longer going. Nothing is running it any more. */
export type ToolStatus = "running" | "done" | "failed" | "awaiting" | "denied" | "stopped";

export type ThreadItem =
  /** `context`: the canvas note the message was stored with, when the person's canvas came along. */
  | { kind: "user"; id: string; text: string; context?: string }
  | { kind: "assistant"; id: string; text: string; model: string | null }
  | {
      kind: "tool";
      id: string;
      name: string;
      arguments: Record<string, unknown>;
      output: string | null;
      status: ToolStatus;
    }
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
  items: ThreadItem[];
  streaming: string | null;
  /** The model is thinking before its first word: a long silence that is not a hang. */
  thinking: boolean;
  busy: boolean;
  pending: PendingApproval | null;
  spentUsd: number;
  unknownCostCalls: number;
  notice: { kind: "error" | "halted" | "fallback" | "stopped" | "handled" | "elsewhere"; text: string } | null;
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

export function itemsFromMessages(messages: StoredMessage[]): ThreadItem[] {
  const items: ThreadItem[] = [];
  const toolIndex = new Map<string, number>();
  for (const m of messages) {
    if (m.role === "user") {
      items.push({ kind: "user", id: m.id, text: m.content, ...(m.context ? { context: m.context } : {}) });
    }
    if (m.role === "assistant") {
      if (m.content) items.push({ kind: "assistant", id: m.id, text: m.content, model: m.model });
      for (const call of m.tool_calls) {
        toolIndex.set(call.id, items.length);
        items.push(toolItem(call, "running"));
      }
    }
    if (m.role === "tool" && m.tool_call_id !== null) {
      const at = toolIndex.get(m.tool_call_id);
      if (at !== undefined) {
        const call = items[at] as ThreadItem & { kind: "tool" };
        items[at] = { ...call, output: m.content, status: storedStatus(call.name, m.content) };
      }
    }
  }
  return items;
}

function toolItem(call: ToolCall, status: ToolStatus): ThreadItem {
  return { kind: "tool", id: call.id, name: call.name, arguments: call.arguments, output: null, status };
}

/**
 * The thread item one tool call becomes.
 *
 * Every call but one becomes a tool card. A progress note becomes a note, because it has
 * already happened by the time it is seen: there is no output coming and no status to
 * settle, so a tool card would spin beside a finished sentence for the rest of the turn.
 */
function threadItemFor(call: ToolCall): ThreadItem {
  if (call.name === PROGRESS_NOTE_TOOL) {
    return { kind: "note", id: call.id, text: noteText(call.arguments) };
  }
  return toolItem(call, "running");
}

/** Without the bubble `user_sent` added for `text`, while it is still the last thing in the
 *  thread: a stored message with the same words is the server's, and anything after the
 *  bubble means the server has already answered. */
function withoutLocalBubble(items: ThreadItem[], text: string): ThreadItem[] {
  const last = items[items.length - 1];
  return last?.kind === "user" && last.id.startsWith("local-") && last.text === text ? items.slice(0, -1) : items;
}

/** The latest user message with `context` as its canvas note, left as it was and in its place:
 *  the bubble was drawn before the server stored the message, and forking finds it by position. */
function withContext(items: ThreadItem[], context: string): ThreadItem[] {
  for (let at = items.length - 1; at >= 0; at--) {
    const item = items[at];
    if (item.kind === "user") return items.map((it, i) => (i === at ? { ...item, context } : it));
  }
  return items;
}

/**
 * Calls that never answered, once no turn is going to answer them. A turn paused on a
 * person is not over: the calls queued behind the one waiting still run once it is
 * decided, so those keep their state.
 */
function settle(state: ThreadState): ThreadItem[] {
  if (state.pending || !state.items.some((it) => it.kind === "tool" && it.status === "running")) {
    return state.items;
  }
  return state.items.map((it) => (it.kind === "tool" && it.status === "running" ? { ...it, status: "stopped" } : it));
}

function updateTool(
  items: ThreadItem[],
  toolCallId: string,
  patch: Partial<Extract<ThreadItem, { kind: "tool" }>>,
): ThreadItem[] {
  return items.map((it) => (it.kind === "tool" && it.id === toolCallId ? { ...it, ...patch } : it));
}

export function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "opened":
      return { ...emptyThread, previewSeq: state.previewSeq };
    case "loaded": {
      const d = action.detail;
      let items = itemsFromMessages(d.messages);
      let pending: PendingApproval | null = null;
      if (d.pending_approval) {
        pending = pendingFromApproval(d.pending_approval);
        items = updateTool(items, pending.toolCallId, { status: "awaiting" });
      }
      // The note that a decision met a request already settled answers the person's own
      // click, and the loads that follow it — the run it resumed, the stream coming back —
      // do not answer it again. A load that brings a new request has moved past it.
      const handled = state.notice?.kind === "handled" && pending === null ? state.notice : null;
      return {
        ...emptyThread,
        items,
        pending,
        spentUsd: d.spent_usd,
        unknownCostCalls: d.unknown_cost_calls,
        notice: handled,
        waiting: d.queued ?? [],
        previewSeq: state.previewSeq,
        ...betweenStreams(state, pending),
      };
    }
    case "user_sent":
      return {
        ...state,
        items: [...state.items, { kind: "user", id: `local-${state.items.length}`, text: action.text }],
        notice: null,
      };
    case "user_unsent":
      return { ...state, items: withoutLocalBubble(state.items, action.text) };
    case "turn_started":
      return { ...state, busy: true, streaming: null, notice: null, ...betweenStreams(state) };
    case "turn_finished":
      return { ...state, busy: false, streaming: null, thinking: false, items: settle(state), ...betweenStreams(state) };
    case "turn_stopped": {
      // Stopping cuts the stream, and the server gives up the turn with it: a decision
      // already sent is spent, so its call stops with the rest instead of asking again.
      const cut = { ...state, pending: null };
      const items = settle(cut).map((it) =>
        it.kind === "tool" && it.status === "awaiting" ? { ...it, status: "stopped" as const } : it,
      );
      const notice = { kind: "stopped" as const, text: "" };
      return { ...cut, items, busy: false, streaming: null, thinking: false, notice, ...noPreviews };
    }
    case "settled": {
      if (state.busy) return state;
      const items = settle(state);
      return items === state.items ? state : { ...state, items };
    }
    case "failed":
      return {
        ...state,
        busy: false,
        streaming: null,
        thinking: false,
        items: settle(state),
        notice: { kind: "error", text: action.message },
        ...betweenStreams(state),
      };
    case "handled":
      // A turn begun since has the thread: a note about the earlier decision would be stale.
      return state.busy ? state : { ...state, notice: { kind: "handled", text: "" } };
    case "queued": {
      // A local bubble for this text was added optimistically by `user_sent` on the plain
      // send path; drop it once the server's own chip stands for it. A busy-send POST never
      // adds that bubble, so there is nothing to drop on that path — only to add here.
      return {
        ...state,
        items: withoutLocalBubble(state.items, action.item.text),
        waiting: [...state.waiting, action.item],
      };
    }
    case "queue_cleared":
      return { ...state, waiting: [] };
    case "elsewhere":
      return { ...state, notice: { kind: "elsewhere", text: "" } };
    case "queue_failed":
      return { ...state, notice: { kind: "error", text: action.message } };
    case "previews_muted":
      return { ...state, previewsMuted: true };
    case "event":
      return applyEvent(state, action.event);
  }
}

function applyEvent(given: ThreadState, e: AgentEvent): ThreadState {
  // Whatever the model does next — words, a tool call, an end — ends its thinking. A
  // model_call marker is not something the model does; it only times the call. A piece of a
  // canvas being written says nothing of it either way: some models think while they write.
  const keeps = e.type === "thinking" || e.type === "model_call" || e.type === "tool_call_delta";
  const state = keeps ? given : { ...given, thinking: false };
  switch (e.type) {
    case "thinking":
      return { ...state, thinking: true };
    case "model_call":
      return state;
    case "text_delta":
      return { ...state, streaming: (state.streaming ?? "") + e.text };
    case "tool_call_delta": {
      const { previews, seq } = applyDelta(state.previews, state.previewSeq, e);
      return { ...state, previews, previewSeq: seq };
    }
    case "assistant_message": {
      const items = [...state.items];
      if (e.content) items.push({ kind: "assistant", id: e.message_id, text: e.content, model: e.model });
      for (const call of e.tool_calls) items.push(threadItemFor(call));
      return { ...state, items, streaming: null, previews: bindCalls(state.previews, e.tool_calls) };
    }
    case "tool_call":
      return state.items.some((it) => it.id === e.tool_call_id)
        ? { ...state, items: updateTool(state.items, e.tool_call_id, { status: "running" }) }
        : {
            ...state,
            items: [
              ...state.items,
              threadItemFor({ id: e.tool_call_id, name: e.name, arguments: e.arguments }),
            ],
          };
    case "tool_result": {
      // A note has no result to show: it was complete when it was written. Falling
      // through would look for a tool item that is not there and drop `pending`.
      if (e.name === PROGRESS_NOTE_TOOL) return state;
      const status: ToolStatus = isDenied(e.output) ? "denied" : e.ok ? "done" : "failed";
      return { ...state, items: updateTool(state.items, e.tool_call_id, { output: e.output, status }), pending: null };
    }
    case "approval_required":
      return {
        ...state,
        busy: false,
        pending: {
          approvalId: e.approval_id,
          toolCallId: e.tool_call_id,
          name: e.name,
          arguments: e.arguments,
          reason: e.reason,
          kind: e.kind ?? "tool",
          options: e.options ?? [],
          ...(e.expires_at ? { expiresAt: e.expires_at } : {}),
        },
        items: updateTool(state.items, e.tool_call_id, { status: "awaiting" }),
        previews: [],
      };
    case "done": {
      const { spent_usd: spentUsd, unknown_cost_calls: unknownCostCalls } = e;
      return { ...state, busy: false, streaming: null, spentUsd, unknownCostCalls, ...noPreviews };
    }
    case "halted": {
      const notice = { kind: "halted" as const, text: e.reason };
      return { ...state, busy: false, streaming: null, spentUsd: e.spent_usd, notice, ...noPreviews };
    }
    case "error":
      return { ...state, busy: false, streaming: null, notice: { kind: "error", text: e.message }, ...noPreviews };
    case "route_fallback":
      return { ...state, notice: { kind: "fallback", text: `${e.provider}:${e.model} — ${e.error}` } };
    // The hook that sent the message intercepts its own `queued` event before the reducer
    // ever sees it — only the hook knows which text was just sent. Reaching here means the
    // event arrived on a stream nothing is watching for it; nothing to do.
    case "queued":
      return state;
    case "user_context":
      return { ...state, items: withContext(state.items, e.context) };
    case "steer": {
      const items = [...state.items, { kind: "user" as const, id: `local-${state.items.length}`, text: e.text }];
      let left = e.count;
      const waiting: QueuedMessage[] = [];
      // Oldest first, drop up to `count` steer chips; a follow_up chip is never touched.
      for (const item of state.waiting) {
        if (item.kind === "steer" && left > 0) {
          left -= 1;
          continue;
        }
        waiting.push(item);
      }
      return { ...state, items, waiting };
    }
    // A server newer than this bundle sends kinds of event added since. Nothing here knows what
    // one means, so nothing changes, the thinking included: the very state given goes back.
    default:
      e satisfies never; // every kind in the union has a case above
      return given;
  }
}
