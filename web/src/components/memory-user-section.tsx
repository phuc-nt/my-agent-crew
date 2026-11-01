import { useState } from "react";
import type { FactBody, FactInfo, FactRecord, FactVersion, UserMemory } from "../api/types";
import { vi } from "../i18n/vi";
import { BasisBadge, FactMeta, MemoryFactCard } from "./memory-fact-card";
import { MemoryEditor } from "./memory-editor";
import { MemoryFactForm } from "./memory-fact-form";

interface Props {
  user: UserMemory | null;
  loadedAt: string;
  onSaveUserMd: (text: string) => Promise<void>;
  onSaveFact: (name: string, body: FactBody) => Promise<void>;
  onRemoveFact: (name: string, purge?: boolean) => Promise<void>;
  onFactHistory: (name: string) => Promise<FactVersion[]>;
}

/** The shared scope: what every agent in the crew knows about the person. */
export function MemoryUserSection(props: Props) {
  const [editing, setEditing] = useState<FactInfo | null | undefined>(undefined);

  if (!props.user) return <p className="muted">{vi.loadFailed}</p>;

  const save = async (name: string, body: FactBody) => {
    await props.onSaveFact(name, body);
    setEditing(undefined);
  };

  const label = (fact: FactRecord) => fact.description || fact.name;
  const retract = (fact: FactRecord) => {
    if (window.confirm(vi.memory.confirmRetract(label(fact)))) void props.onRemoveFact(fact.name);
  };
  const purge = (fact: FactRecord) => {
    if (window.confirm(vi.memory.confirmPurge(label(fact)))) void props.onRemoveFact(fact.name, true);
  };
  const retracted = props.user.retracted ?? [];

  return (
    <div data-testid="memory-user">
      <MemoryEditor
        label={vi.memory.userMd}
        value={props.user.user_md}
        placeholder={vi.memory.userMdPlaceholder}
        onSave={props.onSaveUserMd}
      />
      {props.loadedAt && <p className="muted">{vi.memory.loadedAt(props.loadedAt)}</p>}

      <h3>{vi.memory.facts}</h3>
      {editing !== undefined ? (
        <MemoryFactForm fact={editing} onSave={save} onCancel={() => setEditing(undefined)} />
      ) : (
        <button type="button" onClick={() => setEditing(null)}>
          {vi.memory.newFact}
        </button>
      )}
      {props.user.facts.length === 0 ? (
        <p className="muted">{vi.memory.factsEmpty}</p>
      ) : (
        <ul className="fact-list">
          {props.user.facts.map((fact) => (
            <MemoryFactCard
              key={fact.name}
              fact={fact}
              onEdit={() => setEditing(fact)}
              onRetract={() => retract(fact)}
              onPurge={() => purge(fact)}
              onHistory={props.onFactHistory}
            />
          ))}
        </ul>
      )}

      {retracted.length > 0 && (
        <details className="fact-retracted">
          <summary>
            {vi.memory.retracted} ({retracted.length})
          </summary>
          <p className="muted">{vi.memory.retractedHint}</p>
          <ul className="fact-list">
            {retracted.map((fact) => (
              <li key={fact.name} data-testid={`retracted-${fact.name}`}>
                <div className="fact-head">
                  <strong>{label(fact)}</strong>
                  <BasisBadge fact={fact} />
                </div>
                <FactMeta fact={fact} />
                <div className="memory-editor-actions">
                  <button type="button" className="ghost danger" onClick={() => purge(fact)}>
                    {vi.memory.purge}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
