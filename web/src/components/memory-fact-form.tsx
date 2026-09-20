import { useState } from "react";
import { FACT_TYPES, type FactInfo, type FactType } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  /** null when adding; an existing fact keeps its name, which is its file name. */
  fact: FactInfo | null;
  onSave: (name: string, body: { description: string; type: FactType; body: string }) => Promise<void>;
  onCancel: () => void;
}

export function MemoryFactForm({ fact, onSave, onCancel }: Props) {
  const [name, setName] = useState(fact?.name ?? "");
  const [description, setDescription] = useState(fact?.description ?? "");
  const [type, setType] = useState<FactType>((fact?.type as FactType) ?? "reference");
  const [body, setBody] = useState(fact?.body ?? "");
  const [failed, setFailed] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFailed(false);
    try {
      await onSave(name.trim(), { description: description.trim(), type, body });
    } catch {
      setFailed(true);
    }
  };

  return (
    <form className="memory-fact-form" onSubmit={(event) => void submit(event)}>
      <label>
        {vi.memory.factName}
        <input
          value={name}
          readOnly={fact !== null}
          pattern="[a-z0-9-]{1,60}"
          required
          onChange={(event) => setName(event.currentTarget.value)}
        />
      </label>
      <p className="muted">{vi.memory.factNameHint}</p>
      <label>
        {vi.memory.factDescription}
        <input value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
      </label>
      <label>
        {vi.memory.factType}
        <select value={type} onChange={(event) => setType(event.currentTarget.value as FactType)}>
          {FACT_TYPES.map((value) => (
            <option key={value} value={value}>
              {vi.memory.factTypes[value]}
            </option>
          ))}
        </select>
      </label>
      <label>
        {vi.memory.factBody}
        <textarea rows={5} value={body} onChange={(event) => setBody(event.currentTarget.value)} />
      </label>
      {failed && (
        <p className="notice error" role="status">
          {vi.memory.saveFailed}
        </p>
      )}
      <div className="memory-editor-actions">
        <button type="submit">{vi.memory.save}</button>
        <button type="button" className="ghost" onClick={onCancel}>
          {vi.memory.cancel}
        </button>
      </div>
    </form>
  );
}
