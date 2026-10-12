import type { Conversation } from "../api/types";
import type { ThreadState } from "./thread-reducer";

/** The money of the conversation on screen, read once for every place that shows it. */
export interface ConversationMoney {
  spentUsd: number;
  /** The cap is above zero and the spend has reached it: the server's own rule. */
  capReached: boolean;
  /** The server will halt the next turn before it starts. */
  overBudget: boolean;
}

/**
 * What the conversation on screen has spent, and whether that has used up its cap.
 *
 * Two readings of the spend exist. The row is what the server last sent: the sidebar's
 * entry, read again whenever a run ends, or, for a conversation the sidebar does not list
 * (it lists the master's only), the conversation as it was last loaded. The thread hears
 * the spend from a turn's last event, and only `done` and `halted` say it: a turn that ends
 * in an error, at a request to the person, or stopped by them says nothing of money.
 *
 * So neither reading is always the later one. After a turn that said its spend the thread
 * is ahead of a row nothing has read since. After one that did not, a conversation outside
 * the list is loaded again (`useExternalRunRefresh`), which brings both readings up; until
 * that load lands both are the figure from before the turn. The server only ever adds to a
 * conversation's spend, so the larger of the two is the later, and that one figure goes to
 * the header and to the overview alike.
 *
 * A listed row also brings the server's own word on the budget when it is read again.
 * Nothing brings it for a conversation outside the list, so there it is worked out from
 * the spend and the cap.
 */
export function conversationMoney(
  row: Conversation,
  listed: boolean,
  thread: Pick<ThreadState, "conversationId" | "spentUsd">,
): ConversationMoney {
  const heard = thread.conversationId === row.id ? thread.spentUsd : 0;
  const spentUsd = Math.max(row.spent_usd, heard);
  const capReached = row.cost_cap_usd > 0 && spentUsd >= row.cost_cap_usd;
  return { spentUsd, capReached, overBudget: row.over_budget || (!listed && capReached) };
}
