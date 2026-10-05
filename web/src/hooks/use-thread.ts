import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { MessageCanvas } from "../api/artifact-types";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail, StopResult } from "../api/types";
import { turnErrorText } from "../lib/error-text";
import type { SendResult } from "../lib/send-result";
import { emptyThread, threadReducer, type ThreadState } from "../state/thread-reducer";
import { useThreadSend } from "./use-thread-send";

/** How long Stop waits on the server before giving up and cutting the stream locally
 *  anyway. A `setTimeout` rather than `AbortSignal.timeout`, so a test can drive it with
 *  fake timers instead of waiting out a real three seconds. */
const STOP_WAIT_MS = 3000;

export interface ThreadController {
  state: ThreadState;
  detail: ConversationDetail | null;
  /** Sends `text` and says how that went the moment the server says anything — see
   *  `SendResult` — while the turn it starts goes on after that. Found busy, this tab's own
   *  stream or one this tab did not start, the message queues instead. `canvas` is the one
   *  open in this tab, which the server takes as the conversation's; left out, it keeps its own. */
  send: (text: string, canvas?: MessageCanvas) => Promise<SendResult>;
  /** `always` also whitelists the tool for the rest of this conversation. */
  decide: (approve: boolean, always?: boolean) => Promise<void>;
  /** Reply to a question the agent asked. Only a question row accepts this. */
  answer: (text: string) => Promise<void>;
  /** Tells the server to end the turn and hand back every message still queued, then cuts
   *  this tab's own stream if it has one; resolves with the cleared texts, oldest first, so
   *  the caller can put them back in the composer. `externalRunning` says whether a turn is
   *  known to be going somewhere this tab cannot reach, for the notice it may show. */
  stop: (externalRunning?: boolean) => Promise<string[]>;
  reload: () => Promise<void>;
  /** Loads again now, or once this tab's turn is over: a load mid-turn would drop it. */
  reloadWhenIdle: () => void;
  /** Marks calls no run will answer any more as stopped; a no-op while a turn runs. */
  settle: () => void;
  /** The person put away a canvas being written: none comes up by itself for the rest of the turn. */
  mutePreviews: () => void;
  /** Counts decisions refused as already taken elsewhere: each resumed nothing here. */
  handledElsewhere: number;
}

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const turns = useRef(0);
  // Controllers for a queueing POST still in flight: a busy-send never touches `abortRef`,
  // since that would cut the turn actually running rather than the message trying to join
  // its queue. Switching conversation or unmounting cuts every one of these instead.
  const queueingRef = useRef(new Set<AbortController>());
  // Set for the run of a Stop call and cleared once it settles, so a second press while one
  // is still in flight can tell and skip the server call rather than sending it twice.
  const stoppingRef = useRef(false);
  const [owed, setOwed] = useState(false);
  const [handledElsewhere, setHandledElsewhere] = useState(0);
  // A fresh object each time a conversation is opened: whatever answers for an opening
  // that is no longer the one on screen belongs to a thread the person has left.
  const opened = useRef<{ id: string | null }>({ id: null });

  const reload = useCallback(async () => {
    if (!conversationId) {
      setDetail(null);
      return;
    }
    const opening = opened.current;
    if (opening.id !== conversationId) return;
    // A turn begun while the load was on its way has put the person's message and its
    // stream on screen, which this older copy lacks: it loads again once the turn is over.
    const turn = turns.current;
    try {
      const loaded = await api.getConversation(conversationId);
      if (opening !== opened.current) return;
      if (turn !== turns.current) return setOwed(true);
      setDetail(loaded);
      dispatch({ type: "loaded", detail: loaded });
    } catch (error) {
      if (opening !== opened.current) return;
      if (turn !== turns.current) return setOwed(true);
      dispatch({ type: "failed", message: turnErrorText(error) });
    }
  }, [conversationId]);

  useEffect(() => {
    opened.current = { id: conversationId };
    abortRef.current?.abort();
    for (const controller of queueingRef.current) controller.abort();
    queueingRef.current.clear();
    setOwed(false);
    dispatch({ type: "opened" });
    void reload();
  }, [conversationId, reload]);

  useEffect(() => {
    if (!owed || state.busy) return;
    setOwed(false);
    void reload();
  }, [owed, state.busy, reload]);
  const reloadWhenIdle = useCallback(() => setOwed(true), []);

  const onEvent = useCallback((event: AgentEvent) => dispatch({ type: "event", event }), []);

  const runTurn = useCallback(
    async (
      run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>,
      describe: (error: unknown) => string = turnErrorText,
    ) => {
      const controller = new AbortController();
      abortRef.current = controller;
      turns.current += 1;
      dispatch({ type: "turn_started" });
      // An aborted turn has already been ended — by Stop, or by opening another
      // conversation — so nothing it still delivers may land in the thread on screen.
      const emit = (event: AgentEvent) => {
        if (!controller.signal.aborted) onEvent(event);
      };
      try {
        await run(emit, controller.signal);
        if (!controller.signal.aborted) dispatch({ type: "turn_finished" });
      } catch (error) {
        if (!controller.signal.aborted) dispatch({ type: "failed", message: describe(error) });
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
      await runTurn(async (emit, signal) => {
        try {
          await run(emit, signal);
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 409)) throw error;
          if (opening !== opened.current) return;
          handled = true;
          setOwed(false);
          setHandledElsewhere((n) => n + 1);
        }
      });
      if (!handled) return;
      await reload();
      if (opening === opened.current) dispatch({ type: "handled" });
    },
    [runTurn, reload],
  );

  const send = useThreadSend({ conversationId, busy: state.busy, dispatch, runTurn, queueing: queueingRef });

  const decide = useCallback(
    async (approve: boolean, always = false) => {
      const pending = state.pending;
      if (!conversationId || !pending) return;
      await decisionTurn((emit, signal) =>
        api.resolveApproval(conversationId, pending.approvalId, approve, emit, always && approve, signal),
      );
    },
    [conversationId, decisionTurn, state.pending],
  );

  const answer = useCallback(
    async (text: string) => {
      const pending = state.pending;
      if (!conversationId || !pending || pending.kind !== "question") return;
      await decisionTurn((emit, signal) =>
        api.answerApproval(conversationId, pending.approvalId, text, emit, signal),
      );
    },
    [conversationId, decisionTurn, state.pending],
  );

  /**
   * Stop. The server is told first — it alone knows the queue and can end a turn this tab
   * did not start — and only then is this tab's own stream cut, so a fast reply never races
   * the abort into unwinding before `queue_cleared` and `turn_stopped`/`elsewhere` are both
   * decided from the same server answer.
   *
   * A server that errors or does not answer within `STOP_WAIT_MS` still leaves the local
   * stream cut: the person asked to stop, and a slow or unreachable server is not a reason to
   * keep this tab's own view of the turn running. The chips stay in that case — they are
   * still sitting on the server, unconfirmed — so pressing Stop again is exactly the right
   * next move, and `waiting.length > 0` is what keeps the button around for it.
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
        const hadOwnStream = abortRef.current !== null;
        abortRef.current?.abort();
        if (result) {
          dispatch({ type: "queue_cleared" });
          if (hadOwnStream || result.cancelled) dispatch({ type: "turn_stopped" });
          else if (externalRunning) dispatch({ type: "elsewhere" });
          return result.cleared.map((c) => c.text);
        }
        if (hadOwnStream) dispatch({ type: "turn_stopped" });
        return [];
      } finally {
        stoppingRef.current = false;
      }
    },
    [conversationId],
  );

  const settle = useCallback(() => dispatch({ type: "settled" }), []);
  const mutePreviews = useCallback(() => dispatch({ type: "previews_muted" }), []);

  return { state, detail, send, decide, answer, stop, reload, reloadWhenIdle, settle, mutePreviews, handledElsewhere };
}
