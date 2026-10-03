/**
 * A note for a wait the person can see: while a message waits for the open canvas's last save, the
 * box says so, but only once the wait has gone on a moment, so a save that lands at once leaves no
 * flash behind and nothing for a screen reader to announce.
 */

import { useCallback, useState } from "react";

/** How long a wait goes on before it is said. */
export const SAVING_NOTE_DELAY_MS = 300;

export function useSavingNote(): { shown: boolean; during<T>(work: Promise<T>): Promise<T> } {
  const [shown, setShown] = useState(false);
  const during = useCallback(async <T>(work: Promise<T>): Promise<T> => {
    const timer = setTimeout(() => setShown(true), SAVING_NOTE_DELAY_MS);
    try {
      return await work;
    } finally {
      clearTimeout(timer);
      setShown(false);
    }
  }, []);
  return { shown, during };
}
