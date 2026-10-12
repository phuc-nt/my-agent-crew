import { type RefObject, useEffect, useRef, useState } from "react";
import type { ScriptStoreEntry, ScriptStoreNamespace } from "../api/script-store";
import type { AgentInfo } from "../api/types";
import { useScriptStore } from "../hooks/use-script-store";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";
import { quotedName } from "../lib/quoted-name";
import { namespaceWords } from "../lib/script-store-namespace";
import { EmptyState } from "./empty-state";
import { type RefusedDelete, ScriptStoreNamespaceCard } from "./script-store-namespace";
import { Icon } from "./ui/icon";

const { scriptStore: words } = vi;

interface Props {
  agents: AgentInfo[];
  agentId: string;
  onSelectAgent(agentId: string): void;
}

/**
 * What an agent's scripts keep from one run to the next (`store(key, value)`, read back
 * with `load(key)`): every namespace the chosen agent has, with its keys.
 *
 * It sits among the things the crew remembers because it is one of them: beside an agent's
 * MEMORY.md and its wiki, this is the third thing an agent holds between turns, and like
 * those two it is read one agent at a time.
 */
export function ScriptStoreSection({ agents, agentId, onSelectAgent }: Props) {
  const select = useRef<HTMLSelectElement>(null);
  return (
    <div className="script-store" data-testid="script-store">
      <label>
        {vi.agents}
        <select ref={select} value={agentId} onChange={(event) => onSelectAgent(event.currentTarget.value)}>
          {/* An agent named in the address that the crew does not list is still the one shown. */}
          {!agents.some((agent) => agent.id === agentId) && <option value={agentId}>{agentId}</option>}
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>
      <p className="muted script-store-intro">{words.intro}</p>
      {/* One per agent: nothing read for one agent is ever shown under the next one's name. */}
      <ScriptStoreList key={agentId} agentId={agentId} fallback={select} />
    </div>
  );
}

/** What a delete names: one key, or a whole namespace when no key is given. An empty key
 *  is a key. */
const target = (namespace: string, key?: string) => JSON.stringify([namespace, key ?? null]);

/** Rows that just left the list: which namespace, where it stood, and where the key stood
 *  in it when one key went and not the whole namespace. */
type Gone = { namespace: string; namespaceAt: number; entryAt?: number };

/**
 * A delete is asked about first, naming the key, or how many keys go with a namespace.
 * That number is counted on the server as it is when asked, so the list is read again first:
 * a script may have written since the list on screen was read. It takes away the row the keyboard was on. The keyboard then goes to the key that
 * took its place, to the last key when none did, and once the namespace is empty to the
 * heading of the namespace that took its place, of the last one, or to the agent's select.
 * A line says what went. A person who took the keyboard elsewhere while the server was
 * answering keeps it there, and a delete the server refused moves nothing.
 */
