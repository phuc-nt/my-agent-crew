import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation, ConversationPatch } from "../api/types";

export interface ConversationsController {
  conversations: Conversation[];
  activeId: string | null;
  agentId: string | null;
  error: string | null;
  select: (id: string | null) => void;
  selectAgent: (id: string | null) => void;
  create: () => Promise<Conversation | null>;
  patch: (id: string, body: ConversationPatch) => Promise<void>;
  summarize: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

/** The sidebar's list (optionally scoped to one agent) plus which conversation is open. */
export function useConversations(): ConversationsController {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations(agentId ?? undefined));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [agentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectAgent = useCallback((id: string | null) => {
    setAgentId(id);
    setActiveId(null);
  }, []);

  const create = useCallback(async () => {
    try {
      const created = await api.createConversation(agentId ? { agent_id: agentId } : {});
      setConversations((list) => [created, ...list]);
      setActiveId(created.id);
      return created;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [agentId]);

  const patch = useCallback(async (id: string, body: ConversationPatch) => {
    const updated = await api.patchConversation(id, body);
    setConversations((list) => list.map((c) => (c.id === id ? updated : c)));
  }, []);

  /** Rewrites the recap of a conversation the user is looking at, on demand. */
  const summarize = useCallback(async (id: string) => {
    try {
      const { summary } = await api.summarizeConversation(id);
      setConversations((list) => list.map((c) => (c.id === id ? { ...c, summary } : c)));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteConversation(id);
    setConversations((list) => list.filter((c) => c.id !== id));
    setActiveId((current) => (current === id ? null : current));
  }, []);

  /** Open a conversation that may belong to another agent (from the attention center). */
  const select = useCallback(
    (id: string | null) => {
      if (id && !conversations.some((c) => c.id === id)) setAgentId(null);
      setActiveId(id);
    },
    [conversations],
  );

  return {
    conversations,
    activeId,
    agentId,
    error,
    select,
    selectAgent,
    create,
    patch,
    summarize,
    remove,
    refresh,
  };
}
