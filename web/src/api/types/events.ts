import type { EscalationReason } from "./agents";
import type { ApprovalKind, ConversationDetail, ToolCall } from "./conversation";
import type { NestedToolCall } from "./runs";

export type AgentEvent =
  | { type: "text_delta"; text: string }
  | { type: "thinking" }
  | { type: "model_call"; stage: "sent" | "first_token" }
  | {
      type: "assistant_message";
      message_id: string;
      content: string;
      tool_calls: ToolCall[];
      provider: string | null;
      model: string | null;
      cost_usd: number | null;
      prompt_tokens?: number | null;
      cached_tokens?: number | null;
    }
  | { type: "tool_call"; tool_call_id: string; name: string; arguments: Record<string, unknown> }
  | {
      type: "tool_result";
      tool_call_id: string;
      name: string;
      ok: boolean;
      output: string;
      /** What a script called on its own; empty for every other tool, and absent from a
       *  server older than the bundle. */
      calls?: NestedToolCall[];
      /** Counted for a script that ran, null for every other tool: the characters its calls
       *  handed back to it, and the characters it printed, counted before the agent's cap
       *  on a tool's result shortens what the model reads of them. */
      received_chars?: number | null;
      printed_chars?: number | null;
    }
  /** One call a script made on its own just ended, the `index`-th of the script whose own
   *  call is `tool_call_id`. Sent for a script the model called alone; the calls of one made
   *  beside other calls arrive with its result. */
  | { type: "nested_call"; tool_call_id: string; index: number; call: NestedToolCall }
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
  | { type: "halted"; reason: "budget" | "max_steps" | "loop" | "nested_calls"; spent_usd: number }
  | { type: "error"; message: string }
  | { type: "route_fallback"; provider: string; model: string; error: string }
  /** The turn was stuck and goes on with the agent's escalation route: it kept making the
   *  same call ("loop"), or none of its own routes answered ("error", with what they said). */
  | { type: "escalated"; reason: EscalationReason; provider: string; model: string; error: string }
  /** The message that started this stream found its conversation busy and waits instead:
   *  the only event this stream will ever carry. */
  | { type: "queued"; item_id: number; kind: "follow_up" | "steer"; position: number }
  /** A message sent while this turn ran was just handed to it, before its next model call. */
  | { type: "steer"; text: string; count: number }
  /** The canvas note stored with the message that started this turn, the first thing the
   *  stream of the tab that sent it carries. It names no message: the bubble is that tab's
   *  latest. */
  | { type: "user_context"; context: string }
  /** One more piece of the arguments of a canvas write the model is still writing. `index` is
   *  where the call stands in the answer, and `attempt` which try of this step's answer it is:
   *  a step counts its tries from nothing again. An empty `name` only says the answer was
   *  started over, so what the try before had written is not coming. */
  | { type: "tool_call_delta"; index: number; name: string; chunk: string; attempt: number }
  /** For a tab that has not read the turn from its first event — it opened late, or fell too
   *  far behind: the conversation as it is stored now, to rebuild the thread from. What the
   *  turn is writing follows as ordinary events. `running` is false when the turn ended within
   *  the events this stands in for, so nothing more is coming. */
  | { type: "watching"; running: boolean; detail: ConversationDetail };
