import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation, ConversationPatch } from "../api/types";

export interface ConversationsController {
  conversations: Conversation[];
  activeId: string | null;
  error: string | null;
  select: (id: string | null) => void;
  create: () => Promise<Conversation | null>;
  patch: (id: string, body: ConversationPatch) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}

/** The sidebar's list plus which conversation is open. */
export function useConversations(): ConversationsController {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
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
      const created = await api.createConversation();
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

  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      setConversations((list) => list.filter((c) => c.id !== id));
      setActiveId((current) => (current === id ? null : current));
    },
    [],
  );

  return { conversations, activeId, error, select: setActiveId, create, patch, remove, refresh };
}
