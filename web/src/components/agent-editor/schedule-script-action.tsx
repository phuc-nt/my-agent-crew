import { useId } from "react";
import { vi } from "../../i18n/vi";
import { Field } from "./fields";

interface Props {
  script: string;
  /** The prompt a turn is opened with when the script printed something; empty for a row
   *  whose script tells nobody. */
  thenPrompt: string;
  /** Why the script cannot be saved as it is. */
  problem?: string;
  /** The agent is not this form's to change: the boxes are read, and still scroll. */
  readOnly: boolean;
  onChange: (patch: { script?: string; then_prompt?: string | null }) => void;
}

/** As many lines as the text has, from the fewest worth a box to the most a row can spend. */
const linesOf = (text: string, least: number, most: number) => Math.min(most, Math.max(least, text.split("\n").length));

/**
 * The two boxes of a row that runs a script: the script, and the prompt what it prints
 * goes on with.
 *
 * A script is code, and Python reads its indentation: it is held character for character,
 * nothing trimmed, a pasted tab still a tab, shown four columns wide. The Tab key is not
 * taken to indent with. A box that swallows Tab is one the keyboard cannot leave, so here
 * it moves to the next control as it does in every other box, and indentation is typed as
 * spaces, which the hint says. Spelling marks and a phone's capital letters are off: they
 * are for prose, and would change code as it is typed.
 *
 * An emptied prompt box is no prompt, which the row holds as null, as the file does.
 *
 * On an agent the form cannot change both boxes are read-only rather than disabled, since
 * a script is longer than its box and a disabled one cannot be scrolled or copied from.
 */
export function ScheduleScriptFields({ script, thenPrompt, problem, readOnly, onChange }: Props) {
  const scriptHint = useId();
  const scriptError = useId();
  const thenHint = useId();
  return (
    <>
      <Field
        label={vi.editor.scheduleScript}
        hint={vi.editor.scheduleScriptHint}
        hintId={scriptHint}
        error={problem}
        errorId={scriptError}
      >
        <textarea
          className="mono schedule-script"
          aria-label={vi.editor.scheduleScript}
          aria-describedby={problem ? `${scriptHint} ${scriptError}` : scriptHint}
          aria-invalid={problem ? true : undefined}
          rows={linesOf(script, 6, 12)}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          value={script}
          readOnly={readOnly}
          onChange={(e) => onChange({ script: e.target.value })}
        />
      </Field>
      <Field label={vi.editor.scheduleThenPrompt} hint={vi.editor.scheduleThenPromptHint} hintId={thenHint}>
        <textarea
          aria-label={vi.editor.scheduleThenPrompt}
          aria-describedby={thenHint}
          rows={linesOf(thenPrompt, 2, 6)}
          value={thenPrompt}
          readOnly={readOnly}
          onChange={(e) => onChange({ then_prompt: e.target.value === "" ? null : e.target.value })}
        />
      </Field>
    </>
  );
}
