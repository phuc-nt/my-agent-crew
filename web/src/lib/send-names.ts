import type { RunInfo } from "../api/types";
import { newRequestId } from "./request-id";

/** The name a send goes out under, and what the tab knew of the conversation as it first did. */
export interface SentName {
  name: string;
  /** The runs going there then, a paused one included. None of them is the turn the message
   *  gets: found busy, a message waits for a turn of its own. */
  before: ReadonlySet<string>;
  /** The tab was reading a turn there. */
  reading: boolean;
}

/**
 * The names this tab's messages go out under.
 *
 * A send that failed with nothing heard may have been taken all the same, so the same words
 * sent again to the same conversation go under the same name, and the server answers with what
 * became of the message instead of taking it twice. That holds while the turn the message may
 * have got is open. Once that turn is seen to end the words are a new message — the next step
 * the person asks for — and a name the server has taken would start no turn for it.
 *
 * The server does not say which turn a name got, so the end is told from what this tab saw:
 *
 * - a run of the conversation that was not going as the name first went out, seen going since
 *   the send failed and now gone;
 * - a stream read there saying its turn is over, when nothing was going there as the name went
 *   out. Had a turn been going, the stream could be that turn's, behind which the message waits.
 *
 * Whatever is less than that keeps the name: a turn that stops to wait on the person, the
 * end of a turn the message waited behind, a run this tab never saw going. A name kept too
 * long costs one more send; one dropped too soon has the agent do the work twice.
 */
export interface SendNames {
  /** Every run going or paused, in any conversation, as the activity stream has them now. */
  going(runs: readonly Pick<RunInfo, "id" | "conversation_id">[]): void;
  /** The name for `text` sent to the conversation now. `reading` says the tab is reading a
   *  turn there. A name kept for these words is handed back as it first went out, and spent. */
  take(conversationId: string, text: string, reading: boolean): SentName;
  /** The send failed with nothing heard: its name is kept for the same words. */
  keep(conversationId: string, text: string, sent: SentName): void;
  /** A stream read in the conversation said its turn is over. */
  ended(conversationId: string): void;
}

interface Kept {
  conversationId: string;
  text: string;
  sent: SentName;
  /** The runs seen going in the conversation since the send failed, that were not going as
   *  the name went out: the first of them to be gone ended the turn the message got. */
  since: Set<string>;
}

export function sendNames(): SendNames {
  /** The conversation of each run going now. */
  let live = new Map<string, string | null>();
  // One send at most: any other send is a new one, and lets the kept name go.
  let kept: Kept | null = null;

  const follow = () => {
    if (kept === null) return;
    const { conversationId, sent, since } = kept;
    // The tab was reading a turn whose run it did not know: the next run to end there may be
    // that one, and nothing tells them apart.
    if (sent.reading && sent.before.size === 0) return;
    for (const id of since) {
      if (!live.has(id)) {
        kept = null;
        return;
      }
    }
    for (const [id, conversation] of live) {
      if (conversation === conversationId && !sent.before.has(id)) since.add(id);
    }
  };

  return {
    going(runs) {
      live = new Map(runs.map((run) => [run.id, run.conversation_id]));
      follow();
    },
    take(conversationId, text, reading) {
      const last = kept;
      kept = null;
      if (last !== null && last.conversationId === conversationId && last.text === text) return last.sent;
      const before = new Set<string>();
      for (const [id, conversation] of live) {
        if (conversation === conversationId) before.add(id);
      }
      return { name: newRequestId(), before, reading };
    },
    keep(conversationId, text, sent) {
      kept = { conversationId, text, sent, since: new Set() };
      follow();
    },
    ended(conversationId) {
      if (kept === null || kept.conversationId !== conversationId) return;
      if (!kept.sent.reading && kept.sent.before.size === 0) kept = null;
    },
  };
}
