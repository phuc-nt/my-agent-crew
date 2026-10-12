import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { api } from "../api/client";
import type { AgentEvent } from "../api/types";
import type { ThreadAction } from "../state/thread-reducer";

/** What reading along with a turn needs from the thread it belongs to. */
interface WatchParts {
  conversationId: string | null;
  abortRef: MutableRefObject<AbortController | null>;
  watchRef: MutableRefObject<AbortController | null>;
  dispatch: Dispatch<ThreadAction>;
  onEvent: (event: AgentEvent) => void;
  setWatching: Dispatch<SetStateAction<boolean>>;
  setUnowned: Dispatch<SetStateAction<number>>;
}

export function useThreadWatch({
  conversationId,
  abortRef,
  watchRef,
  dispatch,
  onEvent,
  setWatching,
  setUnowned,
}: WatchParts) {
  const watch = useCallback(async () => {
    if (!conversationId) return false;
    if (abortRef.current && !abortRef.current.signal.aborted) return true;
    const controller = new AbortController();
    abortRef.current = watchRef.current = controller;
    let attached = false;
    try {
      const found = await api.watchTurn(
        conversationId,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.type === "watching" && !attached) {
            attached = true;
            setWatching(true);
            setUnowned((n) => n + 1);
          }
          onEvent(event);
        },
        controller.signal,
      );
      return found || controller.signal.aborted;
    } catch {
      // The view of the turn was lost, not the turn: nothing here to tell the person.
      return attached || controller.signal.aborted;
    } finally {
      // However the stream ended, nothing more of the turn reaches this tab through it. One
      // ended without a last event was stopped elsewhere, or lost: its calls stop spinning.
      if (attached && !controller.signal.aborted) dispatch({ type: "turn_finished" });
      if (abortRef.current === controller) abortRef.current = null;
      if (watchRef.current === controller) {
        watchRef.current = null;
        setWatching(false);
      }
    }
  }, [conversationId, onEvent]);

  return watch;
}
