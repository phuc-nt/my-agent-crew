import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { api } from "../api/client";
import type { StopResult } from "../api/types";
import type { ThreadAction } from "../state/thread-reducer";

/** How long Stop waits on the server before giving up and cutting the stream locally
 *  anyway. A `setTimeout` rather than `AbortSignal.timeout`, so a test can drive it with
 *  fake timers instead of waiting out a real three seconds. */
const STOP_WAIT_MS = 3000;

/** What Stop needs from the thread it belongs to. */
interface StopParts {
  conversationId: string | null;
  abortRef: MutableRefObject<AbortController | null>;
  watchRef: MutableRefObject<AbortController | null>;
  stoppingRef: MutableRefObject<boolean>;
  dispatch: Dispatch<ThreadAction>;
  setStops: Dispatch<SetStateAction<number>>;
  setUnowned: Dispatch<SetStateAction<number>>;
}

export function useThreadStop({
  conversationId,
  abortRef,
  watchRef,
  stoppingRef,
  dispatch,
  setStops,
  setUnowned,
}: StopParts) {
  /**
   * Stop. The server is told first — it alone knows the queue and whether the turn is its
   * to end — and only then is this tab's stream cut, so a fast reply never races the abort
   * into unwinding before `queue_cleared` and `turn_stopped`/`elsewhere` are both decided
   * from the same server answer.
   *
   * A turn this tab only watches is cut when the server ended it. One the server could not
   * end — a bot's, a job's — goes on, and so does the watching, under a note saying so.
   *
   * A server that errors or does not answer within `STOP_WAIT_MS` still leaves the local
   * stream cut: the person asked to stop, and a slow or unreachable server is not a reason to
   * keep this tab's view of the turn running. The run is no longer put down to this tab, so
   * a turn found still going is watched again. The chips stay in that case — they are still
   * sitting on the server, unconfirmed — so pressing Stop again is exactly the right next
   * move, and `waiting.length > 0` is what keeps the button around for it.
   */
  const stop = useCallback(
    async (externalRunning = false) => {
      if (stoppingRef.current) return [];
      stoppingRef.current = true;
      try {
        if (!conversationId) return [];
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), STOP_WAIT_MS);
        let result: StopResult | null = null;
        try {
          result = await api.stopConversation(conversationId, controller.signal);
        } catch {
          result = null;
        } finally {
          clearTimeout(timer);
        }
        const reading = abortRef.current?.signal.aborted ? null : abortRef.current;
        const watched = reading !== null && reading === watchRef.current;
        if (result) {
          dispatch({ type: "queue_cleared" });
          if (result.cancelled || (reading !== null && !watched)) {
            reading?.abort();
            dispatch({ type: "turn_stopped" });
            if (result.cancelled) setStops((n) => n + 1);
          } else if (watched || externalRunning) dispatch({ type: "elsewhere" });
          return result.cleared.map((c) => c.text);
        }
        reading?.abort();
        if (reading !== null) {
          dispatch({ type: "turn_stopped" });
          setUnowned((n) => n + 1);
        }
        return [];
      } finally {
        stoppingRef.current = false;
      }
    },
    [conversationId],
  );

  return stop;
}
