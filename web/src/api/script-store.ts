// What an agent's scripts keep between runs with `store(key, value)` and read back with
// `load(key)`, as `my_agent_crew/server/routes_script_store.py` lists it. Rows are held per
// agent, per namespace and per key; a value is JSON text.
import { request } from "./client";

/** Whose runs a namespace belongs to: a schedule's, a conversation's, or neither. */
export type ScriptStoreKind = "job" | "conv" | "other";

export interface ScriptStoreEntry {
  key: string;
  /** How the value's JSON text opens; the server ends it in "…" when it cut it short. */
  preview: string;
  /** How long the whole JSON text is, in characters. */
  chars: number;
  /** ISO, UTC. */
  updated_at: string;
}

export interface ScriptStoreNamespace {
  /** As stored: `job:<schedule id>` or `conv:<conversation id>`. */
  namespace: string;
  /** Keys plus values, in characters: what is measured against the limit. */
  chars: number;
  entries: ScriptStoreEntry[];
  // The four below say what the namespace is in words. A server older than them sends none,
  // and the namespace is then shown by its stored name alone.
  kind?: ScriptStoreKind;
  /** The schedule id or the conversation id, without its prefix. */
  ref?: string;
  /** The schedule's name or the conversation's title, when there is one. */
  title?: string | null;
  /** The schedule is no longer declared, or the conversation no longer exists. */
  orphan?: boolean;
}

export interface ScriptStoreInfo {
  /** The most one namespace holds, keys plus values. Absent from an older server. */
  limit_chars?: number;
  namespaces: ScriptStoreNamespace[];
}

/** One key's value, whole. */
export interface ScriptStoreValue {
  namespace: string;
  key: string;
  text: string;
  chars: number;
  updated_at: string;
}

const storePath = (agentId: string) => `/agents/${encodeURIComponent(agentId)}/script-store`;

/**
 * The query naming a namespace and, when given, one key in it.
 *
 * Written out rather than left to `query()`, which drops an empty value: a key that went
 * missing from a delete would name the whole namespace instead of one row of it.
 */
function named(namespace: string, key?: string): string {
  const search = new URLSearchParams({ namespace });
  if (key !== undefined) search.set("key", key);
  return `?${search.toString()}`;
}

export const scriptStoreApi = {
  list: (agentId: string) => request<ScriptStoreInfo>(storePath(agentId)),
  /** 404 when the key is no longer there. */
  value: (agentId: string, namespace: string, key: string) =>
    request<ScriptStoreValue>(`${storePath(agentId)}/value${named(namespace, key)}`),
  /** One key, or the whole namespace when no key is named. Answers how many rows went, and
   *  zero when nothing matched. */
  remove: (agentId: string, namespace: string, key?: string) =>
    request<{ deleted: number }>(`${storePath(agentId)}${named(namespace, key)}`, { method: "DELETE" }),
};
