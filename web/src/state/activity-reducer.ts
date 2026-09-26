import { isAnswered } from "../lib/run-progress";
import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import type { AgentEvent, RunInfo, RunPayload, RunStep } from "../api/types";

/** Runs by id, live ones updated step by step from the activity stream. */
export interface ActivityState {
  runs: Record<string, RunInfo>;
  connected: boolean;
}

export type ActivityAction =
  | { type: "payload"; payload: RunPayload }
  | { type: "recent"; runs: RunInfo[] }
  | { type: "connection"; connected: boolean };

export const emptyActivity: ActivityState = { runs: {}, connected: false };

const PREVIEW_CHARS = 160;
const ACTIVE: RunInfo["status"][] = ["running", "awaiting_approval"];

function preview(text: string): string {
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS)}…` : text;
}

/** Client-side twin of the server's step builder so live runs show steps before they finish. */
export function applyRunEvent(run: RunInfo, e: AgentEvent): RunInfo {
  const steps: RunStep[] = [...run.steps];
  let { spent_usd, unknown_cost_calls, summary } = run;
  switch (e.type) {
    case "assistant_message": {
      // A child's answer handed on as this reply: no model spoke, so there is no step
      // and no bill. The delegate step already shows the answer.
      if (e.provider === null) break;
      // A run read mid-call carries that call open; its answer closes it rather than
      // standing beside it as a second call.
      const last = steps[steps.length - 1];
      const open = last?.kind === "model" && !isAnswered(last) ? last : null;
      const answered: RunStep = {
        kind: "model",
        first_token_ms: open?.first_token_ms,
        // This reducer skips deltas, so a snapshot's count stops where the snapshot was
        // taken; the answer is the whole of what streamed.
        chars: Math.max(open?.chars ?? 0, e.content.length),
        provider: e.provider,
        model: e.model,
        cost_usd: e.cost_usd,
        tool_calls: e.tool_calls.map((c) => c.name),
        preview: preview(e.content),
        duration_ms: null,
      };
      if (open) steps[steps.length - 1] = answered;
      else steps.push(answered);
      if (e.cost_usd === null) unknown_cost_calls += 1;
      else spent_usd += e.cost_usd;
      if (e.content) summary = preview(e.content);
      break;
    }
    case "tool_call":
      if (e.name === PROGRESS_NOTE_TOOL) {
        // Closed the moment it is written, exactly as the server writes it: a note is
        // finished as soon as it is said, and an open one would spin a spinner on a
        // sentence for the rest of the run.
        steps.push({ kind: "note", text: noteText(e.arguments), duration_ms: 0 });
        break;
      }
      steps.push({
        kind: "tool",
        name: e.name,
        tool_call_id: e.tool_call_id,
        arguments: e.arguments,
        ok: null,
        output: null,
        duration_ms: null,
      });
      break;
    case "tool_result": {
      // The note step was already written and closed by its call, and it carries no
      // tool_call_id to find. Without this the search below would miss it, which is
      // harmless — but the step must not be patched with an ok flag either way.
      if (e.name === PROGRESS_NOTE_TOOL) break;
      const at = steps.findIndex((s) => s.kind === "tool" && s.tool_call_id === e.tool_call_id);
      const patch = { ok: e.ok, output: preview(e.output) };
      if (at >= 0) steps[at] = { ...(steps[at] as Extract<RunStep, { kind: "tool" }>), ...patch };
      break;
    }
    case "approval_required":
      summary = e.reason ? `${e.name} (${e.reason})` : e.name;
      break;
    case "halted":
      summary = e.reason;
      spent_usd = e.spent_usd;
      break;
    case "error":
      summary = e.message;
      break;
    case "done":
      spent_usd = e.spent_usd;
      unknown_cost_calls = e.unknown_cost_calls;
      break;
    case "route_fallback": {
      // As on the server, an open call moves after the fallback: it now waits on the next
      // route, and left ahead of it the answer would open a second call instead.
      const fallback: RunStep = { kind: "fallback", provider: e.provider, model: e.model, error: preview(e.error), duration_ms: null };
      const last = steps[steps.length - 1];
      if (last?.kind === "model" && !isAnswered(last)) steps.splice(steps.length - 1, 0, fallback);
      else steps.push(fallback);
      break;
    }
    case "text_delta":
    case "thinking":
    case "model_call":
      break;
  }
  return { ...run, steps, spent_usd, unknown_cost_calls, summary };
}

export function activityReducer(state: ActivityState, action: ActivityAction): ActivityState {
  switch (action.type) {
    case "connection":
      return { ...state, connected: action.connected };
    case "recent": {
      const runs = { ...state.runs };
      for (const run of action.runs) if (!ACTIVE.includes(runs[run.id]?.status)) runs[run.id] = run;
      return { ...state, runs };
    }
    case "payload":
      return applyPayload(state, action.payload);
  }
}

function applyPayload(state: ActivityState, payload: RunPayload): ActivityState {
  switch (payload.type) {
    case "snapshot": {
      const runs = { ...state.runs };
      for (const run of payload.runs) runs[run.id] = run;
      return { ...state, runs, connected: true };
    }
    case "run":
      return { ...state, runs: { ...state.runs, [payload.run.id]: payload.run } };
    case "event": {
      const current = state.runs[payload.run_id];
      if (!current) return state;
      const next = { ...applyRunEvent(current, payload.event), status: payload.status };
      return { ...state, runs: { ...state.runs, [payload.run_id]: next } };
    }
  }
}

export function sortedRuns(state: ActivityState): RunInfo[] {
  return Object.values(state.runs).sort((a, b) => (a.started_at < b.started_at ? 1 : -1));
}

export function liveRuns(state: ActivityState): RunInfo[] {
  return sortedRuns(state).filter((r) => ACTIVE.includes(r.status));
}

export function runsForConversation(state: ActivityState, conversationId: string): RunInfo[] {
  return sortedRuns(state).filter((r) => r.conversation_id === conversationId);
}

/**
 * A conversation's own runs together with those of the work it delegated.
 *
 * The delegated run says whose behalf it acts on in its `source`, so the family is read
 * from the runs already in hand — opening the activity strip asks the server for nothing.
 */
export function conversationFamilyRuns(
  state: ActivityState,
  conversationId: string,
): RunInfo[] {
  return sortedRuns(state).filter(
    (r) => r.conversation_id === conversationId || parentConversationId(r) === conversationId,
  );
}

const DELEGATE_SOURCE = "delegate";

/** A delegated run names the conversation that handed out the work: `delegate:<id>`. */
export function parentConversationId(run: RunInfo): string | null {
  return run.source.startsWith(`${DELEGATE_SOURCE}:`)
    ? run.source.slice(DELEGATE_SOURCE.length + 1) || null
    : null;
}

export type RunGroup = { run: RunInfo; children: RunInfo[] };

/**
 * Runs for the rail, with delegated runs tucked under the run that asked for them.
 *
 * Nesting is one level deep because delegation is: a child cannot delegate on, so a
 * child never has children of its own. A child whose parent is not in view stands on
 * its own rather than disappearing.
 */
export function runGroups(runs: RunInfo[]): RunGroup[] {
  const byConversation = new Map<string, RunInfo>();
  for (const run of runs) {
    // A run with no conversation (a scheduled job) can never be delegated to.
    if (run.conversation_id !== null && parentConversationId(run) === null) {
      byConversation.set(run.conversation_id, run);
    }
  }
  const children = new Map<string, RunInfo[]>();
  const orphans: RunInfo[] = [];
  for (const run of runs) {
    const parent = parentConversationId(run);
    if (parent === null) continue;
    if (!byConversation.has(parent)) {
      orphans.push(run);
      continue;
    }
    const known = children.get(parent);
    if (known) known.push(run);
    else children.set(parent, [run]);
  }
  const groups = runs
    .filter((run) => parentConversationId(run) === null)
    .map((run) => ({
      run,
      children: run.conversation_id === null ? [] : (children.get(run.conversation_id) ?? []),
    }));
  return [...groups, ...orphans.map((run) => ({ run, children: [] }))].sort((a, b) =>
    a.run.started_at < b.run.started_at ? 1 : -1,
  );
}

/** What needs a human: approvals waiting anywhere, and runs that ended badly. */
export function needsAttention(state: ActivityState): RunInfo[] {
  return sortedRuns(state).filter(
    (r) => r.status === "awaiting_approval" || r.status === "error" || r.status === "halted",
  );
}
