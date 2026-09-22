// The handful of input shapes the editor sections share. Keeping them here is what lets
// each section file stay a description of one part of a profile rather than a pile of
// label/input/hint markup repeated nine times.
import { useState, type ReactNode } from "react";

interface FieldProps {
  label: string;
  hint?: string;
  children: ReactNode;
}

/**
 * Label, control and hint as one block.
 *
 * The hint lives inside the `<label>` for layout, which would otherwise make it part of
 * the control's accessible name — so every control below carries its own `aria-label`
 * rather than inheriting the label element's whole text.
 */
export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="muted field-hint">{hint}</span>}
    </label>
  );
}

interface TextProps {
  label: string;
  hint?: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function TextField({ label, hint, value, disabled, onChange }: TextProps) {
  return (
    <Field label={label} hint={hint}>
      <input
        type="text"
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

interface NumberProps extends Omit<TextProps, "value" | "onChange"> {
  value: number;
  step?: number;
  min?: number;
  onChange: (value: number) => void;
}

export function NumberField({ label, hint, value, step, min, disabled, onChange }: NumberProps) {
  return (
    <Field label={label} hint={hint}>
      <input
        type="number"
        aria-label={label}
        value={value}
        step={step}
        min={min}
        disabled={disabled}
        // An empty box reads as 0 rather than NaN: the alternative is a field that cannot
        // be cleared without first typing a digit somewhere else.
        onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      />
    </Field>
  );
}

interface CheckProps {
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}

export function CheckField({ label, hint, checked, disabled, onChange }: CheckProps) {
  return (
    <div className="field check-field">
      <label>
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{label}</span>
      </label>
      {hint && <span className="muted field-hint">{hint}</span>}
    </div>
  );
}

interface LinesProps {
  label: string;
  hint?: string;
  value: string[];
  rows?: number;
  disabled?: boolean;
  onChange: (value: string[]) => void;
}

/** The list a given buffer of text stands for: blank lines are spacing, not entries. */
function linesOf(text: string): string[] {
  return text.split("\n").filter((line) => line.trim() !== "");
}

function sameLines(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((line, i) => line === b[i]);
}

/**
 * A list of short strings edited as one textarea, one per line.
 *
 * The text being typed lives here rather than in the draft, because the draft holds a
 * list and a blank line is not an entry. Round-tripping every keystroke through
 * `split`/`join` would delete the empty line the moment the person presses Enter —
 * whether at the end of the list or between two existing entries — and drag the cursor
 * with it.
 *
 * So the buffer is authoritative while it still means the same list the parent holds,
 * and is replaced only when the parent's value says something the buffer does not: a
 * save, a revert, or a different agent. Comparing lists rather than text is what makes
 * the in-progress blank line survive a re-render it did not cause.
 */
export function LinesField({ label, hint, value, rows = 4, disabled, onChange }: LinesProps) {
  const [text, setText] = useState(() => value.join("\n"));
  if (!sameLines(linesOf(text), value)) setText(value.join("\n"));

  return (
    <Field label={label} hint={hint}>
      <textarea
        rows={rows}
        aria-label={label}
        value={text}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value);
          onChange(linesOf(e.target.value));
        }}
      />
    </Field>
  );
}
