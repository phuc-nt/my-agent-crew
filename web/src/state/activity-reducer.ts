import { newestFirst } from "../lib/run-order";
import { isAnswered } from "../lib/run-progress";
import { noteText, PROGRESS_NOTE_TOOL } from "../lib/run-rows";
import type { AgentEvent, RunInfo, RunPayload, RunStep } from "../api/types";

/** Runs by id, live ones updated step by step from the activity stream. */
export interface ActivityState {
  runs: Record<string, RunInfo>;
  connected: boolean;
  /** This connection's snapshot has landed. From then on the stream names every run that
   *  starts, so a run not live here is not going. */
  synced: boolean;
}

export type ActivityAction =
  | { type: "payload"; payload: RunPayload }
  | { type: "recent"; runs: RunInfo[] }
  | { type: "connection"; connected: boolean };

export const emptyActivity: ActivityState = { runs: {}, connected: false, synced: false };

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
        // Kept as the server keeps them, so a live card can show how much of the prompt the
        // cache served without waiting for the run to finish and be read back.
        prompt_tokens: e.prompt_tokens,
        cached_tokens: e.cached_tokens,
        thinking: open?.thinking,
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
    case "approval_required": {
      // As on the server, a question is summarised by what it asked and leaves its step
      // open. The open step is what labels the pause "đang hỏi bạn": without it a run that
      // paused on the live stream reads as a permission request until the list reloads.
      const asked = e.kind === "question" && typeof e.arguments.question === "string" ? e.arguments.question : "";
      if (asked) {
        steps.push({ kind: "question", question: preview(asked), duration_ms: null });
        summary = asked;
        break;
      }
      summary = e.reason ? `${e.name} (${e.reason})` : e.name;
      break;
    }
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
    case "steer":
      // Shown the way a note is, and shortened by the same function the server shortens
      // it with (`note_text` in `activity/steps.py`), so the row does not change text
      // once the server's own stored step replaces this live one.
      steps.push({ kind: "steer", text: noteText(e.text), duration_ms: 0 });
      break;
    // Never reaches the activity stream: a stream nothing is watching for it carries only
    // the one `queued` event, which the sending hook intercepts before this reducer runs.
    // Listed so the switch stays exhaustive against a stale tab that somehow still sees it.
    case "queued":
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
      // Open is not synced yet: the snapshot of what is live follows the open.
      return { ...state, connected: action.connected, synced: false };
    case "recent": {
      const runs = { ...state.runs };
      // A run the list calls settled is over for good (only a paused run ever resumes), so
      // that answer wins: a run that ended while the stream was down gets no other word, and
      // a pause settled meanwhile would otherwise wait in "Cần bạn xử lý" until a reload.
      // A run the list calls live is older news than the stream's. Reads overlap and land in
      // any order, so one taken over a copy that has finished, or over the stream's word on
      // what is live, would be an answer read before the run ended, showing it going for
      // good: it only fills in a run not heard of while the stream has not said.
      for (const run of action.runs) {
        const settled = !ACTIVE.includes(run.status) || run.finished_at !== null;
        if (settled || (!state.synced && !(run.id in runs))) runs[run.id] = run;
      }
      return { ...state, runs };
    }
    case "payload":
      return applyPayload(state, action.payload);
  }
}

function applyPayload(state: ActivityState, payload: RunPayload): ActivityState {
  switch (payload.type) {
    case "snapshot": {
      // The snapshot is everything live on the server. A run held here as live that it
      // leaves out ended while the stream was down, and kept, it would spin for good: it
      // goes, and comes back finished with the next list.
      const runs: Record<string, RunInfo> = {};
      for (const run of Object.values(state.runs)) if (!ACTIVE.includes(run.status)) runs[run.id] = run;
      for (const run of payload.runs) runs[run.id] = run;
      return { ...state, runs, connected: true, synced: true };
    }
    case "run": {
      const { run } = payload;
      // A run first heard of here has just started, after every run held: put ahead of
      // them, it stays the newest of any that started in the same second (`newestFirst`).
      const runs = run.id in state.runs ? { ...state.runs, [run.id]: run } : { [run.id]: run, ...state.runs };
      return { ...state, runs };
    }
    case "event": {
      const current = state.runs[payload.run_id];
      if (!current) return state;
      const next = { ...applyRunEvent(current, payload.event), status: payload.status };
      return { ...state, runs: { ...state.runs, [payload.run_id]: next } };
    }
  }
}

