import { useState } from "react";
import type { FactInfo, FactType, UserMemory } from "../api/types";
import { vi } from "../i18n/vi";
import { MemoryEditor } from "./memory-editor";
import { MemoryFactForm } from "./memory-fact-form";

interface Props {
  user: UserMemory | null;
  loadedAt: string;
  onSaveUserMd: (text: string) => Promise<void>;
  onSaveFact: (name: string, body: { description: string; type: FactType; body: string }) => Promise<void>;
  onRemoveFact: (name: string) => Promise<void>;
}

/** The shared scope: what every agent in the crew knows about the person. */
export function MemoryUserSection(props: Props) {
  const [editing, setEditing] = useState<FactInfo | null | undefined>(undefined);

  if (!props.user) return <p className="muted">{vi.loadFailed}</p>;

  const save = async (name: string, body: { description: string; type: FactType; body: string }) => {
    await props.onSaveFact(name, body);
    setEditing(undefined);
  };

  const remove = (fact: FactInfo) => {
    if (window.confirm(vi.memory.confirmRemove(fact.description || fact.name))) {
      void props.onRemoveFact(fact.name);
    }
  };

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
            <li key={fact.name}>
              <div className="fact-head">
                <strong>{fact.description || fact.name}</strong>
                <span className="badge">{vi.memory.factTypes[fact.type] ?? fact.type}</span>
              </div>
              <div className="muted">
                <code>{fact.name}</code> · {vi.memory.writtenBy(fact.written_by)} · {fact.updated}
              </div>
              {fact.body && <p className="fact-body">{fact.body}</p>}
              <div className="memory-editor-actions">
                <button type="button" className="ghost" onClick={() => setEditing(fact)}>
                  {vi.memory.edit}
                </button>
                <button type="button" className="ghost" onClick={() => remove(fact)}>
                  {vi.memory.remove}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
