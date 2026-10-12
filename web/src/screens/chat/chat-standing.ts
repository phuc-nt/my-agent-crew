import type { RunInfo } from "../../api/types";
import type { AskDisabled } from "../../components/canvas/canvas-ask";
import type { ConversationMoney } from "../../state/conversation-money";
import type { ChatProps } from "./chat-props";

interface StandingParts extends Pick<ChatProps, "thread"> {
  externalRun: RunInfo | null;
  money: ConversationMoney | null;
}

/** What the turn and the budget leave open now: a question about a passage, the raise, Stop. */
export function chatStanding({ thread, externalRun, money }: StandingParts) {
  const { state } = thread;
  // Why a question about a passage cannot go now, which the ask bar says in words. A turn that
  // is running comes first: the passage would be of a canvas the agent is still changing.
  const askDisabled: AskDisabled =
    state.busy || externalRun !== null
      ? "busy"
      : state.pending !== null
        ? "pending"
        : money?.overBudget
          ? "budget"
          : null;
  // One way out of a spent budget on screen at a time: the over-budget notice carries it
  // while it shows, and the halt's notice until then — only while the cap still stands at
  // what was spent, so a raise takes it away and the halt's notice says to send again.
  const overBudget = Boolean(money?.overBudget) && !state.busy;
  // Stop can reach three different things: this tab's own running turn, a message still
  // only sitting in the queue with nothing running yet, or a turn another chat tab or the
  // Telegram channel started. Only the last of those needs asking the server whether
  // anything was even there to stop — `chat` and `api` are the sources a person, not a
  // schedule or a delegate, could plausibly be running from right now. A turn this tab
  // watches is that last kind too, however much of it is on screen.
  const stoppable =
    (state.busy && !thread.watching) ||
    state.waiting.length > 0 ||
    (externalRun !== null && ["chat", "api"].includes(externalRun.source));
  return { askDisabled, overBudget, stoppable };
}
