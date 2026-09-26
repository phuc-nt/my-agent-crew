import { useEffect, useRef } from "react";
import { blankSchedule, type ScheduleRow } from "../../hooks/agent-draft-checks";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { TextField } from "./fields";
import { ScheduleRowEditor } from "./schedule-row";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
  /** The agent's loaded skills, which a prompt job can attach. */
  skills: string[];
  /** Opened from a job's "edit schedule": bring this section into view and focus it. */
  focused?: boolean;
}

/**
 * The jobs that run the agent on their own: its schedules and the nightly memory pass.
 *
 * Both are read by the scheduler once, at boot, so changing either takes a restart — which
 * the save banner says. The consolidation cron lives here rather than among the limits
 * because it is a schedule too, and it shows in the jobs list beside the others.
 */
export function SchedulesSection({ form, readOnly, skills, focused }: Props) {
  const rows = (form.draft.schedules ?? []) as ScheduleRow[];
  const problems = form.problems.schedules ?? {};
  const keys = useRowKeys(rows);
  const put = (next: ScheduleRow[]) => form.set("schedules", next);
  const edit = (i: number, patch: Partial<ScheduleRow>) =>
    put(rows.map((row, at) => (at === i ? { ...row, ...patch } : row)));
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const add = useRef<HTMLButtonElement>(null);
  const refocus = useRef<number | null>(null);

  const remove = (i: number) => {
    refocus.current = i;
    put(rows.filter((_, at) => at !== i));
  };

  // The removed row's button is gone, and focus with it. It goes on purpose to the row
  // that took its place, or to adding one when none did — never to the next row's Xoá,
  // where a second press would remove a schedule nobody chose.
  useEffect(() => {
    const at = refocus.current;
    if (at === null) return;
    refocus.current = null;
    const next = list.current?.children[at]?.querySelector<HTMLElement>("input, textarea");
    (next ?? add.current)?.focus();
  });

  // Arriving from the jobs list means this section, which sits far down the form; left
  // at the top of the editor, the person would have to hunt for what they clicked.
  useEffect(() => {
    if (!focused) return;
    heading.current?.scrollIntoView?.({ block: "start" });
    heading.current?.focus({ preventScroll: true });
  }, [focused]);

  return (
    <section className="editor-section" data-testid="section-schedules">
      <h3 ref={heading} tabIndex={-1}>
        {vi.editor.sectionSchedules}
      </h3>
      <p className="muted">{vi.editor.schedulesHint}</p>
      {rows.length === 0 && <p className="muted">{vi.editor.schedulesEmpty}</p>}
      <ul className="schedule-editor" data-testid="schedule-editor" ref={list}>
        {rows.map((row, i) => (
          <ScheduleRowEditor
            key={keys[i]}
            row={row}
            position={i + 1}
            problems={problems[i]}
            skills={skills}
            readOnly={readOnly}
            onChange={(patch) => edit(i, patch)}
            onRemove={() => remove(i)}
          />
        ))}
      </ul>
      <button
        ref={add}
        type="button"
        className="ghost schedule-add"
        disabled={readOnly}
        onClick={() => put([...rows, blankSchedule()])}
      >
        {vi.editor.addSchedule}
      </button>
      <TextField
        label={vi.editor.memoryConsolidate}
        hint={vi.editor.memoryConsolidateHint}
        value={form.draft.memory_consolidate ?? ""}
        error={form.problems.memoryConsolidate}
        mono
        disabled={readOnly}
        onChange={(v) => form.set("memory_consolidate", v)}
      />
    </section>
  );
}

/**
 * A key per row that follows the row rather than its position.
 *
 * Keyed by index, removing a row handed its component — and the focused Xoá button — to
 * the row below. Rows carry no id of their own (a new one has none until saved), so the
 * key is tied to the row object: an edit replaces one row object and keeps its place, so
 * a row not seen before takes the key its position had; an added row gets a new one.
 */
function useRowKeys(rows: ScheduleRow[]): number[] {
  const known = useRef(new WeakMap<ScheduleRow, number>());
  const last = useRef<number[]>([]);
  const next = useRef(0);
  const used = new Set<number>();
  const keys = rows.map((row, at) => {
    let key = known.current.get(row) ?? last.current[at];
    if (key === undefined || used.has(key)) key = next.current++;
    known.current.set(row, key);
    used.add(key);
    return key;
  });
  last.current = keys;
  return keys;
}
