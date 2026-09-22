import { useState } from "react";
import { api } from "../../api/client";
import { vi } from "../../i18n/vi";

interface Props {
  agentId: string;
  onDeleted: () => void;
}

/**
 * Removing an agent from the crew.
 *
 * Typing the id is the confirmation rather than a yes/no dialog, because the two clicks a
 * dialog costs are exactly the two clicks muscle memory spends without reading. The
 * server moves the folder to `.trash` instead of deleting it, so a mistake here is
 * recoverable — the notice says where it went.
 */
export function DeleteAgent({ agentId, onDeleted }: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAgent(agentId);
      onDeleted();
    } catch (e) {
      // Usually a 409 naming the agents that delegate to this one, which is the whole
      // answer to "why not" — so it is shown as the server wrote it.
      setError(vi.editor.deleteFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="editor-section danger" data-testid="delete-agent">
      <h3>{vi.editor.deleteTitle}</h3>
      <p className="muted">{vi.editor.deleteHint(agentId)}</p>
      {error && (
        <div className="notice error" role="status">
          {error}
        </div>
      )}
      <div className="row">
        <input
          type="text"
          aria-label={vi.editor.deleteTitle}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <button
          type="button"
          className="danger"
          disabled={busy || typed !== agentId}
          onClick={() => void remove()}
        >
          {vi.editor.deleteConfirm}
        </button>
      </div>
    </section>
  );
}
