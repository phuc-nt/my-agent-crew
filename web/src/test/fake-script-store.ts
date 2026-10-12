// The script-store routes as both fakes answer them, so the screen is tested against one set
// of rules.
//
// It mirrors `server/routes_script_store.py`: namespaces in name order and keys in key order,
// a value as compact JSON text, a preview of its first 200 characters ending in "…" when cut,
// a namespace measured as its keys plus its values, an unknown agent as a 404, and a delete
// that matched nothing as a 200 with `deleted: 0`.
import type { ScriptStoreEntry, ScriptStoreInfo, ScriptStoreKind, ScriptStoreNamespace } from "../api/script-store";

export type ScriptStoreReply = { status: number; body: unknown };

type Kept = { text: string; updatedAt: string };
type Refusal = { status: number; detail: string };

const PREVIEW_CHARS = 200;
const KEPT_AT = "2026-10-12T01:00:00+00:00";

export class FakeScriptStore {
  /** The most one namespace holds, keys plus values (`script/limits.py`). */
  limitChars = 262_144;
  /** Answer as the server did before it said what a namespace is: no limit, and a
   *  namespace as its stored name, its size and its entries. */
  old = false;
  /** Whether the crew has this agent. Each fake points it at its own crew. */
  knownAgent: (agentId: string) => boolean = () => true;
  /** The schedule a `job:` namespace names, or nothing once the agent stopped declaring it. */
  schedule: (agentId: string, scheduleId: string) => { name: string } | undefined = () => undefined;
  /** The conversation a `conv:` namespace names, or nothing once it is deleted. */
  conversation: (conversationId: string) => { title: string } | undefined = () => undefined;
  /** What a kind of request is refused with, for as long as a test leaves it set. */
  refuse: { list?: Refusal; value?: Refusal; remove?: Refusal } = {};
  /** agent → namespace → key → what is kept. */
  private kept = new Map<string, Map<string, Map<string, Kept>>>();

  /** Keeps a value the way `store(key, value)` does: as compact JSON text. */
  keep(agentId: string, namespace: string, key: string, value: unknown, updatedAt = KEPT_AT): this {
    return this.keepText(agentId, namespace, key, JSON.stringify(value), updatedAt);
  }

  /** Keeps a text as it is given, JSON or not. */
  keepText(agentId: string, namespace: string, key: string, text: string, updatedAt = KEPT_AT): this {
    const namespaces = this.kept.get(agentId) ?? new Map<string, Map<string, Kept>>();
    const keys = namespaces.get(namespace) ?? new Map<string, Kept>();
    keys.set(key, { text, updatedAt });
    namespaces.set(namespace, keys);
    this.kept.set(agentId, namespaces);
    return this;
  }

  /** The keys a namespace holds now, in key order; none when the namespace is gone. */
  keys(agentId: string, namespace: string): string[] {
    return [...(this.kept.get(agentId)?.get(namespace)?.keys() ?? [])].sort();
  }

  /** Answers one of the three routes, or nothing for a path that is not the store's. */
  route(path: string, method: string, params: URLSearchParams): ScriptStoreReply | null {
    const match = path.match(/^\/agents\/([^/]+)\/script-store(\/value)?$/);
    if (!match) return null;
    const agentId = decodeURIComponent(match[1]);
    const what = match[2] ? "value" : method === "DELETE" ? "remove" : "list";
    if (what === "value" ? method !== "GET" : method !== "GET" && method !== "DELETE") {
      return { status: 405, body: { detail: "Method Not Allowed" } };
    }
    const refused = this.refuse[what];
    if (refused) return { status: refused.status, body: { detail: refused.detail } };
    if (!this.knownAgent(agentId)) return { status: 404, body: { detail: "agent not found" } };
    const namespaces = this.kept.get(agentId) ?? new Map<string, Map<string, Kept>>();
    if (what === "list") return { status: 200, body: this.listed(agentId, namespaces) };

    const namespace = params.get("namespace");
    const key = params.get("key");
    if (namespace === null || (what === "value" && key === null)) {
      return { status: 422, body: { detail: [{ type: "missing", loc: ["query", namespace === null ? "namespace" : "key"] }] } };
    }
    const keys = namespaces.get(namespace);
    if (what === "value") {
      const found = keys?.get(key as string);
      if (!found) return { status: 404, body: { detail: "key not found" } };
      return { status: 200, body: { namespace, key, text: found.text, chars: found.text.length, updated_at: found.updatedAt } };
    }
    if (!keys) return { status: 200, body: { deleted: 0 } };
    if (key === null) {
      namespaces.delete(namespace);
      return { status: 200, body: { deleted: keys.size } };
    }
    const deleted = keys.delete(key) ? 1 : 0;
    // The table holds rows, not namespaces: one with no row left is not listed again.
    if (keys.size === 0) namespaces.delete(namespace);
    return { status: 200, body: { deleted } };
  }

  private listed(agentId: string, namespaces: Map<string, Map<string, Kept>>): ScriptStoreInfo {
    const listed = [...namespaces.keys()].sort().map((namespace): ScriptStoreNamespace => {
      const keys = namespaces.get(namespace) as Map<string, Kept>;
      const entries = [...keys.keys()].sort().map((key): ScriptStoreEntry => {
        const { text, updatedAt } = keys.get(key) as Kept;
        const preview = text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS)}…` : text;
        return { key, preview, chars: text.length, updated_at: updatedAt };
      });
      const chars = entries.reduce((sum, entry) => sum + entry.key.length + entry.chars, 0);
      if (this.old) return { namespace, chars, entries };
      return { namespace, ...this.described(agentId, namespace), chars, entries };
    });
    return this.old ? { namespaces: listed } : { limit_chars: this.limitChars, namespaces: listed };
  }

  /** What a namespace is, in the four fields the server adds to its stored name. */
  private described(agentId: string, namespace: string) {
    const [prefix, ...rest] = namespace.split(":");
    const kind: ScriptStoreKind = rest.length === 0 ? "other" : prefix === "job" ? "job" : prefix === "conv" ? "conv" : "other";
    if (kind === "other") return { kind, ref: namespace, title: null, orphan: false };
    const ref = rest.join(":");
    const owner = kind === "job" ? this.schedule(agentId, ref)?.name : this.conversation(ref)?.title;
    return { kind, ref, title: owner || null, orphan: owner === undefined };
  }
}
