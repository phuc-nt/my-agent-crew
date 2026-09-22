import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { CheckField, Field, TextField } from "./fields";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
}

/** Who the agent is and where it works: the name the master sees, the one-line
 * description it routes on, the chat/work mode, and the folder it may touch. */
export function IdentitySection({ form, readOnly }: Props) {
  const { draft, set } = form;
  return (
    <section className="editor-section" data-testid="section-identity">
      <h3>{vi.editor.sectionIdentity}</h3>
      <TextField
        label={vi.editor.name}
        value={draft.name ?? ""}
        disabled={readOnly}
        onChange={(v) => set("name", v)}
      />
      <TextField
        label={vi.editor.description}
        hint={vi.editor.descriptionHint}
        value={draft.description ?? ""}
        disabled={readOnly}
        onChange={(v) => set("description", v)}
      />
      <Field label={vi.editor.mode} hint={vi.editor.modeHint}>
        <select
          aria-label={vi.editor.mode}
          value={draft.mode ?? "assistant"}
          disabled={readOnly}
          onChange={(e) => set("mode", e.target.value)}
        >
          <option value="assistant">{vi.editor.modeChat}</option>
          <option value="work">{vi.editor.modeWork}</option>
        </select>
      </Field>
      <TextField
        label={vi.editor.workspace}
        hint={vi.editor.workspaceHint}
        value={draft.workspace ?? ""}
        disabled={readOnly}
        onChange={(v) => set("workspace", v)}
      />
      <CheckField
        label={vi.editor.autonomous}
        checked={draft.autonomous ?? false}
        disabled={readOnly}
        onChange={(v) => set("autonomous", v)}
      />
    </section>
  );
}
