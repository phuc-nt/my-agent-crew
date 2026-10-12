import type { ScriptStoreEntry, ScriptStoreNamespace } from "../api/script-store";
import { vi } from "../i18n/vi";
import { showHiddenChars } from "../lib/hidden-chars";
import { namespaceFill, namespaceWords } from "../lib/script-store-namespace";
import { ScriptStoreEntryRow } from "./script-store-entry";
import { MetricBar } from "./ui/metric-card";

const { scriptStore: words } = vi;

/** A delete the server refused: where it was asked, and the sentence to show there. */
export interface RefusedDelete {
  namespace: string;
  /** The key, or nothing when the whole namespace was to go. */
  key?: string;
  text: string;
}

interface Props {
  agentId: string;
  namespace: ScriptStoreNamespace;
  /** The most a namespace holds; absent when the server names none. */
  limit: number | undefined;
  refused: RefusedDelete | null;
  onRead(key: string): Promise<string>;
  onGone(entry: ScriptStoreEntry, at: number): void;
  /** One key when an entry is named, every key of the namespace otherwise. `where` is how
   *  a sentence names the namespace, for the question asked first and the line that says
   *  what went. */
  onDelete(where: string, entry?: ScriptStoreEntry, at?: number): void;
}

/**
 * One namespace of an agent's script store: whose runs it belongs to in words, with a way
 * to that schedule or conversation while it exists, the name it is stored under, how full
 * it is against the most it holds, and its keys.
 *
 * A namespace whose schedule or conversation is gone is marked: nothing will read it again,
 * and the mark says it can be deleted.
 */
export function ScriptStoreNamespaceCard({ agentId, namespace, limit, refused, onRead, onGone, onDelete }: Props) {
  const said = namespaceWords(agentId, namespace);
  const fill = namespaceFill(namespace.chars, limit);
  const stored = showHiddenChars(namespace.namespace);
  const mine = refused?.namespace === namespace.namespace ? refused : null;
  return (
    <section className="script-store-namespace" data-testid="script-store-namespace" data-namespace={namespace.namespace}>
      <div className="script-store-namespace-head">
        {/* Takes the keyboard when the namespace it stood under is deleted. */}
        <h3 className="script-store-heading" tabIndex={-1}>
          {said.kind !== null && <span className="script-store-kind">{said.kind}</span>}
          {said.href !== null ? (
            <a className="script-store-name" href={said.href}>
              {said.name}
            </a>
          ) : (
            <span className="script-store-name">{said.name}</span>
          )}
        </h3>
        {said.orphan && <span className="badge warn">{words.orphan}</span>}
        <button
          type="button"
          className="danger script-store-delete-all"
          aria-label={words.deleteAllLabel(said.phrase)}
          onClick={() => onDelete(said.phrase)}
        >
          {words.deleteAll}
        </button>
      </div>
      {/* The stored name stays in sight beside a name in words: the table knows it by no other. */}
      {said.name !== stored && <code className="script-store-stored">{stored}</code>}
      {said.orphan && <p className="script-store-orphan-hint">{said.orphanHint}</p>}
      <div className="script-store-size">
        <span className="muted tabular">
          {words.keyCount(namespace.entries.length)}
          {" · "}
          {fill === null || limit === undefined ? words.sizeAlone(namespace.chars) : words.size(namespace.chars, limit)}
        </span>
        {fill !== null && <MetricBar ratio={fill.ratio} label={words.sizeLabel(said.phrase)} />}
        {fill !== null && fill.state !== "room" && (
          <p className={`script-store-fill ${fill.state}`}>{fill.state === "full" ? words.full : words.nearLimit}</p>
        )}
      </div>
      {mine !== null && mine.key === undefined && (
        <p className="script-store-refused" role="alert">
          {mine.text}
        </p>
      )}
      <ul className="script-store-entries">
        {namespace.entries.map((entry, at) => (
          <ScriptStoreEntryRow
            key={entry.key}
            entry={entry}
            refused={mine !== null && mine.key === entry.key ? mine.text : null}
            onRead={() => onRead(entry.key)}
            onGone={() => onGone(entry, at)}
            onDelete={() => onDelete(said.phrase, entry, at)}
          />
        ))}
      </ul>
    </section>
  );
}
