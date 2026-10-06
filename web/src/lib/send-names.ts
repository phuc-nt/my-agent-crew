import type { ThreadState } from "../state/thread-reducer";
import { newRequestId } from "./request-id";

/**
 * The names this tab's sends go out under.
 *
 * A send that failed with nothing heard may have been taken by the server all the same. Its
 * words are handed back to the person and its name is kept: sent again, the same words go out
 * under the same name, and the server answers with what became of the message instead of
 * taking it twice.
 *
 * The name is kept until the page shows the message as said. A person goes by the page: while
 * it says the send failed, the same words are the same message. Once the thread shows the
 * message, the page takes the words it handed back out of the box and lets the name go, so the
 * same words typed after that are a new message, as when a person reads the answer and sends
 * "go on" a second time. The server does not say which turn a name got, so "shown" is counted:
 * the thread shows the words as the person's more times than it did when the name first went
 * out.
 *
 * Each conversation keeps one name, that of the last send there that was not heard back.
 * Other words sent to it let the name go; a send to another conversation does not.
 */

/** The name a send goes out under, and how the page stood when it first did. */
export interface SentName {
  name: string;
  /** How many times the thread showed these words as the person's when the name first went
   *  out. `null` when the conversation's stored thread was not on screen to count in: such a
   *  name is never taken to be shown. */
  said: number | null;
}

export interface SendNames {
  /** The name for `text` sent to the conversation. The words of the send kept there go out
   *  under its name, as it first went out; other words get a new one. Either way nothing is
   *  kept afterwards: `keep` holds the name again when this send is not heard back either. */
  take(conversationId: string, text: string, said: number | null): SentName;
  /** The send failed with nothing heard: the server may have the message all the same. */
  keep(conversationId: string, text: string, sent: SentName): void;
  /** The words kept for the conversation, once `said` counts them more times than it did
   *  when their name first went out. Lets nothing go. */
  shown(conversationId: string, said: (text: string) => number): string | null;
  /** Lets go of the name kept for the conversation. */
  forget(conversationId: string): void;
}

/**
 * How many times the thread shows `text` as said by the person: as a message, this tab's own
 * not yet stored included, or as a message waiting in line. The count of a message does not
 * rise when the server's copy takes the place of this tab's, nor when it leaves the line for
 * the thread.
 */
export function timesSaid(thread: Pick<ThreadState, "items" | "waiting">, text: string): number {
  let times = 0;
  for (const item of thread.items) if (item.kind === "user" && item.text === text) times += 1;
  for (const item of thread.waiting) if (item.text === text) times += 1;
  return times;
}

export function sendNames(): SendNames {
  const kept = new Map<string, { text: string; sent: SentName }>();
  return {
    take(conversationId, text, said) {
      const last = kept.get(conversationId);
      kept.delete(conversationId);
      return last !== undefined && last.text === text ? last.sent : { name: newRequestId(), said };
    },
    keep(conversationId, text, sent) {
      kept.set(conversationId, { text, sent });
    },
    shown(conversationId, said) {
      const last = kept.get(conversationId);
      if (last === undefined || last.sent.said === null) return null;
      return said(last.text) > last.sent.said ? last.text : null;
    },
    forget(conversationId) {
      kept.delete(conversationId);
    },
  };
}
