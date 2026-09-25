import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import type { AgentEvent, ApprovalKind, ConversationDetail, StoredMessage, ToolCall } from "../api/types";

export type ToolStatus = "running" | "done" | "failed" | "awaiting" | "denied";

export type ThreadItem =
  | { kind: "user"; id: string; text: string }
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
  /** Why an autonomous conversation stopped for this call; only on the live event. */
  reason?: string;
  /** When the request closes as refused if nobody answers. */
  expiresAt?: string;
  /** A question is answered, not approved. The two close by different routes, so a card
   *  that shows the wrong one gives the person only buttons the server refuses. */
  kind: ApprovalKind;
  /** The choices the question offered. Empty means any words will do. */
  options: string[];
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
  notice: { kind: "error" | "halted" | "fallback"; text: string } | null;
}

export type ThreadAction =
  | { type: "loaded"; detail: ConversationDetail }
  | { type: "user_sent"; text: string }
  | { type: "turn_started" }
  | { type: "turn_finished" }
  | { type: "failed"; message: string }
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
};

const DENIED_MARKER = "Người dùng đã TỪ CHỐI";

export function itemsFromMessages(messages: StoredMessage[]): ThreadItem[] {
  const items: ThreadItem[] = [];
  const toolIndex = new Map<string, number>();
  for (const m of messages) {
    if (m.role === "user") items.push({ kind: "user", id: m.id, text: m.content });
    if (m.role === "assistant") {
      if (m.content) items.push({ kind: "assistant", id: m.id, text: m.content, model: m.model });
      for (const call of m.tool_calls) {
        toolIndex.set(call.id, items.length);
        items.push(toolItem(call, "running"));
      }
    }
    if (m.role === "tool" && m.tool_call_id !== null) {
      const at = toolIndex.get(m.tool_call_id);
      const denied = m.content.startsWith(DENIED_MARKER);
      if (at !== undefined) {
        items[at] = { ...(items[at] as ThreadItem & { kind: "tool" }), output: m.content, status: denied ? "denied" : "done" };
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

function updateTool(
  items: ThreadItem[],
  toolCallId: string,
  patch: Partial<Extract<ThreadItem, { kind: "tool" }>>,
): ThreadItem[] {
  return items.map((it) => (it.kind === "tool" && it.id === toolCallId ? { ...it, ...patch } : it));
}

export function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "loaded": {
      const d = action.detail;
      let items = itemsFromMessages(d.messages);
      let pending: PendingApproval | null = null;
      if (d.pending_approval) {
        const a = d.pending_approval;
        pending = {
          approvalId: a.id,
          toolCallId: a.tool_call_id,
          name: a.tool_name,
          arguments: a.arguments,
          kind: a.kind ?? "tool",
          options: a.options ?? [],
        };
        if (a.expires_at) pending.expiresAt = a.expires_at;
        items = updateTool(items, a.tool_call_id, { status: "awaiting" });
      }
      return {
        ...emptyThread,
        items,
        pending,
        spentUsd: d.spent_usd,
        unknownCostCalls: d.unknown_cost_calls,
      };
    }
    case "user_sent":
      return {
        ...state,
        items: [...state.items, { kind: "user", id: `local-${state.items.length}`, text: action.text }],
        notice: null,
      };
    case "turn_started":
      return { ...state, busy: true, streaming: null, notice: null };
    case "turn_finished":
      return { ...state, busy: false, streaming: null, thinking: false };
    case "failed":
      return { ...state, busy: false, streaming: null, thinking: false, notice: { kind: "error", text: action.message } };
    case "event":
      // Whatever the model does next — words, a tool call, an end — ends its thinking.
      return applyEvent(action.event.type === "thinking" ? state : { ...state, thinking: false }, action.event);
  }
}

function applyEvent(state: ThreadState, e: AgentEvent): ThreadState {
  switch (e.type) {
    case "thinking":
      return { ...state, thinking: true };
    case "text_delta":
      return { ...state, streaming: (state.streaming ?? "") + e.text };
    case "assistant_message": {
      const items = [...state.items];
      if (e.content) items.push({ kind: "assistant", id: e.message_id, text: e.content, model: e.model });
      for (const call of e.tool_calls) items.push(threadItemFor(call));
      return { ...state, items, streaming: null };
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
      const denied = e.output.startsWith(DENIED_MARKER);
      const status: ToolStatus = denied ? "denied" : e.ok ? "done" : "failed";
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
      };
    case "done":
      return { ...state, busy: false, streaming: null, spentUsd: e.spent_usd, unknownCostCalls: e.unknown_cost_calls };
    case "halted":
      return { ...state, busy: false, streaming: null, spentUsd: e.spent_usd, notice: { kind: "halted", text: e.reason } };
    case "error":
      return { ...state, busy: false, streaming: null, notice: { kind: "error", text: e.message } };
    case "route_fallback":
      return { ...state, notice: { kind: "fallback", text: `${e.provider}:${e.model} — ${e.error}` } };
  }
}
