import { useId } from "react";
import type { ScriptCalls } from "../../api/types";
import { scriptsAskNobody } from "../../hooks/agent-draft-shape";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { routeHash } from "../../hooks/use-route";
import { vi } from "../../i18n/vi";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
}

const CALLS: ScriptCalls[] = ["none", "read_only", "gated"];

/**
 * What the agent's scripts may reach, and whether they may ask a model.
 *
 * Both sit with the tools because they are the say over one of them: the script tool is
 * handed outside the allow-list, as a server's tools are, and these two keys are the only
 * thing that takes it away or widens what it calls.
 *
 * Under the select is the line for the option chosen, tied to it as its description, so
 * the consequence is read where the choice is made. With `gated` chosen on an agent the
 * form has running by itself, that line says what the two mean together: nobody is asked.
 * The same line stands under the autonomy tick, at the top of the form.
 *
 * Last comes the way to what those scripts keep from one run to the next, on the screen
 * that shows it with this agent chosen. The form's type allows no agent at all, which no
 * screen opens this on: the link is made of the agent's id, so it waits for one.
 */
export function ScriptControls({ form, readOnly }: Props) {
  const callsHint = useId();
  const llmHint = useId();
  const t = vi.editor;
  const calls = form.draft.script_calls ?? "read_only";
  const unasked = scriptsAskNobody(form.draft);
  const kept = form.original && routeHash({ kind: "manage", section: "memory", param: "scripts", focus: form.original.id });

  return (
    <>
      <h3>{t.sectionScript}</h3>
      <p className="muted">{t.scriptHint}</p>
      <label className="field">
        <span className="field-label">{t.scriptCalls}</span>
        <select
          aria-label={t.scriptCalls}
          aria-describedby={callsHint}
          value={calls}
          disabled={readOnly}
          onChange={(e) => form.set("script_calls", e.target.value as ScriptCalls)}
        >
          {CALLS.map((value) => (
            <option key={value} value={value}>
              {t.scriptCallsOption[value]}
            </option>
          ))}
        </select>
        <span className={unasked ? "field-hint warn-text" : "muted field-hint"} id={callsHint}>
          {unasked ? t.scriptCallsGatedAutonomous : t.scriptCallsHint[calls]}
        </span>
      </label>
      <div className="field check-field">
        <label>
          <input
            type="checkbox"
            aria-describedby={llmHint}
            checked={form.draft.script_llm ?? true}
            disabled={readOnly}
            onChange={(e) => form.set("script_llm", e.target.checked)}
          />
          <span>{t.scriptLlm}</span>
        </label>
        <span className="muted field-hint" id={llmHint}>
          {t.scriptLlmHint}
        </span>
      </div>
      {kept && (
        <a className="editor-link" href={kept}>
          {t.scriptStoreLink}
        </a>
      )}
    </>
  );
}
