import { useCallback, type Dispatch, type MutableRefObject } from "react";
import type { MessageCanvas } from "../api/artifact-types";
import { api } from "../api/client";
import type { AgentEvent } from "../api/types";
import { vi } from "../i18n/vi";
import { turnErrorText } from "../lib/error-text";
import { settlement, type SendResult, type Settlement } from "../lib/send-result";
import type { ThreadAction } from "../state/thread-reducer";

/** What a send needs from the conversation it belongs to. */
interface SendParts {
  conversationId: string | null;
  /** This tab's own stream is running. */
  busy: boolean;
  dispatch: Dispatch<ThreadAction>;
  /** Runs a turn on this tab's own stream: busy while it lasts, cut by Stop, its errors
   *  put on screen as a notice, worded by `describe` when the caller knows better. */
  runTurn: (
    run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>,
    describe?: (error: unknown) => string,
  ) => Promise<void>;
  /** The queueing POSTs still in flight, each cut when the conversation is left. */
  queueing: MutableRefObject<Set<AbortController>>;
}

/**
 * Sends a message and answers as soon as the server says anything: the turn goes on after
 * that, and what the caller has to decide — are the words spent, or do they go back where
 * they were typed — is known by then.
 */
export function useThreadSend({ conversationId, busy, dispatch, runTurn, queueing }: SendParts) {
  /** This tab's own stream is running: a second POST joins the queue behind it without ever
   *  touching `runTurn`, `abortRef` or `turns` — the turn already on screen must keep
   *  receiving events and stay abortable by Stop exactly as if this send had not happened. */
  const queueBehindTurn = useCallback(
    async (id: string, text: string, answer: Settlement, canvas?: MessageCanvas) => {
      const controller = new AbortController();
      queueing.current.add(controller);
      try {
        await api.sendMessage(
          id,
          text,
          (event) => {
            if (event.type === "queued") dispatch({ type: "queued", item: { id: event.item_id, kind: event.kind, text } });
            answer.heard(event);
          },
          controller.signal,
          canvas,
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        // `queue_failed` only sets the notice, leaving `busy`, `streaming` and `items` exactly
        // as the running stream left them. The notice is worded as for any other send: the
        // server's own sentence when it wrote one, as a full queue does, and ours for what a
        // person cannot act on — a validation dump, a dropped connection — or for a canvas
        // selection, which the server words in English.
        const message = turnErrorText(error, canvas !== undefined);
        dispatch({ type: "queue_failed", message });
        answer.failed(error);
      } finally {
        answer.ended();
        queueing.current.delete(controller);
      }
    },
    [dispatch, queueing],
  );

  /** This tab believes the conversation is idle. It may still be busy somewhere this tab
   *  cannot see — another tab, a job, the schedule — in which case the server queues the
   *  message and this stream's only event is `queued`. */
  const startTurn = useCallback(
    async (id: string, text: string, answer: Settlement, canvas?: MessageCanvas) => {
      dispatch({ type: "user_sent", text });
      const describe = (error: unknown) => turnErrorText(error, canvas !== undefined);
      await runTurn(async (emit, signal) => {
        try {
          await api.sendMessage(
            id,
            text,
            (event) => {
              answer.heard(event);
              // Not passed on to the reducer's own `event` action: `applyEvent`'s `case
              // "queued"` is a documented no-op, since only this caller knows which text was
              // just sent and needs its temp bubble replaced with a chip.
              if (event.type === "queued") dispatch({ type: "queued", item: { id: event.item_id, kind: event.kind, text } });
              else emit(event);
            },
            signal,
            canvas,
          );
        } catch (error) {
          // Nothing the server said has reached this tab, so the message may never have got
          // there: its bubble goes and the words stay with whoever typed them. A cut-off —
          // Stop, or leaving the conversation — is no failure, and once the server has said
          // anything the bubble stays with the error `runTurn` puts beside it.
          if (!signal.aborted && !answer.done) {
            dispatch({ type: "user_unsent", text });
            answer.failed(error);
          }
          throw error;
        } finally {
          answer.ended();
        }
      }, describe);
    },
    [dispatch, runTurn],
  );

  return useCallback(
    (text: string, canvas?: MessageCanvas): Promise<SendResult> => {
      if (!conversationId) return Promise.resolve({ status: "failed", error: vi.sendFailed.other });
      const answer = settlement(canvas !== undefined);
      const go = busy ? queueBehindTurn : startTurn;
      void go(conversationId, text, answer, canvas);
      return answer.promise;
    },
    [conversationId, busy, queueBehindTurn, startTurn],
  );
}
