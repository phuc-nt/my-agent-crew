import { storedWork } from "../lib/nested-calls";
import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import { storedStatus } from "../lib/tool-reply";
import type { StoredMessage, ToolCall } from "../api/types";
import type { ThreadItem, ThreadState, ToolStatus } from "./thread-state";

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
        const status = storedStatus(call.name, m.content);
        items[at] = { ...call, output: m.content, status, ...storedWork(m.context) };
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
export function threadItemFor(call: ToolCall): ThreadItem {
  if (call.name === PROGRESS_NOTE_TOOL) {
    return { kind: "note", id: call.id, text: noteText(call.arguments) };
  }
  return toolItem(call, "running");
}

/** Without the bubble `user_sent` added for `text`, while it is still the last thing in the
 *  thread: a stored message with the same words is the server's, and anything after the
 *  bubble means the server has already answered. */
export function withoutLocalBubble(items: ThreadItem[], text: string): ThreadItem[] {
  const last = items[items.length - 1];
  return last?.kind === "user" && last.id.startsWith("local-") && last.text === text ? items.slice(0, -1) : items;
}

/** The latest user message with `context` as its canvas note, left as it was and in its place:
 *  the bubble was drawn before the server stored the message, and forking finds it by position. */
export function withContext(items: ThreadItem[], context: string): ThreadItem[] {
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
export function settle(state: ThreadState): ThreadItem[] {
  if (state.pending || !state.items.some((it) => it.kind === "tool" && it.status === "running")) {
    return state.items;
  }
  return state.items.map((it) => (it.kind === "tool" && it.status === "running" ? { ...it, status: "stopped" } : it));
}

export function updateTool(
  items: ThreadItem[],
  toolCallId: string,
  patch: Partial<Extract<ThreadItem, { kind: "tool" }>>,
): ThreadItem[] {
  return items.map((it) => (it.kind === "tool" && it.id === toolCallId ? { ...it, ...patch } : it));
}
