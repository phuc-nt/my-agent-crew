import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";

interface Props {
  agent: AgentInfo;
  readOnly: boolean;
}

/**
 * The agent's character files, one tab each.
 *
 * These are plain markdown on disk, not profile keys, so they save on their own button
 * rather than riding along with the rest of the form — a half-written persona should not
 * be written out because the person changed the cost cap.
 */
export function PersonaSection({ agent, readOnly }: Props) {
  // Every file the agent would read, not only the ones already written: a new agent has
  // written none, and a tab strip built from what exists would offer nothing to edit.
  const names = agent.persona_names;
  const written = new Set(agent.persona_files);
  const [open, setOpen] = useState(names[0] ?? "");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setLoading(true);
    setNotice(null);
    api
      .personaFile(agent.id, open)
      .then((file) => live && setBody(file.content))
      // A file that does not exist yet is the normal case for a fresh agent: the editor
      // opens empty and the first save creates it.
      .catch(() => live && setBody(""))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [agent.id, open]);

  const save = async () => {
    setSaving(true);
    setNotice(null);
    try {
      await api.putPersonaFile(agent.id, open, body);
      setNotice({ kind: "ok", text: vi.editor.personaSaved(open) });
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="editor-section" data-testid="section-persona">
      <h3>{vi.editor.sectionPersona}</h3>
      <p className="muted">{vi.editor.personaHint}</p>
      <div className="row persona-tabs" role="tablist">
        {names.map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === open}
            className={name === open ? "ghost active" : "ghost"}
            onClick={() => setOpen(name)}
          >
            {name}
            {/* Which files actually say something, so an empty one reads as "not written
                yet" rather than as a file that failed to load. */}
            {!written.has(name) && <span className="muted"> {vi.editor.personaEmpty}</span>}
          </button>
        ))}
      </div>
      {notice && (
        <div className={`notice ${notice.kind}`} role="status">
          {notice.text}
        </div>
      )}
      <textarea
        className="persona-body"
        rows={16}
        value={loading ? vi.manage.loading : body}
        disabled={readOnly || loading}
        onChange={(e) => setBody(e.target.value)}
      />
      <button type="button" disabled={readOnly || loading || saving} onClick={() => void save()}>
        {saving ? vi.editor.saving : vi.editor.personaSave}
      </button>
    </section>
  );
}
