// Shapes of the activity stream, the job list and the cost summary (GET /api/activity/*, /jobs, /stats).
import type { ArtifactEvent } from "./artifact-types";
import type { ScheduleInfo } from "./types/agents";
import type { Conversation } from "./types/conversation";
import type { AgentEvent } from "./types/events";
import type { RunInfo, RunStatus } from "./types/runs";

export type * from "./types/runs";

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
  | { type: "conversation"; conversation: Conversation }
  // A canvas changed: its summary or its deletion, never its text.
  | ArtifactEvent
  // The job list is no longer what a page read. The server counts a run into its job's
  // streak of failures, and tells the owner, only after the run is over; and a schedule
  // saved, an agent that joined and one that left change which jobs there are with no run
  // at all. It carries nothing; the page reads the list again.
  | { type: "jobs" };

/** A job whose runs keep ending in an error, and what the owner was told about it. */
export interface JobFailing {
  /** Runs in a row that failed, the latest included: one at least. */
  count: number;
  /** When the first failure of the streak was counted, which is after that run ended. */
  since: string;
  /** When the owner was last told over Telegram; null while no notice has got through. */
  told_at: string | null;
  /** The earliest a failure is told again; null along with `told_at`. */
  next_notice_at: string | null;
  /** A notice of this streak is on its way to Telegram, which has not answered yet. */
  telling: boolean;
}

export interface JobInfo extends ScheduleInfo {
  schedule_id: string;
  agent_id: string;
  next_run: string | null;
  last_run: RunInfo | null;
  running: boolean;
  /** Switched off at runtime; `enabled` is the effective value (profile AND not paused). */
  paused: boolean;
  /** "profile" came from `agent.yaml` and is changed in the agent's editor; "chat" was
   *  proposed by the agent and approved by a person, and can be deleted from here. */
  origin: "profile" | "chat";
  /** Set while the job is in a streak of failed runs. A server from before the streak was
   *  counted leaves the key out, which reads as no streak. */
  failing?: JobFailing | null;
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
   *  `title`, `session_summary`, `tool_summary`, `image`, `pdf`, `consolidate`, `wiki`,
   *  `script` (a model a script asked on its own). */
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
