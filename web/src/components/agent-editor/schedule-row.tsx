import { type MouseEvent, useRef } from "react";
import type { RowProblems } from "../../hooks/agent-draft-checks";
import { type ScheduleRow, usesEvery } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { cronText, everyText } from "../../lib/cron-text";
import { TextField } from "./fields";
import { ScheduleAction } from "./schedule-action";
import { Choice } from "./schedule-parts";

interface Props {
  row: ScheduleRow;
  /** Where the row sits in the list, counted from 1: the name of a row not named yet. */
  position: number;
  problems?: RowProblems;
  /** The agent's loaded skills, offered to the turn a row opens. */
  skills: string[];
  readOnly: boolean;
  /** The row the jobs list sent the person to: it can take focus, to be brought into view. */
  landed?: boolean;
  onChange: (patch: Partial<ScheduleRow>) => void;
  onRemove: () => void;
}

/** The two keys a row's timing switches between. */
type Timing = "cron" | "every";

const TIMINGS = [
  ["cron", vi.editor.scheduleCron],
  ["every", vi.editor.scheduleEvery],
] as const;

/**
 * One schedule: when it runs, what it does, and whether it is on.
 *
 * The parser takes exactly one of cron / every and exactly one of prompt / command /
 * script, so each is one choice with one box rather than boxes that can all be filled.
 * Switching sets the other key to null: the row keeps the declared shape, and a row the
 * person never touched still compares equal to the file and is not counted as a change.
 * What the switched-away box held is kept for the life of the row and comes back with it,
 * so a mis-tap is undone by tapping back rather than by retyping. What a row does, and the
 * same rule for it, is `ScheduleAction`.
 */
export function ScheduleRowEditor(props: Props) {
  const { row, position, problems, skills, readOnly, landed, onChange, onRemove } = props;
  const kept = useRef<Partial<Record<Timing, string>>>({});
  const every = usesEvery(row);
  const title = row.name || row.id || vi.editor.scheduleUnnamed(position);
  const timing = (every ? row.every : row.cron) ?? "";
  // The jobs list shows this same reading; seeing it here is how a swapped hour and
  // minute gets caught before it is saved rather than at seven in the evening. An error
  // takes the hint's place rather than repeating it underneath.
  const words = every ? everyText(timing) : cronText(timing);
  const timingHint = problems?.timing
    ? undefined
    : timing.trim() && words !== timing
      ? vi.editor.scheduleReads(words)
      : every
        ? vi.editor.scheduleEveryHint
        : vi.editor.scheduleCronHint;

  const swap = (from: Timing, to: Timing): Partial<ScheduleRow> => {
    kept.current[from] = row[from] ?? "";
    return { [from]: null, [to]: kept.current[to] ?? "" };
  };
  // The second click of a double click lands on whatever moved under the pointer — the
  // next row's Xoá — and would remove that schedule too.
  const remove = (event: MouseEvent) => {
    if (event.detail < 2) onRemove();
  };

  return (
    <li className="crew-card schedule-row" data-testid="schedule-row" tabIndex={landed ? -1 : undefined}>
      <div className="schedule-row-head">
        <TextField
          label={vi.editor.scheduleName}
          value={row.name}
          disabled={readOnly}
          onChange={(name) => onChange({ name })}
        />
        {/* Worded as in the jobs list: a bare switch beside Xoá read as part of removing. */}
        <label className="schedule-switch">
          <input
            type="checkbox"
            className="switch"
            checked={row.enabled}
            disabled={readOnly}
            aria-label={vi.editor.scheduleEnabled(title)}
            onChange={(e) => onChange({ enabled: e.currentTarget.checked })}
          />
          <span>{vi.jobEnabled}</span>
        </label>
        <button
          type="button"
          className="ghost"
          disabled={readOnly}
          aria-label={vi.editor.scheduleRemove(title)}
          onClick={remove}
        >
          {vi.editor.remove}
        </button>
      </div>
      <TextField
        label={vi.editor.scheduleId}
        hint={vi.editor.scheduleIdHint}
        value={row.id}
        error={problems?.id}
        mono
        disabled={readOnly}
        onChange={(id) => onChange({ id })}
      />

      <span className="field-label">{vi.editor.scheduleTiming}</span>
      <Choice
        label={vi.editor.scheduleTiming}
        value={every ? "every" : "cron"}
        options={TIMINGS}
        disabled={readOnly}
        onPick={(pick) => onChange(pick === "every" ? swap("cron", "every") : swap("every", "cron"))}
      />
      <TextField
        label={every ? vi.editor.scheduleEvery : vi.editor.scheduleCron}
        hint={timingHint}
        value={timing}
        error={problems?.timing}
        mono
        disabled={readOnly}
        onChange={(text) => onChange(every ? { every: text } : { cron: text })}
      />

      <span className="field-label">{vi.editor.scheduleAction}</span>
      <ScheduleAction row={row} problem={problems?.action} skills={skills} readOnly={readOnly} onChange={onChange} />
    </li>
  );
}
