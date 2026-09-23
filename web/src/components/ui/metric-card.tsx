import type { ReactNode } from "react";

/** The colour a figure or its note takes: the same triples the badges read. */
export type Tone = "ok" | "warn" | "danger" | "accent" | "muted";

/**
 * A dense card of labelled figures: an icon and a name on the left, the value in
 * monospace on the right, and an optional coloured note underneath.
 *
 * Every summary surface — the chat's activity column, the header popovers, settings,
 * costs — is built from these rows, so a figure reads the same wherever it appears and
 * the eye learns one layout instead of one per screen.
 */
export function MetricCard({
  title,
  testId,
  className = "",
  children,
}: {
  title?: string;
  testId?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`metric-card ${className}`.trim()} data-testid={testId} aria-label={title}>
      {title && <h3 className="metric-card-title">{title}</h3>}
      {children}
    </section>
  );
}

/** A hover explanation beside a label: the glyph stays small, the sentence stays one hover away. */
export function Hint({ text }: { text: string }) {
  return (
    <span className="metric-hint" title={text}>
      ⓘ
    </span>
  );
}

export function MetricRow({
  icon,
  label,
  hint,
  value,
  sub,
  subTone = "muted",
  action,
  children,
}: {
  icon?: string;
  label: ReactNode;
  hint?: string;
  value?: ReactNode;
  sub?: ReactNode;
  subTone?: Tone;
  /** A control at the end of the row, after the value: a link or a small button. */
  action?: ReactNode;
  /** Rendered between the head and the note, e.g. a bar. */
  children?: ReactNode;
}) {
  return (
    <div className="metric-row">
      <div className="metric-head">
        <span className="metric-label">
          {icon && (
            <span className="metric-icon" aria-hidden="true">
              {icon}
            </span>
          )}
          {label}
          {hint && <Hint text={hint} />}
        </span>
        {value !== undefined && <span className="metric-value tabular">{value}</span>}
        {action}
      </div>
      {children}
      {sub && <div className={`metric-sub ${subTone}`}>{sub}</div>}
    </div>
  );
}

/**
 * A thin proportion bar. The tone follows how close the figure is to its limit unless
 * the caller names one, so every budget in the app turns amber and red at the same points.
 */
export function MetricBar({ ratio, label, tone }: { ratio: number; label: string; tone?: Tone }) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const shade = tone ?? (clamped >= 1 ? "danger" : clamped >= 0.8 ? "warn" : "accent");
  const percent = Math.round(clamped * 100);
  return (
    <div
      className={`metric-bar ${shade}`}
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span style={{ width: `${Math.max(clamped > 0 ? 2 : 0, percent)}%` }} />
    </div>
  );
}

export function MetricDivider() {
  return <hr className="metric-divider" />;
}

/**
 * A setting that is on or off, drawn as a switch. It stays a native checkbox underneath,
 * so the keyboard, the form semantics and every "checkbox named X" lookup keep working;
 * only the look changes. The name is given explicitly so the hint glyph never ends up in it.
 */
export function SwitchRow({
  icon,
  label,
  hint,
  checked,
  disabled,
  onChange,
  sub,
  indent = false,
}: {
  icon?: string;
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
  sub?: ReactNode;
  indent?: boolean;
}) {
  return (
    <label className={`metric-row switch-row${indent ? " indent" : ""}`}>
      <span className="metric-head">
        <span className="metric-label">
          {icon && (
            <span className="metric-icon" aria-hidden="true">
              {icon}
            </span>
          )}
          {label}
          {hint && <Hint text={hint} />}
        </span>
        <input
          type="checkbox"
          className="switch"
          aria-label={label}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.currentTarget.checked)}
        />
      </span>
      {sub && <span className="metric-sub muted">{sub}</span>}
    </label>
  );
}
