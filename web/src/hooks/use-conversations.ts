import { useCallback, useEffect, useRef, useState } from "react";
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
  /** Takes a conversation the server pushed — a title written in the background — into the list. */
  applyUpdate: (conversation: Conversation) => void;
}

export function useConversations(): ConversationsController {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Updates the stream pushed, kept by id with the number of list fetches that had been
  // started when each arrived. The stream can beat a fetch that is still in flight, and
  // that fetch would otherwise answer with the title it pushed past.
  const pushed = useRef(new Map<string, { at: number; conversation: Conversation }>());
  const fetches = useRef(0);

  const refresh = useCallback(async () => {
    const started = ++fetches.current;
    try {
      const listed = await api.listConversations(MASTER_ID);
      // An update is spent once a fetch that began after it has answered: only such a
      // fetch can have seen it, so only then is the server the newer source. Fetches
      // already in flight when it arrived carry the older row and must not retire it —
      // two of them overlap on every load, StrictMode's pair being the common case.
      // Pruned before the merge, so this answer already reflects what it retires.
      for (const [id, entry] of pushed.current) {
        if (entry.at < started) pushed.current.delete(id);
      }
      setConversations(listed.map((c) => pushed.current.get(c.id)?.conversation ?? c));
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
    // Whatever the stream pushed about this row is now older than what was just sent;
    // keeping it would let the next refresh put the previous name back.
    pushed.current.delete(id);
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

  /** Replaces the row in place. A conversation belonging to another agent — a delegate's
   *  child — is not part of this list and is ignored rather than appended to it. */
  const applyUpdate = useCallback((conversation: Conversation) => {
    if (conversation.agent_id !== MASTER_ID) return;
    // A row not in the list yet is one the in-flight fetch will bring; remembering the
    // update here is what keeps that fetch from answering with the older title.
    pushed.current.set(conversation.id, { at: fetches.current, conversation });
    setConversations((list) => list.map((c) => (c.id === conversation.id ? conversation : c)));
  }, []);

  return {
    conversations,
    activeId,
    error,
    select,
    create,
    patch,
    summarize,
    remove,
    refresh,
    applyUpdate,
  };
}
