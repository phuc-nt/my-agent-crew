import { useEffect, useState } from "react";
import { vi } from "../i18n/vi";

interface Props {
  label: string;
  value: string;
  placeholder?: string;
  rows?: number;
  onSave: (text: string) => Promise<void>;
}

type SaveState = "idle" | "saving" | "saved" | "failed";

/**
 * A labelled textarea with its own save button.
 *
 * USER.md, MEMORY.md and a daily note are all the same interaction: edit a plain text
 * file, press save, see whether it landed. The outer value reloads after a save, so the
 * draft follows it whenever the person is not mid-edit.
 */
export function MemoryEditor({ label, value, placeholder, rows = 10, onSave }: Props) {
  const [draft, setDraft] = useState(value);
  const [state, setState] = useState<SaveState>("idle");

  useEffect(() => {
    setDraft(value);
    setState("idle");
  }, [value]);

  const dirty = draft !== value;
  const save = async () => {
    setState("saving");
    try {
      await onSave(draft);
      setState("saved");
    } catch {
      setState("failed");
    }
  };

  return (
    <div className="memory-editor">
      <label>
        {label}
        <textarea
          rows={rows}
          value={draft}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.currentTarget.value)}
        />
      </label>
      <div className="memory-editor-actions">
        <button type="button" className="primary" disabled={!dirty || state === "saving"} onClick={() => void save()}>
          {state === "saving" ? vi.memory.saving : vi.memory.save}
        </button>
        <span role="status" aria-live="polite" className="muted">
          {state === "saved" && !dirty ? vi.memory.saved : ""}
          {state === "failed" ? vi.memory.saveFailed : ""}
        </span>
      </div>
    </div>
  );
}
