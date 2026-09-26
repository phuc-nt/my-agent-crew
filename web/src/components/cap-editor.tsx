import { useState } from "react";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";

interface Props {
  capUsd: number;
  /** Stores the new cap, 0 lifting it; rejects with the server's reason when refused. */
  onSave: (capUsd: number) => Promise<void>;
}

// A top-up is a step, not a figure to work out: the person mostly wants a little more
// room to let the agent finish, not to rethink the budget.
const STEPS = [0.5, 1];

/**
 * Changes a conversation's cost cap in place: a step above the current cap, or a typed
 * figure where 0 lifts the cap. A refused save says so here, beside the control that
 * caused it — the page's load error would blame the wrong thing.
 */
export function CapEditor({ capUsd, onSave }: Props) {
  const [custom, setCustom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const unlimited = capUsd <= 0;

  const save = async (next: number) => {
    // The field's min is only a hint to the browser; a typed "-1" still arrives here.
    if (!Number.isFinite(next) || next < 0) return setError(vi.budgetCard.capInvalid);
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
      setCustom("");
    } catch (e) {
      setError(vi.budgetCard.saveFailed(e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cap-editor" data-testid="cap-editor">
      <p>
        {vi.budgetCard.cap} <strong className="tabular">{unlimited ? vi.unlimited : formatUsd(capUsd)}</strong>
      </p>
      {/* Stepping up from "no cap" would set one, the opposite of raising it. Cents are
          what a cap is written in, and two floats do not always sum to one. */}
      {!unlimited && (
        <div className="cap-editor-steps" role="group" aria-label={vi.budgetCard.raise}>
          {STEPS.map((step) => (
            <button
              key={step}
              type="button"
              disabled={saving}
              onClick={() => void save(Math.round((capUsd + step) * 100) / 100)}
            >
              +{formatUsd(step)}
            </button>
          ))}
        </div>
      )}
      <form className="cap-editor-custom" noValidate onSubmit={(event) => {
        event.preventDefault();
        void save(Number(custom));
      }}>
        <label>
          {vi.budgetCard.custom}
          <input type="number" inputMode="decimal" min={0} step="0.01" value={custom}
            onChange={(event) => setCustom(event.target.value)} />
        </label>
        <button type="submit" className="primary" disabled={saving || custom.trim() === ""}>
          {vi.budgetCard.set}
        </button>
      </form>
      {error && <p className="cap-editor-error" role="alert">{error}</p>}
    </div>
  );
}
