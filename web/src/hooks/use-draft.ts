import { useCallback, useState } from "react";
import { readText, writeText } from "../lib/local-store";

// Kept as the text itself, not JSON: switching would lose every draft already saved.
const PREFIX = "composer-draft:";

function read(key: string | null): string {
  return key === null ? "" : (readText(PREFIX + key) ?? "");
}

/** Where storage is refused, the text still lives while the page does. */
function write(key: string | null, text: string): void {
  // An empty box is no draft: removing the entry keeps storage to the texts worth keeping.
  if (key !== null) writeText(PREFIX + key, text || null);
}

/** Drops a conversation's draft once the conversation itself is gone: nothing can show it again. */
export function forgetDraft(key: string): void {
  write(key, "");
}

/**
 * The composer's text, kept per conversation so a half-written message survives switching
 * away and back — on a phone the drawer makes that switch constant — and a reload.
 *
 * The text is written through on every change rather than on leaving: there is no
 * reliable "leaving" on a phone, where the page can simply be frozen in the background.
 * A `null` key keeps the text in memory only.
 */
export function useDraft(key: string | null): [string, (text: string) => void] {
  const [state, setState] = useState(() => ({ key, text: read(key) }));
  // A new key swaps in that conversation's draft during the same render, so the box never
  // shows one conversation's words under another's header, not even for a frame.
  let current = state;
  if (state.key !== key) {
    current = { key, text: read(key) };
    setState(current);
  }
  const setText = useCallback(
    (text: string) => {
      setState({ key, text });
      write(key, text);
    },
    [key],
  );
  return [current.text, setText];
}
