import type { RegistryTool } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  tools: RegistryTool[];
}

/**
 * Which tools the agent may use.
 *
 * An empty list is not "no tools" — it is "no allow-list", which means every tool the
 * mode grants. That difference is invisible in a bare set of checkboxes, so it gets its
 * own radio pair above them; ticking nothing would otherwise silently mean the opposite
 * of what it looks like.
 */
export function ToolsSection({ form, readOnly, tools }: Props) {
  const picked = form.draft.tools ?? [];
  const restricted = picked.length > 0;

  const toggle = (name: string) => {
    const next = picked.includes(name) ? picked.filter((t) => t !== name) : [...picked, name];
    form.set("tools", next);
  };

  return (
    <section className="editor-section" data-testid="section-tools">
      <h3>{vi.editor.sectionTools}</h3>
      <div className="field check-field">
        <label>
          <input
            type="radio"
            name="tools-mode"
            checked={!restricted}
            disabled={readOnly}
            onChange={() => form.set("tools", [])}
          />
          <span>{vi.editor.toolsAll}</span>
        </label>
        <label>
          <input
            type="radio"
            name="tools-mode"
            checked={restricted}
            disabled={readOnly}
            // Switching on the allow-list with nothing ticked would save as "no
            // allow-list" again, so it starts from everything the agent holds today.
            onChange={() => form.set("tools", tools.map((t) => t.name))}
          />
          <span>{vi.editor.toolsPick}</span>
        </label>
        <span className="muted field-hint">{vi.editor.toolsHint}</span>
      </div>
      <ul className="tool-picker" data-testid="tool-picker">
        {tools.map((tool) => (
          <li key={tool.name}>
            <label>
              <input
                type="checkbox"
                checked={picked.includes(tool.name)}
                disabled={readOnly || !restricted}
                onChange={() => toggle(tool.name)}
              />
              <code>{tool.name}</code>
              {tool.optional && <span className="badge">{vi.tools.optional}</span>}
            </label>
            <div className="muted">{tool.description}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
