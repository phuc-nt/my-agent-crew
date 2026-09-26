import { useCallback, useState } from "react";

const PREFIX = "composer-draft:";

function read(key: string | null): string {
  if (key === null) return "";
  try {
    return window.localStorage.getItem(PREFIX + key) ?? "";
  } catch {
    return "";
  }
}

function write(key: string | null, text: string): void {
  if (key === null) return;
  try {
    // An empty box is no draft: removing the entry keeps storage to the texts worth keeping.
    if (text) window.localStorage.setItem(PREFIX + key, text);
    else window.localStorage.removeItem(PREFIX + key);
  } catch {
    // Storage refused (a private window, a full quota): the text still lives while the page does.
  }
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
