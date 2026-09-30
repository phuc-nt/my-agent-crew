import { useCallback, useState } from "react";
import { api } from "../api/client";
import { vi } from "../i18n/vi";
import { itemsFromMessages, type ThreadItem } from "../state/thread-reducer";
import { saveDraft } from "./use-draft";

type UserItem = ThreadItem & { kind: "user" };

/** A number id from the server as a plain digit string; a bubble the send call has not
 *  had a chance to reload since still carries its optimistic `local-N` placeholder — see
 *  `use-thread.ts`, which does not reload after a turn it started itself. */
function isServerId(id: string): boolean {
  return /^\d+$/.test(id);
}

/** How far `item` sits from the end among every user bubble in `items`: 0 for the most
 *  recent one, 1 for the one before it, and so on. Matched against the same count run on
 *  a freshly fetched history, since a `local-N` id names a position, not a row. */
function fromEnd(items: readonly ThreadItem[], item: ThreadItem): number {
  const users = items.filter((i): i is UserItem => i.kind === "user");
  return users.length - 1 - users.indexOf(item as UserItem);
}

/** The real message id `item` was rendered from: `item.id` itself when the server already
 *  gave it one, or the id at the same from-the-end position in a freshly read history when
 *  it is still the optimistic `local-N` a send has not been reloaded past yet. Returns
 *  `null` without saying why — a mismatched position is not distinguished from a network
 *  failure, since the caller reports both the same way. */
async function resolveMessageId(conversationId: string, item: UserItem, items: readonly ThreadItem[]): Promise<number | null> {
  if (isServerId(item.id)) return Number(item.id);
  const detail = await api.getConversation(conversationId);
  const users = itemsFromMessages(detail.messages).filter((i): i is UserItem => i.kind === "user");
  const at = users.length - 1 - fromEnd(items, item);
  const candidate = users[at];
  if (candidate === undefined || candidate.text !== item.text) return null;
  return Number(candidate.id);
}

export interface UseForkOptions {
  /** Reloads the conversation list so the fork appears in it before it is selected. */
  refresh: () => Promise<void>;
  /** Puts the fork in the address bar and opens it, the same as picking it from the list. */
  onSelectConversation: (conversationId: string) => void;
}

export interface ForkController {
  /** Resolves `item`'s real message id, asks the server to fork at it, and — on success —
   *  seeds the fork's draft, refreshes the list and opens it. Returns whether it worked;
   *  a resolution mismatch never reaches the server at all. */
  fork: (conversationId: string, item: ThreadItem, items: readonly ThreadItem[]) => Promise<boolean>;
  error: string | null;
}

/** "Sửa và gửi lại từ đây": rewind and fork a conversation at a saved user message. */
export function useFork({ refresh, onSelectConversation }: UseForkOptions): ForkController {
  const [error, setError] = useState<string | null>(null);

  const fork = useCallback(
    async (conversationId: string, item: ThreadItem, items: readonly ThreadItem[]) => {
      if (item.kind !== "user") return false;
      try {
        const beforeMessageId = await resolveMessageId(conversationId, item, items);
        if (beforeMessageId === null) {
          setError(vi.fork.failed);
          return false;
        }
        const result = await api.forkConversation(conversationId, beforeMessageId);
        saveDraft(result.id, result.draft);
        await refresh();
        onSelectConversation(result.id);
        setError(null);
        return true;
      } catch {
        // Same generic message as a resolution mismatch: neither is something retrying
        // with the exact same click would fix, and the raw error is a server detail the
        // person cannot act on.
        setError(vi.fork.failed);
        return false;
      }
    },
    [refresh, onSelectConversation],
  );

  return { fork, error };
}
