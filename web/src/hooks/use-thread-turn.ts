import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { ApiError } from "../api/client";
import type { AgentEvent } from "../api/types";
import { turnErrorText } from "../lib/error-text";
import { endsTurn } from "../lib/turn-end";
import type { ThreadAction } from "../state/thread-reducer";

/** What a turn on this tab's own stream needs from the thread it belongs to. */
interface TurnParts {
  abortRef: MutableRefObject<AbortController | null>;
  watchRef: MutableRefObject<AbortController | null>;
  turns: MutableRefObject<number>;
  opened: MutableRefObject<{ id: string | null }>;
  dispatch: Dispatch<ThreadAction>;
  onEvent: (event: AgentEvent) => void;
  reload: () => Promise<void>;
  setOwed: Dispatch<SetStateAction<boolean>>;
  setUnowned: Dispatch<SetStateAction<number>>;
}

export function useThreadTurn({
  abortRef,
  watchRef,
  turns,
  opened,
  dispatch,
  onEvent,
  reload,
  setOwed,
  setUnowned,
}: TurnParts) {
  /** Runs a turn on a stream this tab starts. `turnless` is asked once the stream has closed,
   *  and says the server answered with no turn on it: the message was only put in line, or
   *  the decision was refused. */
  const runTurn = useCallback(
    async (
      run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>,
      describe: (error: unknown) => string = turnErrorText,
      turnless: () => boolean = () => false,
    ) => {
      const controller = new AbortController();
      watchRef.current?.abort(); // one stream feeds the thread: this one takes over
      abortRef.current = controller;
      turns.current += 1;
      dispatch({ type: "turn_started" });
      const said = { last: false };
      // An aborted stream is one this tab stopped reading — Stop, or another conversation
      // opened — so nothing it still delivers may land in the thread on screen. The turn
      // itself is the server's: only Stop ends it.
      const emit = (event: AgentEvent) => {
        if (controller.signal.aborted) return;
        said.last ||= endsTurn(event);
        onEvent(event);
      };
      try {
        await run(emit, controller.signal);
        if (controller.signal.aborted) return;
        dispatch({ type: "turn_finished" });
        // A stream that closed before its turn's last word says nothing of the turn: a
        // server told to go ends its streams so and the next one carries the turn on, or
        // the turn was stopped elsewhere. Its run is this tab's no more, so the server is
        // asked about it, as it is of any run this tab does not read.
        if (!said.last && !turnless()) setUnowned((n) => n + 1);
      } catch (error) {
        if (controller.signal.aborted) return;
        dispatch({ type: "failed", message: describe(error) });
        // What failed is this tab's reading. A turn the server did start goes on without it.
        setUnowned((n) => n + 1);
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [onEvent],
  );

  /** Carries out a decision. A 409 means someone got there first — another tab, Telegram
   *  or the expiry sweep — which is not the conversation being busy: saying so would send
   *  the person to wait for something already over. The thread is read again to show how
   *  far it has got, which also covers any load owed, and then says the request was
   *  handled; a run resumed elsewhere may still be going, so nothing is settled. */
  const decisionTurn = useCallback(
    async (run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      const opening = opened.current;
      let handled = false;
      await runTurn(
        async (emit, signal) => {
          try {
            await run(emit, signal);
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 409)) throw error;
            if (opening !== opened.current) return;
            handled = true;
            setOwed(false);
            setUnowned((n) => n + 1);
          }
        },
        undefined,
        // The refusal is counted above, where a Stop pressed meanwhile cannot leave it out.
        () => handled,
      );
      if (!handled) return;
      await reload();
      if (opening === opened.current) dispatch({ type: "handled" });
    },
    [runTurn, reload],
  );

  return { runTurn, decisionTurn };
}
