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
  const put = (next: ScheduleRow[]) => form.set("schedules", next);
  const edit = (i: number, patch: Partial<ScheduleRow>) =>
    put(rows.map((row, at) => (at === i ? { ...row, ...patch } : row)));
  const heading = useRef<HTMLHeadingElement>(null);

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
      <ul className="schedule-editor" data-testid="schedule-editor">
        {rows.map((row, i) => (
          <ScheduleRowEditor
            key={i}
            row={row}
            problems={problems[i]}
            skills={skills}
            readOnly={readOnly}
            onChange={(patch) => edit(i, patch)}
            onRemove={() => put(rows.filter((_, at) => at !== i))}
          />
        ))}
      </ul>
      <button
        type="button"
        className="ghost"
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
