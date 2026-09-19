import type { AgentEvent, ConversationDetail, StoredMessage, ToolCall } from "../api/types";

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
    };

export interface PendingApproval {
  approvalId: string;
  toolCallId: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ThreadState {
  items: ThreadItem[];
  streaming: string | null;
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
        pending = { approvalId: a.id, toolCallId: a.tool_call_id, name: a.tool_name, arguments: a.arguments };
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
      return { ...state, busy: false, streaming: null };
    case "failed":
      return { ...state, busy: false, streaming: null, notice: { kind: "error", text: action.message } };
    case "event":
      return applyEvent(state, action.event);
  }
}

function applyEvent(state: ThreadState, e: AgentEvent): ThreadState {
  switch (e.type) {
    case "text_delta":
      return { ...state, streaming: (state.streaming ?? "") + e.text };
    case "assistant_message": {
      const items = [...state.items];
      if (e.content) items.push({ kind: "assistant", id: e.message_id, text: e.content, model: e.model });
      for (const call of e.tool_calls) items.push(toolItem(call, "running"));
      return { ...state, items, streaming: null };
    }
    case "tool_call":
      return state.items.some((it) => it.kind === "tool" && it.id === e.tool_call_id)
        ? { ...state, items: updateTool(state.items, e.tool_call_id, { status: "running" }) }
        : { ...state, items: [...state.items, toolItem({ id: e.tool_call_id, name: e.name, arguments: e.arguments }, "running")] };
    case "tool_result": {
      const denied = e.output.startsWith(DENIED_MARKER);
      const status: ToolStatus = denied ? "denied" : e.ok ? "done" : "failed";
      return { ...state, items: updateTool(state.items, e.tool_call_id, { output: e.output, status }), pending: null };
    }
    case "approval_required":
      return {
        ...state,
        busy: false,
        pending: { approvalId: e.approval_id, toolCallId: e.tool_call_id, name: e.name, arguments: e.arguments },
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
