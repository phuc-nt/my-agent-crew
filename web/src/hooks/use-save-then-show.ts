import { useCallback, useRef, useState } from "react";

/**
 * Turning to a view that shows only what the server holds waits for the save, so the page shown is
 * the one just written. Each turn takes a ticket, and a later turn, to either view, cancels one
 * still waiting: the last click wins however slowly the save answers.
 *
 * Whatever the save comes to, the turn is made: a save that failed leaves the last saved version
 * on show, and the panel says so while some text is not in it.
 */
export function useSaveThenShow(flush: () => Promise<number | null>) {
  const ticket = useRef(0);
  const [waiting, setWaiting] = useState(false);
  const save = useRef(flush);
  save.current = flush;

  /** Runs `show` now, or when the save has answered if `wait`. */
  const turn = useCallback((wait: boolean, show: () => void) => {
    const mine = ++ticket.current;
    if (!wait) {
      setWaiting(false);
      show();
      return;
    }
    setWaiting(true);
    void save
      .current()
      .catch(() => null)
      .then(() => {
        if (ticket.current !== mine) return;
        setWaiting(false);
        show();
      });
  }, []);

  /** Drops a turn still waiting, for a move that is not a turn itself. */
  const cancel = useCallback(() => {
    ticket.current++;
    setWaiting(false);
  }, []);

  return { waiting, turn, cancel };
}
