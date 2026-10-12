import { withNested, workOf } from "../lib/nested-calls";
import { PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import { isDenied } from "../lib/tool-reply";
import type { AgentEvent, QueuedMessage } from "../api/types";
import { watchingFrom } from "./thread-detail";
import { threadItemFor, updateTool, withContext } from "./thread-items";
import type { ThreadItem, ThreadState, ToolStatus } from "./thread-state";
import { applyDelta, bindCalls, noPreviews } from "./writing-previews";

export function applyEvent(given: ThreadState, e: AgentEvent): ThreadState {
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
      const patch = { output: e.output, status, ...workOf(e) };
      return { ...state, items: updateTool(state.items, e.tool_call_id, patch), pending: null };
    }
    // One call a script made, listed on the script's card while the script still runs. A
    // tab that joined the turn late lists the calls from where it joined; the result then
    // names them all. A script with no card here changes nothing.
    case "nested_call": {
      const listed = (it: ThreadItem): ThreadItem =>
        it.kind === "tool" && it.id === e.tool_call_id
          ? { ...it, calls: withNested(it.calls, e.index, e.call).calls }
          : it;
      return { ...state, items: state.items.map(listed) };
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
      return { ...state, busy: false, streaming: null, notice: { kind: "error", text: e.message, ofTurn: true }, ...noPreviews };
    case "route_fallback":
      return { ...state, notice: { kind: "fallback", text: `${e.provider}:${e.model} — ${e.error}` } };
    // The turn goes on, so nothing else changes: the notice says which model the rest of it
    // is answered by, and takes the place of the fallback notice the failed routes left.
    case "escalated":
      return { ...state, notice: { kind: "escalated", text: `${e.provider}:${e.model}`, reason: e.reason } };
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
    case "watching":
      return watchingFrom(given, e);
    // A server newer than this bundle sends kinds of event added since. Nothing here knows what
    // one means, so nothing changes, the thinking included: the very state given goes back.
    default:
      e satisfies never; // every kind in the union has a case above
      return given;
  }
}
