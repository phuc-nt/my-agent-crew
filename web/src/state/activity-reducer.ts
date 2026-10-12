import { newestFirst } from "../lib/run-order";
import type { RunInfo, RunPayload } from "../api/types";
import { applyRunEvent } from "./activity-run-event";
import { parentConversationId } from "./run-groups";

export { applyRunEvent } from "./activity-run-event";
export { parentConversationId, runGroups, type RunGroup } from "./run-groups";

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

const ACTIVE: RunInfo["status"][] = ["running", "awaiting_approval"];

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

/** What needs a human: approvals waiting anywhere, and runs that ended badly. */
export function needsAttention(state: ActivityState): RunInfo[] {
  return sortedRuns(state).filter(
    (r) => r.status === "awaiting_approval" || r.status === "error" || r.status === "halted",
  );
}
