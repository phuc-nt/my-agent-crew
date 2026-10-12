import type { MessageCanvas } from "../api/artifact-types";
import type { ConversationDetail } from "../api/types";
import type { SendResult } from "../lib/send-result";
import type { ThreadState } from "../state/thread-reducer";

export interface ThreadController {
  state: ThreadState;
  detail: ConversationDetail | null;
  /** Sends `text` and says how that went the moment the server says anything — see
   *  `SendResult` — while the turn it starts goes on after that. Found busy, this tab's own
   *  stream or one this tab did not start, the message queues instead. `canvas` is the one
   *  open in this tab, which the server takes as the conversation's; left out, it keeps its own. */
  send: (text: string, canvas?: MessageCanvas) => Promise<SendResult>;
  /** `always` also whitelists the tool for the rest of this conversation. */
  decide: (approve: boolean, always?: boolean) => Promise<void>;
  /** Reply to a question the agent asked. Only a question row accepts this. */
  answer: (text: string) => Promise<void>;
  /** Tells the server to end the turn and hand back every message still queued, then cuts
   *  this tab's stream of a turn that was ended; resolves with the cleared texts, oldest
   *  first, so the caller can put them back in the composer. `externalRunning` says whether a
   *  turn is known to be going somewhere this tab cannot reach, for the notice it may show. */
  stop: (externalRunning?: boolean) => Promise<string[]>;
  /** Reads along with the turn under way here, whoever started it, unless this tab is
   *  reading one already. Resolves once it has no more to read, false when there was nothing:
   *  the server had no turn under way, or could not be asked. */
  watch: () => Promise<boolean>;
  /** The turn on screen is one this tab reads along with, not one it started. */
  watching: boolean;
  reload: () => Promise<void>;
  /** Loads again now, or once this tab's turn is over: a load mid-turn would drop it. */
  reloadWhenIdle: () => void;
  /** Marks calls no run will answer any more as stopped; a no-op while a turn runs. */
  settle: () => void;
  /** The person put away a canvas being written: none comes up by itself for the rest of the turn. */
  mutePreviews: () => void;
  /** Counts the times a run turned out not to be read by a stream this tab started: a
   *  decision refused as already taken elsewhere, a turn joined by watching, a stream lost
   *  while its turn went on, a stream that closed before its turn's last word. Whatever run
   *  was put down to this tab then is not its own. */
  unowned: number;
  /** Counts the Stops the server answered by ending the turn. The run going here then is
   *  over, though the activity stream says so only once the turn has let go of its work. */
  stops: number;
}
