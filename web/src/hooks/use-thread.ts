import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
import { vi } from "../i18n/vi";
import { emptyThread, threadReducer, type ThreadState } from "../state/thread-reducer";
import { errorText } from "../lib/error-text";

export interface ThreadController {
  state: ThreadState;
  detail: ConversationDetail | null;
  send: (text: string) => Promise<void>;
  /** `always` also whitelists the tool for the rest of this conversation. */
  decide: (approve: boolean, always?: boolean) => Promise<void>;
  /** Reply to a question the agent asked. Only a question row accepts this. */
  answer: (text: string) => Promise<void>;
  /** Cuts whichever stream is running — a message, a decision or an answer. */
  stop: () => void;
  reload: () => Promise<void>;
  /** Loads again now, or once this tab's turn is over: a load mid-turn would drop it. */
  reloadWhenIdle: () => void;
  /** Marks calls no run will answer any more as stopped; a no-op while a turn runs. */
  settle: () => void;
  /** Counts decisions refused as already taken elsewhere: each resumed nothing here. */
  handledElsewhere: number;
}

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const turns = useRef(0);
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
      dispatch({ type: "failed", message: describe(error) });
    }
  }, [conversationId]);

  useEffect(() => {
    opened.current = { id: conversationId };
    abortRef.current?.abort();
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
    async (run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
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

  const send = useCallback(
    async (text: string) => {
      if (!conversationId) return;
      dispatch({ type: "user_sent", text });
      await runTurn((emit, signal) => api.sendMessage(conversationId, text, emit, signal));
    },
    [conversationId, runTurn],
  );

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

  // Ends the turn on screen at once rather than when the aborted fetch unwinds: a stream
  // stuck on a dead connection may take its time to notice it was cut.
  const stop = useCallback(() => {
    const controller = abortRef.current;
    if (!controller) return;
    controller.abort();
    dispatch({ type: "turn_stopped" });
  }, []);

  const settle = useCallback(() => dispatch({ type: "settled" }), []);

  return { state, detail, send, decide, answer, stop, reload, reloadWhenIdle, settle, handledElsewhere };
}

function describe(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return vi.busyConflict;
  return errorText(error);
}
