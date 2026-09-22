import { useState } from "react";
import { api } from "../api/client";
import { vi } from "../i18n/vi";

interface Props {
  /** Called with the new agent's id so the caller can open its editor straight away. */
  onCreated: (agentId: string) => void;
  onCancel: () => void;
}

/**
 * A new agent, from the three things that cannot be guessed.
 *
 * Everything else — routes, limits, tools — comes from the crew's defaults and is edited
 * afterwards in the editor. Asking for all of it here would make the first agent the
 * hardest one to add, which is exactly backwards.
 */
export function AddAgentForm({ onCreated, onCancel }: Props) {
  const [agentId, setAgentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createAgent(agentId, { name: name || agentId, description });
      onCreated(agentId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="crew-card add-agent"
      data-testid="add-agent"
      onSubmit={(e) => {
        e.preventDefault();
        void create();
      }}
    >
      <h3>{vi.crew.addTitle}</h3>
      {error && (
        <div className="notice error" role="status">
          {error}
        </div>
      )}
      {/* The hint sits inside the label element for layout, so each input carries its own
          `aria-label`: otherwise a screen reader announces the field name and the whole
          hint as one run-on name. */}
      <label className="field">
        <span className="field-label">{vi.crew.addId}</span>
        <input
          type="text"
          aria-label={vi.crew.addId}
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          required
        />
        <span className="muted field-hint">{vi.crew.addIdHint}</span>
      </label>
      <label className="field">
        <span className="field-label">{vi.crew.addName}</span>
        <input
          type="text"
          aria-label={vi.crew.addName}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="field">
        <span className="field-label">{vi.crew.addDescription}</span>
        <input
          type="text"
          aria-label={vi.crew.addDescription}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <span className="muted field-hint">{vi.crew.addDescriptionHint}</span>
      </label>
      <div className="row">
        <button type="submit" disabled={busy || agentId.trim() === ""}>
          {busy ? vi.crew.creating : vi.crew.create}
        </button>
        <button type="button" className="ghost" disabled={busy} onClick={onCancel}>
          {vi.crew.cancel}
        </button>
      </div>
    </form>
  );
}
