import { useEffect } from "react";

export interface Shortcuts {
  /** ⌘/Ctrl+K — jump to the conversation search. */
  onSearch?: () => void;
  /** ⌘/Ctrl+N — start a new conversation. */
  onNew?: () => void;
  /** Escape — close whatever is open on top. */
  onEscape?: () => void;
}

/** A field where a bare Escape means "abandon what I typed", not "close the panel". */
function isEditing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/**
 * The three keys worth taking from the browser.
 *
 * Each one is claimed only when this app has something to do with it, because every
 * combination here already means something in at least one browser — ⌘N opens a window,
 * ⌘K focuses the address bar in Safari. Handling a key the caller did not ask for would
 * break that with nothing to show for it, so a missing handler is left entirely alone.
 */
export function useShortcuts({ onSearch, onNew, onEscape }: Shortcuts) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "k" && onSearch) {
        event.preventDefault();
        onSearch();
        return;
      }
      if (mod && event.key.toLowerCase() === "n" && onNew) {
        event.preventDefault();
        onNew();
        return;
      }
      // Escape while typing belongs to the field: a rename in progress cancels there,
      // and closing the panel around it would throw away the edit as a side effect.
      if (event.key === "Escape" && onEscape && !isEditing(event.target)) onEscape();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSearch, onNew, onEscape]);
}
