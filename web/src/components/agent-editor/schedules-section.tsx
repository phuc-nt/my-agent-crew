import type { ScheduleInfo } from "../../api/types";
import type { AgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { TextField } from "./fields";

interface Props {
  form: AgentDraft;
  readOnly: boolean;
}

/** Cron jobs that open a conversation with the agent on their own. Changing one takes a
 * restart, which the save banner says; the scheduler reads its table only at boot. */
export function SchedulesSection({ form, readOnly }: Props) {
  const rows = (form.draft.schedules ?? []) as Partial<ScheduleInfo>[];
  const put = (next: Partial<ScheduleInfo>[]) => form.set("schedules", next);
  const edit = (i: number, patch: Partial<ScheduleInfo>) =>
    put(rows.map((row, at) => (at === i ? { ...row, ...patch } : row)));

  return (
    <section className="editor-section" data-testid="section-schedules">
      <h3>{vi.editor.sectionSchedules}</h3>
      <p className="muted">{vi.editor.schedulesHint}</p>
      <ul className="schedule-editor" data-testid="schedule-editor">
        {rows.map((row, i) => (
          <li key={i} className="crew-card">
            <div className="row">
              <TextField
                label={vi.editor.scheduleId}
                value={row.id ?? ""}
                disabled={readOnly}
                onChange={(v) => edit(i, { id: v })}
              />
              <TextField
                label={vi.editor.scheduleCron}
                value={row.cron ?? ""}
                disabled={readOnly}
                onChange={(v) => edit(i, { cron: v })}
              />
              <button
                type="button"
                className="ghost"
                disabled={readOnly}
                onClick={() => put(rows.filter((_, at) => at !== i))}
              >
                {vi.editor.remove}
              </button>
            </div>
            <TextField
              label={vi.editor.schedulePrompt}
              value={row.prompt ?? ""}
              disabled={readOnly}
              onChange={(v) => edit(i, { prompt: v })}
            />
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="ghost"
        disabled={readOnly}
        onClick={() => put([...rows, { id: "", kind: "prompt", cron: "", prompt: "", enabled: true }])}
      >
        {vi.editor.addSchedule}
      </button>
    </section>
  );
}
