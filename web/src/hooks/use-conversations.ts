import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation, ConversationPatch } from "../api/types";

/** The sidebar is the person's chat with the master; the rest of the crew is reached through it. */
export const MASTER_ID = "default";

export interface ConversationsController {
  conversations: Conversation[];
  activeId: string | null;
  error: string | null;
  /** Opens a conversation; one outside the list (a delegate's) still opens, it is just not listed. */
  select: (id: string | null) => void;
  create: () => Promise<Conversation | null>;
  patch: (id: string, body: ConversationPatch) => Promise<void>;
  summarize: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useConversations(): ConversationsController {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations(MASTER_ID));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async () => {
    try {
      const created = await api.createConversation({ agent_id: MASTER_ID });
      setConversations((list) => [created, ...list]);
      setActiveId(created.id);
      return created;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, []);

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

  const select = useCallback((id: string | null) => setActiveId(id), []);

  return { conversations, activeId, error, select, create, patch, summarize, remove, refresh };
}
