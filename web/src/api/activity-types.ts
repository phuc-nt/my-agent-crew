// Shapes of the activity stream, the job list and the cost summary (GET /api/activity/*, /jobs, /stats).
import type { AgentEvent, Conversation, ScheduleInfo } from "./types";

export type RunStatus = "running" | "awaiting_approval" | "done" | "halted" | "error";

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
}

/** The payloads that describe runs, and so change the activity state. */
export type RunPayload =
  | { type: "snapshot"; runs: RunInfo[] }
  | { type: "run"; run: RunInfo }
  | {
      type: "event";
      run_id: string;
      agent_id: string;
      conversation_id: string | null;
      status: RunStatus;
      event: AgentEvent;
    };

/** Everything the stream carries. Payloads outside `RunPayload` are routed to their
 *  own listener before the activity reducer sees them. */
export type ActivityPayload =
  | RunPayload
  // A conversation changed outside a run — so far only its title, written in the
  // background once the first message named it.
  | { type: "conversation"; conversation: Conversation };

export interface JobInfo extends ScheduleInfo {
  schedule_id: string;
  agent_id: string;
  next_run: string | null;
  last_run: RunInfo | null;
  running: boolean;
  /** Switched off at runtime; `enabled` is the effective value (profile AND not paused). */
  paused: boolean;
}

/** Calls, tokens and cost added up from the message log for one bucket. */
export interface UsageTotals {
  calls: number;
  cost_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  /** The part of `prompt_tokens` the provider served from its prompt cache. */
  cached_tokens: number;
  unknown_cost_calls: number;
}

export interface DayUsage extends UsageTotals {
  /** Calendar day in the server's configured zone (the owner's, UTC+7), `YYYY-MM-DD`. */
  day: string;
}

export interface ModelUsage extends UsageTotals {
  /** `provider:model`. */
  model: string;
}

export interface PurposeUsage extends UsageTotals {
  /** `chat` for the turns' own calls; otherwise what a call beside them was for:
   *  `title`, `session_summary`, `tool_summary`, `image`, `pdf`, `consolidate`, `wiki`. */
  purpose: string;
}

/** One agent's prompt tokens and the part of them served from the provider's cache. */
export interface AgentCacheTotals {
  prompt_tokens: number;
  cached_tokens: number;
}

export interface StatsInfo {
  runs: number;
  model_calls: number;
  spent_usd: number;
  unknown_cost_calls: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
  by_day: Record<string, number>;
  /** Per agent over the same runs as `by_agent`, from the calls that reported both
   *  figures. A server from before it was counted leaves it out. */
  cache_by_agent?: Record<string, AgentCacheTotals>;
  /** Calls on those runs that reported a prompt but no cache figure, which
   *  `cache_by_agent` leaves out. A server from before it was counted leaves it out. */
  unknown_cache_calls?: number;
  /** Memory writes waiting for a decision — the count on the "Ghi nhớ" tab. */
  pending_proposals: number;
  /** The last seven days, oldest first, zeros kept so the chart holds its shape. */
  days: DayUsage[];
  /** Every model ever billed, biggest spender first. */
  models: ModelUsage[];
  /** The same calls split by what they were for, biggest spender first. A server from
   *  before side calls were written down leaves it out. */
  purposes?: PurposeUsage[];
}
