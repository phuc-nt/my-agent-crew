import { useState } from "react";
import type { FactInfo, FactRecord, FactVersion } from "../api/types";
import { routeHash } from "../hooks/use-route";
import { vi } from "../i18n/vi";

interface Props {
  fact: FactInfo;
  onEdit: () => void;
  onRetract: () => void;
  onPurge: () => void;
  onHistory: (name: string) => Promise<FactVersion[]>;
}

const CONV = "conv:";
const day = (stamp: string) => stamp.slice(0, 10);

/** A source as a link where it names a conversation, plain text otherwise. */
export function FactSources({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;
  return (
    <span className="fact-sources">
      {vi.memory.factSources}{" "}
      {sources.map((source, i) => (
        <span key={source}>
          {i > 0 && ", "}
          {source.startsWith(CONV) ? (
            <a href={routeHash({ kind: "chat", conversationId: source.slice(CONV.length) })}>{source}</a>
          ) : (
            <code>{source}</code>
          )}
        </span>
      ))}
    </span>
  );
}

/** The line of who, when and since when that every version shares. */
export function FactMeta({ fact }: { fact: FactRecord }) {
  const span = fact.valid_from || fact.valid_until ? vi.memory.factSpan(fact.valid_from, fact.valid_until) : "";
  return (
    <div className="muted fact-meta">
      <code>{fact.name}</code> · v{fact.version} · {vi.memory.writtenBy(fact.written_by)} · {day(fact.updated)}
      {span && <> · {span}</>}
      {fact.confirmed && <> · {vi.memory.factConfirmed(day(fact.confirmed))}</>}
    </div>
  );
}

/** The person's own word, typed or said, shows apart from what an agent made of it. */
const PERSONS = new Set(["operator", "said"]);

export function BasisBadge({ fact }: { fact: FactRecord }) {
  const tone = PERSONS.has(fact.basis) ? "badge ok" : "badge";
  return <span className={tone}>{vi.memory.factBasis[fact.basis] ?? fact.basis}</span>;
}

/** One fact with what stands behind it, and its past versions on demand. */
export function MemoryFactCard({ fact, onEdit, onRetract, onPurge, onHistory }: Props) {
  const [versions, setVersions] = useState<FactVersion[] | null>(null);
  const toggle = async () => setVersions(versions ? null : await onHistory(fact.name));

  return (
    <li data-testid={`fact-${fact.name}`} className={`fact-${fact.state}`}>
      <div className="fact-head">
        <strong>{fact.description || fact.name}</strong>
        <span className="badge">{vi.memory.factTypes[fact.type] ?? fact.type}</span>
        <BasisBadge fact={fact} />
        {fact.state === "pending" && <span className="badge accent">{vi.memory.factPending(fact.valid_from)}</span>}
        {fact.state === "expired" && <span className="badge danger">{vi.memory.factExpired}</span>}
        {fact.stale && <span className="badge warn">{vi.memory.factStale}</span>}
      </div>
      <FactMeta fact={fact} />
      {fact.body && <p className="fact-body">{fact.body}</p>}
      <div className="muted fact-meta">
        {fact.recalls > 0 && <span>{vi.memory.factRecalls(fact.recalls)} · </span>}
        <FactSources sources={fact.sources} />
      </div>
      <div className="memory-editor-actions">
        <button type="button" className="ghost" onClick={onEdit}>
          {vi.memory.edit}
        </button>
        <button type="button" className="ghost" aria-expanded={versions !== null} onClick={() => void toggle()}>
          {vi.memory.factHistory(fact.history_count)}
        </button>
        <button type="button" className="ghost" onClick={onRetract}>
          {vi.memory.retract}
        </button>
        <button type="button" className="ghost danger" onClick={onPurge}>
          {vi.memory.purge}
        </button>
      </div>
      {versions && <FactVersions versions={versions} />}
    </li>
  );
}

function FactVersions({ versions }: { versions: FactVersion[] }) {
  if (versions.length === 0) return <p className="muted">{vi.memory.factHistoryEmpty}</p>;
  return (
    <ol className="fact-versions">
      {versions.map((v) => (
        <li key={`${v.version}-${v.ended_at}`}>
          <div className="fact-head">
            <span>v{v.version}</span>
            <strong>{v.description || v.name}</strong>
            <BasisBadge fact={v} />
            <span className="muted">
              {vi.memory.factEnded[v.why] ?? v.why} {day(v.ended_at)}
            </span>
          </div>
          {v.body && <p className="fact-body">{v.body}</p>}
        </li>
      ))}
    </ol>
  );
}
