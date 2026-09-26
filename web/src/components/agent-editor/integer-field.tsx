import { useId, useState } from "react";
import { Field } from "./fields";

interface Props {
  label: string;
  hint?: string;
  value: number;
  disabled?: boolean;
  error?: string;
  /** The number typed, or NaN while the box holds something that is not a whole number. */
  onChange: (value: number) => void;
}

const WHOLE = /^-?\d+$/;

function parse(text: string): number {
  const trimmed = text.trim();
  return WHOLE.test(trimmed) ? Number(trimmed) : Number.NaN;
}

/** Zero is "not set yet" for the ids this field holds, so it shows as an empty box. */
function format(value: number): string {
  return Number.isNaN(value) || value === 0 ? "" : String(value);
}

function means(text: string, value: number): boolean {
  return Object.is(parse(text), value) || (text.trim() === "" && value === 0);
}

/**
 * A whole number typed as text.
 *
 * `type="number"` accepts 1e5 and 1.5 and reports anything half-typed, such as the lone
 * "-" a group id starts with, as an empty string — which would reach the draft as 0 and
 * be saved as a different id than the one on screen. Here the box keeps what was typed
 * and the draft gets the number it stands for, or NaN, which the form's checks name.
 *
 * As in `LinesField`, the buffer stays authoritative while it still means the parent's
 * value, and is replaced only by a value it does not mean: a save, a revert, an agent.
 */
export function IntegerField({ label, hint, value, disabled, error, onChange }: Props) {
  const errorId = useId();
  const [text, setText] = useState(() => format(value));
  if (!means(text, value)) setText(format(value));

  return (
    <Field label={label} hint={hint} error={error} errorId={errorId}>
      <input
        type="text"
        aria-label={label}
        className="mono"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        value={text}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value);
          onChange(parse(e.target.value));
        }}
      />
    </Field>
  );
}
