import { useRef } from "react";
import { type ActionKind, actionKind, type ScheduleRow } from "../../hooks/schedule-row-shape";
import { vi } from "../../i18n/vi";
import { TextField } from "./fields";
import { Choice, SkillPicker } from "./schedule-parts";
import { ScheduleScriptFields } from "./schedule-script-action";

interface Props {
  row: ScheduleRow;
  /** Why the action cannot be saved as it is, named under its box. */
  problem?: string;
  /** The agent's loaded skills, offered to the turn a row opens. */
  skills: string[];
  readOnly: boolean;
  onChange: (patch: Partial<ScheduleRow>) => void;
}

const ACTIONS = [
  ["prompt", vi.editor.schedulePrompt],
  ["command", vi.editor.scheduleCommand],
  ["script", vi.editor.scheduleScript],
] as const;

/** What a kind held when the row was switched away from it. */
interface Kept {
  text: string;
  /** A script's prompt to follow; the other two have none. */
  then: string | null;
  skills: string[];
}

/**
 * What a schedule does when its time comes: nudge the agent, run a shell command, or run a
 * script. The parser takes exactly one of the three, so they are one choice with one box,
 * and the two keys not chosen are null, as the file declares a row.
 *
 * Each kind keeps its own words. Switching brings back what the kind switched to held
 * before, or an empty box, and never what the kind being left holds: a prompt does not turn
 * up in the script box as code to run, and a script is not sent to the model as a prompt.
 * What was typed is not lost either; tapping back finds it, for as long as the row is on
 * the page. Only the kind chosen when the form is saved is written.
 *
 * Skills are attached to the turn a row opens: a prompt's own, or the one a script's
 * output goes on to. A command opens none. Each kind keeps its own list like its own words,
 * a command the one its row was written with, so going round and back changes nothing.
 */
export function ScheduleAction({ row, problem, skills, readOnly, onChange }: Props) {
  const kept = useRef<Partial<Record<ActionKind, Kept>>>({});
  const kind = actionKind(row);
  const thenPrompt = row.then_prompt ?? "";

  const pick = (to: ActionKind) => {
    kept.current[kind] = { text: row[kind] ?? "", then: row.then_prompt ?? null, skills: row.skills };
    const back = kept.current[to];
    const patch: Partial<ScheduleRow> = { [kind]: null, [to]: back?.text ?? "" };
    if (kind === "script" || to === "script") patch.then_prompt = to === "script" ? (back?.then ?? null) : null;
    // A command written by hand may list skills this form never showed: they go on with
    // the row to the kind where they can be seen and taken off. They are the command's own
    // all the same, and come back with it; a kind new to the row starts with none.
    patch.skills = back?.skills ?? (kind === "command" ? row.skills : []);
    onChange(patch);
  };

  // A script opens a turn only when it has a prompt to go on with; skills the row already
  // carries stay in sight without one, so they can be taken off.
  const opensTurn = kind === "prompt" || (kind === "script" && (thenPrompt.trim() !== "" || row.skills.length > 0));

  return (
    <>
      <Choice label={vi.editor.scheduleAction} value={kind} options={ACTIONS} disabled={readOnly} onPick={pick} />
      {kind === "script" ? (
        <ScheduleScriptFields
          script={row.script ?? ""}
          thenPrompt={thenPrompt}
          problem={problem}
          readOnly={readOnly}
          onChange={onChange}
        />
      ) : (
        <TextField
          label={kind === "command" ? vi.editor.scheduleCommand : vi.editor.schedulePrompt}
          value={row[kind] ?? ""}
          error={problem}
          mono={kind === "command"}
          rows={kind === "command" ? 2 : 3}
          disabled={readOnly}
          onChange={(text) => onChange({ [kind]: text })}
        />
      )}
      {opensTurn && (
        <SkillPicker
          available={skills}
          chosen={row.skills}
          disabled={readOnly}
          onChange={(chosen) => onChange({ skills: chosen })}
        />
      )}
    </>
  );
}
