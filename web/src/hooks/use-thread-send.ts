import { useCallback, useRef, type Dispatch, type MutableRefObject } from "react";
import type { MessageCanvas } from "../api/artifact-types";
import { api } from "../api/client";
import type { AgentEvent } from "../api/types";
import { vi } from "../i18n/vi";
import { turnErrorText } from "../lib/error-text";
import { newRequestId } from "../lib/request-id";
import { settlement, type SendResult, type Settlement } from "../lib/send-result";
import type { ThreadAction } from "../state/thread-reducer";

/** Whether the message names a passage of the canvas: only then is a 422 about the passage. A
 *  message that names the canvas alone, as the page's errors do, can be refused for nothing the
 *  person selected. */
const hasSelection = (canvas?: MessageCanvas): boolean => canvas?.selection != null;

/** A send the server was never heard to answer: it may have taken the message all the same. */
type Unheard = { conversationId: string; text: string; name: string };

/** What a send needs from the conversation it belongs to. */
interface SendParts {
  conversationId: string | null;
  /** This tab's own stream is running. */
  busy: boolean;
  dispatch: Dispatch<ThreadAction>;
  /** Runs a turn on this tab's own stream: busy while it lasts, cut by Stop, its errors
   *  put on screen as a notice, worded by `describe` when the caller knows better. `turnless`
   *  says, once the stream has closed, that the server answered with no turn on it. */
  runTurn: (
    run: (emit: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>,
    describe?: (error: unknown) => string,
    turnless?: () => boolean,
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
  // The last send that failed with nothing heard. The same words sent again to the same
  // conversation go under the same name, so a message that did arrive is not said twice:
  // the server answers with what became of it. Any other send is a new one.
  const unheard = useRef<Unheard | null>(null);
  const nameFor = useCallback((id: string, text: string) => {
    const last = unheard.current;
    unheard.current = null;
    return last !== null && last.conversationId === id && last.text === text ? last.name : newRequestId();
  }, []);

  /** This tab's own stream is running: a second POST joins the queue behind it without ever
   *  touching `runTurn`, `abortRef` or `turns` — the turn already on screen must keep
   *  receiving events and stay abortable by Stop exactly as if this send had not happened. */
  const queueBehindTurn = useCallback(
    async (id: string, text: string, name: string, answer: Settlement, canvas?: MessageCanvas) => {
      const controller = new AbortController();
      queueing.current.add(controller);
      try {
        await api.sendMessage(
          id,
          text,
          (event) => {
            if (event.type === "queued") dispatch({ type: "queued", item: { id: event.item_id, kind: event.kind, text } });
            answer.heard(event);
            // Anything else answers a send the server had already taken, with the turn on
            // screen as it stands: this tab reads that turn on its own stream already.
            if (event.type !== "queued") controller.abort();
          },
          controller.signal,
          canvas,
          name,
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        if (!answer.done) unheard.current = { conversationId: id, text, name };
        // `queue_failed` only sets the notice, leaving `busy`, `streaming` and `items` exactly
        // as the running stream left them. The notice is worded as for any other send: the
        // server's own sentence when it wrote one, as a full queue does, and ours for what a
        // person cannot act on — a validation dump, a dropped connection — or for a canvas
        // selection, which the server words in English.
        const message = turnErrorText(error, hasSelection(canvas));
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
    async (id: string, text: string, name: string, answer: Settlement, canvas?: MessageCanvas) => {
      dispatch({ type: "user_sent", text });
      const describe = (error: unknown) => turnErrorText(error, hasSelection(canvas));
      // The message was put in line: this stream reads no turn, and has said all it had to.
      let inLine = false;
      await runTurn(
        async (emit, signal) => {
          try {
            await api.sendMessage(
              id,
              text,
              (event) => {
                answer.heard(event);
                // Not passed on to the reducer's own `event` action: `applyEvent`'s `case
                // "queued"` is a documented no-op, since only this caller knows which text was
                // just sent and needs its temp bubble replaced with a chip.
                if (event.type === "queued") {
                  inLine = true;
                  dispatch({ type: "queued", item: { id: event.item_id, kind: event.kind, text } });
                } else emit(event);
              },
              signal,
              canvas,
              name,
            );
          } catch (error) {
            // Nothing the server said has reached this tab, so the message may never have got
            // there: its bubble goes and the words stay with whoever typed them. A cut-off —
            // Stop, or leaving the conversation — is no failure, and once the server has said
            // anything the bubble stays with the error `runTurn` puts beside it.
            if (!signal.aborted && !answer.done) {
              dispatch({ type: "user_unsent", text });
              answer.failed(error);
              unheard.current = { conversationId: id, text, name };
            }
            throw error;
          } finally {
            answer.ended();
          }
        },
        describe,
        () => inLine,
      );
    },
    [dispatch, runTurn],
  );

  return useCallback(
    (text: string, canvas?: MessageCanvas): Promise<SendResult> => {
      if (!conversationId) return Promise.resolve({ status: "failed", error: vi.sendFailed.other });
      const answer = settlement(hasSelection(canvas));
      const go = busy ? queueBehindTurn : startTurn;
      void go(conversationId, text, nameFor(conversationId, text), answer, canvas);
      return answer.promise;
    },
    [conversationId, busy, queueBehindTurn, startTurn, nameFor],
  );
}
