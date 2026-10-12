import type { EscalationReason } from "./agents";

export type RunStatus = "running" | "awaiting_approval" | "done" | "halted" | "error";

/**
 * One call a script made on its own (`tool_script`). The model read none of these, only
 * what its script printed, so the step of the script is the one place they show. Must
 * match `NestedCall` in the backend's `tools/result.py`.
 */
export interface NestedToolCall {
  /** A tool's name, or what a script asked a model itself (`llm.classify`,
   *  `llm.summarise`), which is the name of no tool. */
  name: string;
  /** Shortened the way a step's own arguments are. */
  arguments: Record<string, unknown>;
  ok: boolean;
  /** The start of what came back to the script. */
  output: string;
  ms: number;
  /** Read only when `metered`: what the call paid a model, null when no price came with it. */
  cost_usd: number | null;
  metered: boolean;
  /** The call changed something and the approval gate let it through. Absent on a call
   * that changed nothing, and on every call kept from before the gate reached scripts. */
  gated?: boolean;
  /** Only on a task handed to another agent, and only above zero: what that agent spent
   * on it. It is the other conversation's money and no part of this run's spend, which
   * is why it rides apart from `cost_usd`. */
  child_spent_usd?: number;
}

export type RunStep =
  | {
      kind: "model";
      chars: number;
      // Written when the answer lands. A run read while its model is still answering
      // carries the call open, with none of them yet — see `isAnswered`.
      provider?: string | null;
      model?: string | null;
      cost_usd?: number | null;
      tool_calls?: string[];
      preview?: string;
      duration_ms: number | null;
      // Milliseconds from the request to the first chunk; absent on runs from before it was timed.
      first_token_ms?: number | null;
      // The whole prompt the call sent, and the part of it the provider served from its
      // cache. Null where the provider did not say.
      prompt_tokens?: number | null;
      cached_tokens?: number | null;
      /** Set once the model streamed reasoning before (or instead of) its answer. */
      thinking?: boolean;
    }
  | {
      kind: "tool";
      name: string;
      /**
       * Both absent when the result arrived without its call on this run — a turn that
       * resumes after an approval gets the result, while the call was recorded on the
       * run that paused. The server still opens a step for it, so the result is not lost.
       */
      tool_call_id?: string;
      /**
       * A mapping of argument name to value — except on runs recorded before the
       * store kept the shape, where the whole mapping was flattened to one string.
       * Those rows are still in the database, so reading one back has to cope.
       */
      arguments?: Record<string, unknown> | string;
      ok: boolean | null;
      output: string | null;
      /**
       * Present only when the output was too long for the agent's cap and had to be
       * brought under it. `kind` says how: "json" kept the structure, "summary" had a
       * model rewrite the middle, "cut" dropped the tail. `original_chars` is the size
       * before that happened, so a short answer built on a shortened tool output is not
       * mistaken for one built on the whole thing.
       */
      shaped?: { kind: "json" | "summary" | "cut"; original_chars: number };
      /**
       * What the tool paid a model: a picture or a scanned page read, a long output
       * summarised. Absent on a tool that asked no model; null when the provider put no
       * price on the call. The run's total already includes it.
       */
      cost_usd?: number | null;
      /**
       * Only on the step of a script that called something: each call it made, in order.
       * None of them is a step of its own. One that paid a model is in the run's total.
       */
      calls?: NestedToolCall[];
      /**
       * Only on the step of a script that ran: how many characters its calls handed back to
       * it, none of which the model read, and how many of what it printed went to the model.
       * Absent on a step written before the two were counted.
       */
      received_chars?: number;
      printed_chars?: number;
      duration_ms: number | null;
    }
  | {
      kind: "fallback";
      provider: string;
      model: string;
      error: string;
      duration_ms: number | null;
    }
  | {
      /** The turn was stuck and moved to the agent's escalation route for the rest of it.
       *  `error` is what its own routes said, and is absent on a move made for a loop. */
      kind: "escalation";
      reason: EscalationReason;
      provider: string;
      model: string;
      error?: string;
      duration_ms: number | null;
    }
  | {
      /** The run stopped to ask the person something. It stays open: the answer arrives
       *  on a new run, so this step has no end and its duration is never filled in. */
      kind: "question";
      question: string;
      duration_ms: number | null;
    }
  | {
      /** The agent saying what it is about to do, for whoever is watching. Written when
       *  the call is made rather than when it returns, so it appears alongside the work
       *  it describes. It has no `ok`, because a sentence cannot fail, and its duration
       *  is always zero, because saying it took no time. */
      kind: "note";
      text: string;
      duration_ms: number | null;
    }
  | {
      /** What a person handed the running turn — `/steer text` or a kit command — shown
       *  the way a note is: one line, done the instant it is said. */
      kind: "steer";
      text: string;
      duration_ms: number | null;
    };

/** A chat turn or job execution with its step timeline. */
export interface RunInfo {
  id: string;
  agent_id: string;
  conversation_id: string | null;
  source: string;
  title: string;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  spent_usd: number;
  unknown_cost_calls: number;
  summary: string;
  steps: RunStep[];
  /** True once the server has carried this run on after a restart cut it, which it does
   *  once. Absent from a server older than the bundle, which never does. */
  resumed?: boolean;
}
