import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
import { vi } from "../i18n/vi";
import { emptyThread, threadReducer, type ThreadState } from "../state/thread-reducer";

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
  /** Marks calls no run will answer any more as stopped; a no-op while a turn runs. */
  settle: () => void;
}

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const turns = useRef(0);
  const [owed, setOwed] = useState(false);

  const reload = useCallback(async () => {
    if (!conversationId) {
      setDetail(null);
      return;
    }
    // A turn begun while the load was on its way has put the person's message and its
    // stream on screen, which this older copy lacks: it loads again once the turn is over.
    const turn = turns.current;
    try {
      const loaded = await api.getConversation(conversationId);
      if (turn !== turns.current) return setOwed(true);
      setDetail(loaded);
      dispatch({ type: "loaded", detail: loaded });
    } catch (error) {
      if (turn !== turns.current) return setOwed(true);
      dispatch({ type: "failed", message: describe(error) });
    }
  }, [conversationId]);

  useEffect(() => {
    abortRef.current?.abort();
    setOwed(false);
    dispatch({ type: "loaded", detail: blankDetail(conversationId) });
    void reload();
  }, [conversationId, reload]);

  useEffect(() => {
    if (!owed || state.busy) return;
    setOwed(false);
    void reload();
  }, [owed, state.busy, reload]);

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
   *  it ended, and then says the request was handled. */
  const decisionTurn = useCallback(
    async (run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      let handledElsewhere = false;
      await runTurn(async (emit, signal) => {
        try {
          await run(emit, signal);
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 409)) throw error;
          handledElsewhere = true;
        }
      });
      if (!handledElsewhere) return;
      await reload();
      dispatch({ type: "failed", message: vi.attentionHandled });
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

  return { state, detail, send, decide, answer, stop, reload, settle };
}

function describe(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return vi.busyConflict;
  if (error instanceof Error) return error.message;
  return String(error);
}

function blankDetail(id: string | null): ConversationDetail {
  return {
    id: id ?? "",
    agent_id: "default",
    channel: "",
    title: "",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 0,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    messages: [],
    pending_approval: null,
  };
}
