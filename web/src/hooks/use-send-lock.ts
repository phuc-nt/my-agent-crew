import { useReducer, useRef } from "react";
import { forgetDraft } from "./use-draft";

/** What the box hands its words to. A promise answers later whether they were taken. */
export type SendWords = (text: string) => Promise<boolean> | void;

/**
 * Holds a message in the box that wrote it for as long as it takes to be sent.
 *
 * A caller that answers with a promise says the words may still not go: the canvas open beside
 * them is saved first, and the POST can fail. Until it settles the box stays as it is, read-only
 * and holding the text, and a second send is ignored. `true` then spends the words and `false`
 * leaves them where they were typed, so a failed send costs the person nothing. A caller that
 * answers with nothing spends them at once.
 *
 * The hold belongs to the draft `key` the words were typed under, not to the component: another
 * conversation's box is free to write in meanwhile, and the one that was left is found holding
 * its words on return.
 */
export function useSendLock(key: string | null, text: string, setText: (text: string) => void) {
  const sending = useRef(new Set<string | null>());
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  // A send outlives the render that started it, so it reads the box as it is when it settles.
  const latest = useRef({ key, text, setText });
  latest.current = { key, text, setText };

  const spend = (from: string | null, typed: string) => {
    const now = latest.current;
    if (now.key !== from) {
      // The person went elsewhere meanwhile: the words still wait in the draft of the box left.
      if (from !== null) forgetDraft(from);
      return;
    }
    // Only what was sent goes. Stop may have handed queued words back while the box was held,
    // ahead of the text, and a suggestion may have replaced it: neither is the person's to lose.
    if (now.text === typed) now.setText("");
    else if (now.text.endsWith(typed)) now.setText(now.text.slice(0, -typed.length).replace(/\n+$/, ""));
  };

  const send = (onSend: SendWords, typed: string): void => {
    const words = typed.trim();
    if (!words || sending.current.has(key)) return;
    const answer = onSend(words);
    if (!(answer instanceof Promise)) {
      setText("");
      return;
    }
    sending.current.add(key);
    redraw();
    void answer
      .catch((error: unknown) => {
        console.error("the message could not be sent", error);
        return false;
      })
      .then((spent) => {
        sending.current.delete(key);
        redraw();
        if (spent) spend(key, typed);
      });
  };

  return { locked: sending.current.has(key), send };
}
