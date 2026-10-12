import type { AgentEvent, ConversationDetail } from "../api/types";
import { itemsFromMessages, updateTool } from "./thread-items";
import {
  emptyThread,
  pendingFromApproval,
  type PendingApproval,
  type ThreadItem,
  type ThreadState,
} from "./thread-state";
import { betweenStreams } from "./writing-previews";

/** The thread as the stored conversation `d` has it: its messages, the request it waits
 *  on, its queue. Nothing of a turn's stream survives it, so it is for between turns, or
 *  for a turn about to be followed from here on. */
export function fromDetail(state: ThreadState, d: ConversationDetail): ThreadState {
  let items = itemsFromMessages(d.messages);
  let pending: PendingApproval | null = null;
  if (d.pending_approval) {
    pending = pendingFromApproval(d.pending_approval);
    items = updateTool(items, pending.toolCallId, { status: "awaiting" });
  }
  // Two notes say what the person's own click came to, which no stored conversation holds:
  // that a decision met a request already settled, and that a turn was stopped. The loads
  // that follow do not answer the click again — the run the decision resumed, the run the
  // Stop ended in a tab that only read along, the stream coming back. A load that brings a
  // new request has moved past either.
  //
  // No stored conversation holds what a turn said of itself either: that it ended in an
  // error, stopped short, or went on by another route. A load follows the turn's own end
  // whenever the message overtook the conversation's opening load, and always in a tab that
  // only read along. So that word stays while the stored thread ends where the thread on
  // screen ends, and goes with a load that brings anything after it. An error of a request
  // this tab made is answered by any load that comes back.
  const kind = state.notice?.kind;
  const click = kind === "handled" || kind === "stopped";
  const said = kind === "halted" || kind === "fallback" || kind === "escalated" || state.notice?.ofTurn === true;
  const answered = (click ? pending === null : said && endsWhereItDid(state.items, items)) ? state.notice : null;
  return {
    ...emptyThread,
    conversationId: d.id,
    items,
    pending,
    spentUsd: d.spent_usd,
    unknownCostCalls: d.unknown_cost_calls,
    notice: answered,
    waiting: d.queued ?? [],
    previewSeq: state.previewSeq,
    ...betweenStreams(state, pending),
  };
}

/** Whether the stored thread ends on what the thread on screen ends on. A message the
 *  person sent from here has no stored id until it is loaded, so its words stand for it.
 *  Anything else is known by its id, a note the same as the call it is stored as. */
function endsWhereItDid(shown: ThreadItem[], stored: ThreadItem[]): boolean {
  const a = shown[shown.length - 1];
  const b = stored[stored.length - 1];
  if (!a || !b) return false;
  return a.kind === "user" && b.kind === "user" ? a.text === b.text : a.id === b.id;
}

/** A turn this tab now follows from the stored conversation on: it opened late, or fell
 *  too far behind to be sent every event. What the turn is writing comes next, as events.
 *
 *  A tab already on the turn keeps what is its own and no stored conversation holds: the
 *  canvas the person put away stays away, and a note still standing — the route that
 *  stepped in, the message that would not queue — stays up. A tab that was not on it finds
 *  another turn going than the one its note was of, whether that one was stopped or said
 *  something of itself: only the word that a decision was already made is not of a turn. */
export function watchingFrom(given: ThreadState, e: Extract<AgentEvent, { type: "watching" }>): ThreadState {
  const rebuilt = { ...fromDetail(given, e.detail), busy: e.running };
  if (given.busy) return { ...rebuilt, notice: rebuilt.notice ?? given.notice, previewsMuted: given.previewsMuted };
  return e.running && rebuilt.notice !== null && rebuilt.notice.kind !== "handled" ? { ...rebuilt, notice: null } : rebuilt;
}
