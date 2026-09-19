import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AgentEvent, ConversationDetail } from "../api/types";
import { vi } from "../i18n/vi";
import { emptyThread, threadReducer, type ThreadState } from "../state/thread-reducer";

export interface ThreadController {
  state: ThreadState;
  detail: ConversationDetail | null;
  send: (text: string) => Promise<void>;
  decide: (approve: boolean) => Promise<void>;
  stop: () => void;
  reload: () => Promise<void>;
}

/** Owns one conversation: loads its history, streams turns, resolves approvals. */
export function useThread(conversationId: string | null): ThreadController {
  const [state, dispatch] = useReducer(threadReducer, emptyThread);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    if (!conversationId) {
      setDetail(null);
      return;
    }
    try {
      const loaded = await api.getConversation(conversationId);
      setDetail(loaded);
      dispatch({ type: "loaded", detail: loaded });
    } catch (error) {
      dispatch({ type: "failed", message: describe(error) });
    }
  }, [conversationId]);

  useEffect(() => {
    abortRef.current?.abort();
    dispatch({ type: "loaded", detail: blankDetail(conversationId) });
    void reload();
  }, [conversationId, reload]);

  const onEvent = useCallback((event: AgentEvent) => dispatch({ type: "event", event }), []);

  const runTurn = useCallback(
    async (run: (onEvent: (e: AgentEvent) => void, signal: AbortSignal) => Promise<void>) => {
      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: "turn_started" });
      try {
        await run(onEvent, controller.signal);
        dispatch({ type: "turn_finished" });
      } catch (error) {
        if (controller.signal.aborted) dispatch({ type: "turn_finished" });
        else dispatch({ type: "failed", message: describe(error) });
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [onEvent],
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
    async (approve: boolean) => {
      const pending = state.pending;
      if (!conversationId || !pending) return;
      await runTurn((emit) => api.resolveApproval(conversationId, pending.approvalId, approve, emit));
    },
    [conversationId, runTurn, state.pending],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return { state, detail, send, decide, stop, reload };
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
    title: "",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 0,
    skills: [],
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    messages: [],
    pending_approval: null,
  };
}
