import type { AgentInfo } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { LinesField, NumberField } from "./fields";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  /** Everyone else in the crew; the master is the only one that should hand work out. */
  others: AgentInfo[];
  isMaster: boolean;
}

/** The two things that stop a run going on forever, the commands that still ask even
 * when the agent is autonomous, and who it may hand work to. */
export function LimitsSection({ form, readOnly, others, isMaster }: Props) {
  const { draft, set } = form;
  const delegates = draft.delegates ?? [];

  const toggle = (id: string) =>
    set("delegates", delegates.includes(id) ? delegates.filter((d) => d !== id) : [...delegates, id]);

  return (
    <section className="editor-section" data-testid="section-limits">
      <h3>{vi.editor.sectionLimits}</h3>
      <NumberField
        label={vi.editor.costCap}
        value={draft.cost_cap_usd ?? 0}
        step={0.1}
        min={0}
        disabled={readOnly}
        onChange={(v) => set("cost_cap_usd", v)}
      />
      <NumberField
        label={vi.editor.maxSteps}
        value={draft.max_steps ?? 0}
        min={1}
        disabled={readOnly}
        onChange={(v) => set("max_steps", v)}
      />
      <NumberField
        label={vi.editor.toolOutputChars}
        value={draft.tool_output_chars ?? 0}
        min={0}
        disabled={readOnly}
        onChange={(v) => set("tool_output_chars", v)}
      />
      <LinesField
        label={vi.editor.askPatterns}
        hint={vi.editor.askPatternsHint}
        value={draft.shell_ask_patterns ?? []}
        disabled={readOnly}
        onChange={(v) => set("shell_ask_patterns", v)}
      />

      <h3>{vi.editor.sectionDelegates}</h3>
      {!isMaster && <p className="muted warn-text">{vi.editor.delegatesHint}</p>}
      {others.length === 0 ? (
        <p className="muted">{vi.editor.delegatesEmpty}</p>
      ) : (
        <ul className="tool-picker" data-testid="delegate-picker">
          {others.map((agent) => (
            <li key={agent.id}>
              <label>
                <input
                  type="checkbox"
                  checked={delegates.includes(agent.id)}
                  disabled={readOnly}
                  onChange={() => toggle(agent.id)}
                />
                <strong>{agent.name}</strong>
                <code>{agent.id}</code>
              </label>
              <div className="muted">{agent.description}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
