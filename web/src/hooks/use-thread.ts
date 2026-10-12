import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from "react";
import { api } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
import { turnErrorText } from "../lib/error-text";
import { sendNames, timesSaid } from "../lib/send-names";
import { emptyThread, threadReducer } from "../state/thread-reducer";
import type { ThreadController } from "./thread-controller";
import { withdrawDraft } from "./use-draft";
import { useThreadSend } from "./use-thread-send";
import { useThreadStop } from "./use-thread-stop";
import { useThreadTurn } from "./use-thread-turn";
import { useThreadWatch } from "./use-thread-watch";

export type { ThreadController } from "./thread-controller";

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // The stream in `abortRef` when it is a watch: a turn this tab reads but did not start.
  const watchRef = useRef<AbortController | null>(null);
  const [watching, setWatching] = useState(false);
  const turns = useRef(0);
  // Controllers for a queueing POST still in flight: a busy-send never touches `abortRef`,
  // since that would cut the turn actually running rather than the message trying to join
  // its queue. Switching conversation or unmounting cuts every one of these instead.
  const queueingRef = useRef(new Set<AbortController>());
  // Set for the run of a Stop call and cleared once it settles, so a second press while one
  // is still in flight can tell and skip the server call rather than sending it twice.
  const stoppingRef = useRef(false);
  const [owed, setOwed] = useState(false);
  const [unowned, setUnowned] = useState(0);
  const [stops, setStops] = useState(0);
  // A fresh object each time a conversation is opened: whatever answers for an opening
  // that is no longer the one on screen belongs to a thread the person has left.
  const opened = useRef<{ id: string | null }>({ id: null });
  // The names this tab's sends go out under. One the server may have taken is kept until the
  // thread shows its message as said. In that same commit the words the send handed back
  // leave the box, as they would have had the send been heard, so the page never shows a
  // message as said beside the offer to send it again. What is typed after that is new.
  const [names] = useState(sendNames);
  const onScreen = useRef(state);
  onScreen.current = state;
  /** How many times the thread on screen shows `text` as the person's. Nothing to count in
   *  until it is this conversation's stored thread that is on screen. */
  const said = useCallback(
    (text: string) => (onScreen.current.conversationId === conversationId ? timesSaid(onScreen.current, text) : null),
    [conversationId],
  );
  useLayoutEffect(() => {
    const id = state.conversationId;
    if (id === null) return;
    const words = names.shown(id, (text) => timesSaid(state, text));
    if (words !== null && withdrawDraft(id, words)) names.forget(id);
  }, [names, state]);

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
    setWatching(false);
    dispatch({ type: "opened" });
    void reload();
  }, [conversationId, reload]);

  useEffect(() => {
    if (!owed || state.busy) return;
    setOwed(false);
    void reload();
  }, [owed, state.busy, reload]);
  const reloadWhenIdle = useCallback(() => setOwed(true), []);

  const onEvent = useCallback((event: AgentEvent) => {
    if (event.type === "watching") {
      // The server hands over the conversation as it is stored now: a load still on its
      // way is older than that, and loads again once the turn is over.
      turns.current += 1;
      setDetail(event.detail);
    }
    dispatch({ type: "event", event });
  }, []);

  const { runTurn, decisionTurn } = useThreadTurn({
    abortRef,
    watchRef,
    turns,
    opened,
    dispatch,
    onEvent,
    reload,
    setOwed,
    setUnowned,
  });

  const send = useThreadSend({ conversationId, busy: state.busy, dispatch, runTurn, queueing: queueingRef, names, said });

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

  const watch = useThreadWatch({ conversationId, abortRef, watchRef, dispatch, onEvent, setWatching, setUnowned });

  const stop = useThreadStop({ conversationId, abortRef, watchRef, stoppingRef, dispatch, setStops, setUnowned });

  const settle = useCallback(() => dispatch({ type: "settled" }), []);
  const mutePreviews = useCallback(() => dispatch({ type: "previews_muted" }), []);

  return {
    state,
    detail,
    send,
    decide,
    answer,
    stop,
    watch,
    watching,
    reload,
    reloadWhenIdle,
    settle,
    mutePreviews,
    unowned,
    stops,
  };
}
