import { vi } from "../../i18n/vi";
import { Field } from "./fields";

interface Props {
  script: string;
  /** The prompt a turn is opened with when the script printed something; a row without
   *  one runs its script and calls no model at all. */
  thenPrompt?: string | null;
}

/** As many lines as the text has, within what a row can spend on one box. */
const linesOf = (text: string, most: number) => Math.min(most, Math.max(2, text.split("\n").length));

/**
 * What a script row does, shown and not edited.
 *
 * A script job is written by hand in `agent.yaml`: it runs code with no model call, and a
 * box to type one into is a different feature from the one this form is. So the row says
 * what kind it is where the other rows choose between a prompt and a command, with no
 * choice to make, and shows the script and the prompt its output goes on with in boxes
 * that are read-only rather than disabled: they can be scrolled, selected and read out,
 * which is all there is to do with them here.
 */
export function ScheduleScriptAction({ script, thenPrompt }: Props) {
  return (
    <>
      <div className="schedule-script-kind" data-testid="schedule-script-kind">
        {/* Named as the jobs list names the kind, so one thing has one name on both pages. */}
        <span className="badge">{vi.jobKindScript}</span>
        <span className="muted field-hint">{vi.editor.scheduleScriptHint}</span>
      </div>
      <Field label={vi.editor.scheduleScript}>
        <textarea
          className="mono"
          aria-label={vi.editor.scheduleScript}
          rows={linesOf(script, 12)}
          value={script}
          readOnly
        />
      </Field>
      {thenPrompt && (
        <Field label={vi.editor.scheduleThenPrompt}>
          <textarea aria-label={vi.editor.scheduleThenPrompt} rows={linesOf(thenPrompt, 6)} value={thenPrompt} readOnly />
        </Field>
      )}
    </>
  );
}