export function sortedRuns(state: ActivityState): RunInfo[] {
  return Object.values(state.runs).sort(newestFirst);
}

export function liveRuns(state: ActivityState): RunInfo[] {
  return sortedRuns(state).filter((r) => ACTIVE.includes(r.status));
}

/** Live runs doing work. A paused run is live as well, but it waits on a person and is
 *  counted with what waits on them: counting it here too would say one request twice. */
export function runningRuns(state: ActivityState): RunInfo[] {
  return liveRuns(state).filter((r) => r.status === "running");
}

export function runsForConversation(state: ActivityState, conversationId: string): RunInfo[] {
  return sortedRuns(state).filter((r) => r.conversation_id === conversationId);
}

/**
 * A conversation's own runs together with those of the work it delegated.
 *
 * The delegated run says whose behalf it acts on in its `source`, so the family is read
 * from the streamed runs alone. This narrows only that side: the activity strip lays them
 * over the conversation's stored history, which it asks the server for (`mergeRuns`).
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

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const known = map.get(key);
  if (known) known.push(value);
  else map.set(key, [value]);
}

/**
 * The turn that asked for a delegated run, among its parent conversation's turns.
 *
 * The source names only the conversation, and a conversation's history holds many turns.
 * A conversation runs one turn at a time and the delegate tool starts its child from inside
 * one, so the turn that asked is the one going when the child started: begun by then, and
 * not yet over. Timestamps are whole seconds, so both ends count; of two turns that touch
 * the same second, the later one is the one still going.
 */
function askingTurn(child: RunInfo, turns: RunInfo[]): RunInfo | null {
  const start = Date.parse(child.started_at);
  let asking: RunInfo | null = null;
  for (const turn of turns) {
    const began = Date.parse(turn.started_at);
    const ended = turn.finished_at === null ? Infinity : Date.parse(turn.finished_at);
    const going = began <= start && start <= ended;
    if (going && (asking === null || began > Date.parse(asking.started_at))) asking = turn;
  }
  return asking;
}

/**
 * Runs for the rail, with delegated runs tucked under the run that asked for them.
 *
 * Nesting is one level deep because delegation is: a child cannot delegate on, so a
 * child never has children of its own. A child whose parent is not in view stands on
 * its own rather than disappearing.
 */
export function runGroups(runs: RunInfo[]): RunGroup[] {
  const turns = new Map<string, RunInfo[]>();
  for (const run of runs) {
    // A run with no conversation (a scheduled job) can never be delegated to.
    if (run.conversation_id !== null && parentConversationId(run) === null) {
      push(turns, run.conversation_id, run);
    }
  }
  const children = new Map<string, RunInfo[]>();
  const orphans = new Set<RunInfo>();
  for (const run of runs) {
    const parent = parentConversationId(run);
    if (parent === null) continue;
    const asking = askingTurn(run, turns.get(parent) ?? []);
    if (asking === null) orphans.add(run);
    else push(children, asking.id, run);
  }
  // Kept in the order given, a child standing alone included, for runs that tie.
  return runs
    .filter((run) => parentConversationId(run) === null || orphans.has(run))
    .map((run) => ({ run, children: children.get(run.id) ?? [] }))
    .sort((a, b) => newestFirst(a.run, b.run));
}

/** What needs a human: approvals waiting anywhere, and runs that ended badly. */
export function needsAttention(state: ActivityState): RunInfo[] {
  return sortedRuns(state).filter(
    (r) => r.status === "awaiting_approval" || r.status === "error" || r.status === "halted",
  );
}
