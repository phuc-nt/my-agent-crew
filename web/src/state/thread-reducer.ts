import { fromDetail } from "./thread-detail";
import { applyEvent } from "./thread-events";
import { settle, withoutLocalBubble } from "./thread-items";
import { emptyThread, type ThreadAction, type ThreadState } from "./thread-state";
import { betweenStreams, noPreviews } from "./writing-previews";

export { itemsFromMessages } from "./thread-items";
export {
  emptyThread,
  pendingFromApproval,
  questionText,
  type PendingApproval,
  type ThreadAction,
  type ThreadItem,
  type ThreadState,
  type ToolStatus,
} from "./thread-state";

export function threadReducer(state: ThreadState, action: ThreadAction): ThreadState {
  switch (action.type) {
    case "opened":
      return { ...emptyThread, previewSeq: state.previewSeq };
    case "loaded":
      return fromDetail(state, action.detail);
    case "user_sent":
      return {
        ...state,
        items: [...state.items, { kind: "user", id: `local-${state.items.length}`, text: action.text }],
        notice: null,
      };
    case "user_unsent":
      return { ...state, items: withoutLocalBubble(state.items, action.text) };
    case "turn_started":
      return { ...state, busy: true, streaming: null, notice: null, ...betweenStreams(state) };
    case "turn_finished":
      return { ...state, busy: false, streaming: null, thinking: false, items: settle(state), ...betweenStreams(state) };
    case "turn_stopped": {
      // Stopping cuts the stream, and the server gives up the turn with it: a decision
      // already sent is spent, so its call stops with the rest instead of asking again.
      const cut = { ...state, pending: null };
      const items = settle(cut).map((it) =>
        it.kind === "tool" && it.status === "awaiting" ? { ...it, status: "stopped" as const } : it,
      );
      const notice = { kind: "stopped" as const, text: "" };
      return { ...cut, items, busy: false, streaming: null, thinking: false, notice, ...noPreviews };
    }
    case "settled": {
      if (state.busy) return state;
      const items = settle(state);
      return items === state.items ? state : { ...state, items };
    }
    case "failed":
      return {
        ...state,
        busy: false,
        streaming: null,
        thinking: false,
        items: settle(state),
        notice: { kind: "error", text: action.message },
        ...betweenStreams(state),
      };
    case "handled":
      // A turn begun since has the thread: a note about the earlier decision would be stale.
      return state.busy ? state : { ...state, notice: { kind: "handled", text: "" } };
    case "queued": {
      // A local bubble for this text was added optimistically by `user_sent` on the plain
      // send path; drop it once the server's own chip stands for it. A busy-send POST never
      // adds that bubble, so there is nothing to drop on that path — only to add here.
      // A send made again is answered with the chip it already has: one stands for it.
      const known = state.waiting.some((item) => item.id === action.item.id);
      return {
        ...state,
        items: withoutLocalBubble(state.items, action.item.text),
        waiting: known ? state.waiting : [...state.waiting, action.item],
      };
    }
    case "queue_cleared":
      return { ...state, waiting: [] };
    case "elsewhere":
      return { ...state, notice: { kind: "elsewhere", text: "" } };
    case "queue_failed":
      return { ...state, notice: { kind: "error", text: action.message } };
    case "previews_muted":
      return { ...state, previewsMuted: true };
    case "event":
      return applyEvent(state, action.event);
  }
}
