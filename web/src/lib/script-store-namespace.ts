// What one namespace of an agent's script store is, in the words the screen uses for it.
//
// The server stores a namespace as `job:<schedule id>` or `conv:<conversation id>`, and since
// it describes one says which of the two it is, what the schedule or the conversation is
// called, and whether that owner is still there. A server older than that sends the stored
// name alone, and the stored name is then all the screen says.
import type { ScriptStoreNamespace } from "../api/script-store";
import { routeHash } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { showHiddenChars } from "./hidden-chars";

export interface NamespaceWords {
  /** Whose runs it belongs to, as a word; null when the server did not say. */
  kind: string | null;
  /** The schedule's name or the conversation's title; its id when it has neither; the
   *  stored name when the server said nothing more. */
  name: string;
  /** How a sentence calls it: `lịch "Bản tin sáng"`, or the stored name. */
  phrase: string;
  /** The job's row or the conversation, while there is one to open. */
  href: string | null;
  /** Its schedule or its conversation is gone, so nothing will read it again. */
  orphan: boolean;
  /** The sentence saying so. */
  orphanHint: string;
}

const { scriptStore: words } = vi;

/**
 * A name is whatever a person or an agent typed, so the characters nobody would see in it
 * are written out. The address is built from the id as the server sent it.
 */
export function namespaceWords(agentId: string, namespace: ScriptStoreNamespace): NamespaceWords {
  const stored = showHiddenChars(namespace.namespace);
  const orphan = namespace.orphan === true;
  const owned = namespace.kind === "job" || namespace.kind === "conv" ? namespace.kind : null;
  if (owned === null) {
    // "other", a kind this page does not know, or no kind at all: the stored name is the name.
    const kind = namespace.kind === undefined ? null : words.kinds.other;
    return { kind, name: stored, phrase: stored, href: null, orphan, orphanHint: words.orphanHint.other };
  }
  const ref = namespace.ref ?? "";
  const name = showHiddenChars((namespace.title ?? "").trim() || ref) || stored;
  const href =
    orphan || ref === ""
      ? null
      : owned === "job"
        ? // A job's row is named by its agent and its schedule (`scheduler/runner.py`).
          routeHash({ kind: "manage", section: "jobs", param: `${agentId}/${ref}` })
        : routeHash({ kind: "chat", conversationId: ref });
  return { kind: words.kinds[owned], name, phrase: words.named[owned](name), href, orphan, orphanHint: words.orphanHint[owned] };
}

/** `MetricBar` turns amber here and red at the limit; the sentence under it turns with it. */
const NEAR = 0.8;

export interface Fill {
  /** Keys plus values, over the most a namespace holds. */
  ratio: number;
  state: "room" | "near" | "full";
}

/** How full a namespace is, or null when the server names no limit to measure against. */
export function namespaceFill(chars: number, limit: number | undefined): Fill | null {
  if (limit === undefined || !(limit > 0)) return null;
  const ratio = chars / limit;
  return { ratio, state: ratio >= 1 ? "full" : ratio >= NEAR ? "near" : "room" };
}