function ScriptStoreList({ agentId, fallback }: { agentId: string; fallback: RefObject<HTMLElement | null> }) {
  const { store, failed, refresh, reread, value, remove, drop } = useScriptStore(agentId);
  const root = useRef<HTMLDivElement>(null);
  /** The deletes the server has not answered yet, by what each names. */
  const deleting = useRef(new Set<string>());
  const [said, setSaid] = useState("");
  const [refused, setRefused] = useState<RefusedDelete | null>(null);
  const [gone, setGone] = useState<Gone | null>(null);

  // Runs once the rows are out of the page, which leaves a keyboard that was on one nowhere.
  useEffect(() => {
    if (gone === null || document.activeElement !== document.body) return;
    const cards = [...(root.current?.querySelectorAll<HTMLElement>(".script-store-namespace") ?? [])];
    const same = cards.find((card) => card.dataset.namespace === gone.namespace);
    const keys = gone.entryAt === undefined ? undefined : same?.querySelectorAll<HTMLElement>(".script-store-view");
    const key = keys?.[Math.min(gone.entryAt ?? 0, keys.length - 1)];
    const card = same ?? cards[Math.min(gone.namespaceAt, cards.length - 1)];
    (key ?? card?.querySelector<HTMLElement>(".script-store-heading") ?? fallback.current)?.focus();
  }, [gone, fallback]);

  /** The namespace as the server has it now, with how a sentence names it; undefined when
   *  it has none by that name any more, null when the screen closed while it was read. */
  const asItIsNow = async (namespace: string) => {
    const now = await reread();
    if (now === null) return null;
    const fresh = now.namespaces.find((it) => it.namespace === namespace);
    return fresh && { keys: fresh.entries.length, where: namespaceWords(agentId, fresh).phrase };
  };

  const onDelete = async (held: ScriptStoreNamespace, at: number, shown: string, entry?: ScriptStoreEntry, entryAt?: number) => {
    const whole = target(held.namespace);
    const mine = target(held.namespace, entry?.key);
    // Pressed again before this press is settled, or a key of a namespace that is being asked
    // about or is going whole: nobody is asked to agree a second time.
    if (deleting.current.has(mine) || deleting.current.has(whole)) return;
    // Taken before the first wait, so a press that comes during it finds it taken.
    deleting.current.add(mine);
    try {
      // A key is whatever a script chose: it goes into the question, and into the line that
      // says what went, between quotes and on one line.
      const key = entry && quotedName(entry.key);
      let where = shown;
      let question: string;
      if (key !== undefined) question = words.deleteKeyConfirm(key, where);
      else {
        const fresh = await asItIsNow(held.namespace);
        if (fresh === null) return;
        if (fresh === undefined) {
          // Gone since the list was read: nothing is left to ask about, or to delete.
          setRefused(null);
          setSaid(words.nothingDeleted);
          setGone({ namespace: held.namespace, namespaceAt: at });
          return;
        }
        where = fresh.where;
        question = words.deleteAllConfirm(fresh.keys, where);
      }
      if (!window.confirm(question)) return;
      setRefused(null);
      setSaid("");
      const deleted = await remove(held.namespace, entry?.key);
      if (deleted === 0) setSaid(words.nothingDeleted);
      else setSaid(key === undefined ? words.deletedAll(deleted, where) : words.deletedKey(key));
      setGone({ namespace: held.namespace, namespaceAt: at, entryAt });
    } catch (error) {
      setSaid("");
      setRefused({ namespace: held.namespace, key: entry?.key, text: errorText(error) });
    } finally {
      deleting.current.delete(mine);
    }
  };

  const onGone = (held: ScriptStoreNamespace, at: number, entry: ScriptStoreEntry, entryAt: number) => {
    setRefused(null);
    setSaid(words.gone(quotedName(entry.key)));
    drop(held.namespace, entry.key);
    setGone({ namespace: held.namespace, namespaceAt: at, entryAt });
  };

  return (
    <div className="script-store-list" ref={root}>
      {/* There from the start: a screen reader hears a line it knows fill, and may miss a new one. */}
      <p className="muted script-store-said" role="status">
        {said}
      </p>
      {failed !== null && (
        <div className="notice error script-store-notice" role="alert">
          <Icon name="alert" />
          <span>{errorText(failed)}</span>
          <button type="button" className="link-button" onClick={() => void refresh()}>
            {vi.retry}
          </button>
        </div>
      )}
      {store === null && failed === null && <p className="muted">{vi.loading}</p>}
      {store?.namespaces.length === 0 && <EmptyState says={words.empty} />}
      {store?.namespaces.map((held, at) => (
        <ScriptStoreNamespaceCard
          key={held.namespace}
          agentId={agentId}
          namespace={held}
          limit={store.limit_chars}
          refused={refused}
          onRead={(key) => value(held.namespace, key)}
          onGone={(entry, entryAt) => onGone(held, at, entry, entryAt)}
          onDelete={(where, entry, entryAt) => void onDelete(held, at, where, entry, entryAt)}
        />
      ))}
    </div>
  );
}
