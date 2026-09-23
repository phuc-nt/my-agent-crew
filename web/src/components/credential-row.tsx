import { useState, type FormEvent } from "react";
import type { CredentialInfo } from "../api/types";
import type { CredentialsController } from "../hooks/use-credentials";
import { vi } from "../i18n/vi";
import { MetricRow, type Tone } from "./ui/metric-card";

interface Props {
  item: CredentialInfo;
  credentials: CredentialsController;
}

interface Note {
  tone: Tone;
  text: string;
}

const errorText = (e: unknown) => vi.connectionsPage.failed(e instanceof Error ? e.message : String(e));

/**
 * One environment variable: whether it is set, and the controls to set, replace, remove
 * or check it. The field is write-only — it starts empty even when a value is set and is
 * cleared once saved — so a secret typed here is never read back into the page.
 */
export function CredentialRow({ item, credentials }: Props) {
  const t = vi.connectionsPage;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  // Which action is in flight: every control waits for it, only its own says so.
  const [pending, setPending] = useState<"save" | "check" | "remove" | null>(null);
  const busy = pending !== null;
  const [note, setNote] = useState<Note | null>(null);

  const run = async (kind: "save" | "check" | "remove", work: () => Promise<Note>) => {
    setPending(kind);
    setNote(null);
    try {
      setNote(await work());
    } catch (e) {
      setNote({ tone: "danger", text: errorText(e) });
    } finally {
      setPending(null);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run("save", async () => {
      const answer = await credentials.save(item.name, draft);
      setDraft("");
      setEditing(false);
      return answer.restart_required
        ? { tone: "warn", text: answer.restart_required }
        : { tone: "ok", text: t.saved };
    });
  };

  const remove = () => {
    if (!window.confirm(t.confirmRemove(item.name))) return;
    void run("remove", async () => {
      const answer = await credentials.remove(item.name);
      return answer.restart_required
        ? { tone: "warn", text: answer.restart_required }
        : { tone: "ok", text: t.removed };
    });
  };

  const check = () =>
    void run("check", async () => {
      const result = await credentials.check(item.name);
      return { tone: result.ok ? "ok" : "danger", text: result.detail };
    });

  const shown = !item.secret && (item.value || (item.default && t.defaultValue(item.default)));
  const sub = !item.editable
    ? t.fileOnly
    : item.source === "process"
      ? t.fromProcess
      : shown || undefined;

  return (
    <li data-testid={`credential-${item.name}`}>
      <MetricRow
        label={
          <>
            <code>{item.name}</code>
            {item.agents && item.agents.length > 0 && (
              <span className="muted">{t.usedBy(item.agents.join(", "))}</span>
            )}
          </>
        }
        value={
          <span className={`badge ${item.present ? "ok" : "warn"}`}>
            {item.present ? t.present : t.absent}
          </span>
        }
        sub={sub}
        subTone={item.source === "process" ? "warn" : "muted"}
      />
      {editing ? (
        <form className="credential-form" onSubmit={submit}>
          <input
            type={item.secret ? "password" : "url"}
            autoComplete={item.secret ? "new-password" : "off"}
            spellCheck={false}
            autoFocus
            aria-label={t.valueFor(item.name)}
            placeholder={item.secret ? t.secretPlaceholder : t.urlPlaceholder}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="primary" disabled={busy || !draft.trim()}>
            {pending === "save" ? t.saving : t.save}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => {
              setEditing(false);
              setDraft("");
            }}
          >
            {t.cancel}
          </button>
        </form>
      ) : (
        <div className="credential-actions">
          {item.editable && (
            <button type="button" disabled={busy} onClick={() => setEditing(true)}>
              {item.present ? t.replace : t.set}
            </button>
          )}
          {item.checkable && (
            <button type="button" className="ghost" disabled={busy} onClick={check}>
              {pending === "check" ? t.checking : item.check_spends ? t.checkSpends : t.check}
            </button>
          )}
          {item.editable && item.present && item.source === "file" && (
            <button type="button" className="danger" disabled={busy} onClick={remove}>
              {t.remove}
            </button>
          )}
        </div>
      )}
      {note && (
        <p className={`credential-note ${note.tone}`} role="status">
          {note.text}
        </p>
      )}
    </li>
  );
}
