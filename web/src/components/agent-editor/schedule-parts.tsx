// The two controls a schedule row is built from besides plain text boxes.
import { vi } from "../../i18n/vi";

interface ChoiceProps<T extends string> {
  label: string;
  value: T;
  options: readonly (readonly [T, string])[];
  disabled?: boolean;
  onPick: (value: T) => void;
}

/**
 * One of two ways to say the same thing, as a segmented control.
 *
 * Buttons with `aria-pressed` rather than radios: each choice swaps which box is shown,
 * and a pressed button says that plainly to a screen reader without a fieldset around
 * a pair of inputs that each hold nothing.
 */
export function Choice<T extends string>({ label, value, options, disabled, onPick }: ChoiceProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          disabled={disabled}
          onClick={() => value !== key && onPick(key)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

interface SkillProps {
  /** The skills the agent actually loaded; a job can only attach what the agent has. */
  available: string[];
  chosen: string[];
  disabled?: boolean;
  onChange: (skills: string[]) => void;
}

/**
 * The skills attached in full to the conversation a prompt job opens.
 *
 * A name the row already carries stays on offer even when the agent no longer loads it,
 * so the person can see it and take it off rather than have it vanish from the form while
 * it is still written in the file.
 */
export function SkillPicker({ available, chosen, disabled, onChange }: SkillProps) {
  const names = [...available, ...chosen.filter((name) => !available.includes(name))];
  if (names.length === 0) return <p className="muted field-hint">{vi.editor.scheduleSkillsEmpty}</p>;
  // Named as the jobs list names them, so one thing has one name on both pages.
  return (
    <div className="schedule-skills" role="group" aria-label={vi.jobSkills}>
      <span className="field-label">{vi.jobSkills}</span>
      <div className="row wrap">
        {names.map((name) => {
          const on = chosen.includes(name);
          return (
            <button
              key={name}
              type="button"
              className="chip"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onChange(on ? chosen.filter((s) => s !== name) : [...chosen, name])}
            >
              {name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
