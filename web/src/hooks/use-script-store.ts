import { useCallback, useEffect, useRef, useState } from "react";
import { type ScriptStoreInfo, type ScriptStoreValue, scriptStoreApi } from "../api/script-store";

export interface ScriptStoreController {
  /** What the agent's scripts keep; null until it has been read once. */
  store: ScriptStoreInfo | null;
  /** Why the last read failed, or null. A list read before that stays on screen. */
  failed: unknown;
  /** Reads the list again. */
  refresh(): Promise<void>;
  /** One key's value, whole, with how long it is and when it was written. Rejects with the
   *  request's error; a 404 means the key is gone. A value written since the list was read
   *  has the list read again, so the row beside the value is that same writing's. */
  value(namespace: string, key: string): Promise<ScriptStoreValue>;
  /** Deletes one key, or the whole namespace when no key is named, and answers how many rows
   *  the server took out. Rejects with the request's error, having changed nothing. */
  remove(namespace: string, key?: string): Promise<number>;
  /** Takes rows the server no longer has out of the list at once, then reads the list again
   *  for what else changed with them. */
  drop(namespace: string, key?: string): void;
}

/** The list without one key, or without a whole namespace. A namespace left with no key
 *  goes too: the server lists rows, and it has none for one that is empty. */
function without(store: ScriptStoreInfo, namespace: string, key?: string): ScriptStoreInfo {
  const namespaces = store.namespaces.flatMap((held) => {
    if (held.namespace !== namespace) return [held];
    if (key === undefined) return [];
    const gone = held.entries.find((entry) => entry.key === key);
    if (gone === undefined) return [held];
    const entries = held.entries.filter((entry) => entry !== gone);
    // A namespace is measured as its keys plus its values.
    return entries.length > 0 ? [{ ...held, entries, chars: held.chars - gone.key.length - gone.chars }] : [];
  });
  return { ...store, namespaces };
}

/**
 * What one agent's scripts keep between runs, read when the screen opens.
 *
 * It serves one agent for as long as it is mounted: the screen mounts another for another
 * agent, so nothing read for one agent is ever shown under the next one's name.
 */
export function useScriptStore(agentId: string): ScriptStoreController {
  const [store, setStore] = useState<ScriptStoreInfo | null>(null);
  const [failed, setFailed] = useState<unknown>(null);
  /** Counts the reads asked for: only the answer to the last one is taken. */
  const asked = useRef(0);

  const refresh = useCallback(async () => {
    asked.current += 1;
    const mine = asked.current;
    try {
      const read = await scriptStoreApi.list(agentId);
      if (mine !== asked.current) return;
      setStore(read);
      setFailed(null);
    } catch (error) {
      if (mine === asked.current) setFailed(error);
    }
  }, [agentId]);

  useEffect(() => {
    void refresh();
    // An answer that comes back after the screen closed is nobody's.
    return () => {
      asked.current += 1;
    };
  }, [refresh]);

  /** The list on screen, for an answer that lands between two renders; nothing once the
   *  screen closed. */
  const onScreen = useRef<ScriptStoreInfo | null>(null);
  useEffect(() => {
    onScreen.current = store;
    return () => {
      onScreen.current = null;
    };
  }, [store]);

  const value = useCallback(
    async (namespace: string, key: string) => {
      const read = await scriptStoreApi.value(agentId, namespace, key);
      const row = onScreen.current?.namespaces.find((held) => held.namespace === namespace)?.entries.find((entry) => entry.key === key);
      // Written again since the list was read: the row's size and time, the namespace's size
      // and its bar are still the earlier writing's, and only the list brings the new ones.
      if (row !== undefined && (row.chars !== read.chars || row.updated_at !== read.updated_at)) void refresh();
      return read;
    },
    [agentId, refresh],
  );

  const drop = useCallback(
    (namespace: string, key?: string) => {
      setStore((held) => (held === null ? held : without(held, namespace, key)));
      void refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (namespace: string, key?: string) => {
      const { deleted } = await scriptStoreApi.remove(agentId, namespace, key);
      drop(namespace, key);
      return deleted;
    },
    [agentId, drop],
  );

  return { store, failed, refresh, value, remove, drop };
}
