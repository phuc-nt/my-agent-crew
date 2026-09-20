// Shapes of the activity stream, the job list and the cost summary (GET /api/activity/*, /jobs, /stats).
import type { AgentEvent, ScheduleInfo } from "./types";

export type RunStatus = "running" | "awaiting_approval" | "done" | "halted" | "error";

export type RunStep =
  | {
      kind: "model";
      chars: number;
      provider: string | null;
      model: string | null;
      cost_usd: number | null;
      tool_calls: string[];
      preview: string;
      duration_ms: number | null;
    }
  | {
      kind: "tool";
      name: string;
      tool_call_id: string;
      arguments: Record<string, unknown>;
      ok: boolean | null;
      output: string | null;
      duration_ms: number | null;
    }
  | {
      kind: "fallback";
      provider: string;
      model: string;
      error: string;
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

export type ActivityPayload =
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
  unknown_cost_calls: number;
}

export interface DayUsage extends UsageTotals {
  /** Calendar day (UTC), `YYYY-MM-DD`. */
  day: string;
}

export interface ModelUsage extends UsageTotals {
  /** `provider:model`. */
  model: string;
}

export interface StatsInfo {
  runs: number;
  model_calls: number;
  spent_usd: number;
  unknown_cost_calls: number;
  by_agent: Record<string, number>;
  by_model: Record<string, number>;
  by_day: Record<string, number>;
  /** Memory writes waiting for a decision — the count on the "Ghi nhớ" tab. */
  pending_proposals: number;
  /** The last seven days, oldest first, zeros kept so the chart holds its shape. */
  days: DayUsage[];
  /** Every model ever billed, biggest spender first. */
  models: ModelUsage[];
}
