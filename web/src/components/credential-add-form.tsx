import { useState, type FormEvent } from "react";
import type { CredentialsController } from "../hooks/use-credentials";
import { vi } from "../i18n/vi";

// The same rule the server enforces; checked here too so the button says no before a
// round trip does. Names the server keeps for itself (PATH, MY_AGENT_*) still come back
// as its own error.
const NAME_RE = /^[A-Z][A-Z0-9_]{0,63}$/;

/** A variable the page does not know by name: a skill's user id, a script's token. */
export function CredentialAddForm({ credentials }: { credentials: CredentialsController }) {
  const t = vi.connectionsPage;
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validName = NAME_RE.test(name);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await credentials.save(name, value);
      setName("");
      setValue("");
    } catch (e) {
      setError(t.failed(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="credential-form" data-testid="credential-add" onSubmit={submit}>
      <input
        type="text"
        aria-label={t.newName}
        placeholder={t.namePlaceholder}
        autoComplete="off"
        spellCheck={false}
        value={name}
        onChange={(e) => setName(e.target.value.toUpperCase())}
      />
      <input
        type="password"
        aria-label={t.valueFor(name || t.newName)}
        placeholder={t.secretPlaceholder}
        autoComplete="new-password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button type="submit" className="primary" disabled={busy || !validName || !value.trim()}>
        {busy ? t.saving : t.add}
      </button>
      {name && !validName && <p className="credential-note warn">{t.nameRule}</p>}
      {error && (
        <p className="credential-note danger" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
