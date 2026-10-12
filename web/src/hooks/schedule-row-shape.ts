// One schedule row as the agent form holds it: which of its keys are in use, and what of
// it goes back to the server.
//
// A row keeps the shape the file declares it in, every key present and the ones not in use
// null, so a row nobody touched compares equal to the file and is not counted as a change.
import type { DeclaredProfile } from "../api/types";

/** One schedule as the file declares it: `kind` is derived and never written back. */
export type ScheduleRow = DeclaredProfile["schedules"][number];

/** What a row does when its time comes: the three actions the parser takes one of. */
export type ActionKind = "prompt" | "command" | "script";

/** The parser's bound on a script (`script.limits.MAX_SOURCE_CHARS`), in characters. */
export const MAX_SCRIPT_CHARS = 20_000;

/** A new row, in the shape the server declares rows in, so an untouched one compares equal. */
export function blankSchedule(): ScheduleRow {
  return { id: "", name: "", cron: "", every: null, prompt: "", command: null, enabled: true, skills: [] };
}

/** Which timing a row uses. A row switched to an interval carries `cron: null`. */
export function usesEvery(row: ScheduleRow): boolean {
  return row.cron === null && row.every !== null;
}

/** Which action a row takes. A row switched to a command carries `prompt: null`. */
export function usesCommand(row: ScheduleRow): boolean {
  return row.prompt === null && row.command !== null;
}

/**
 * A row that runs a script: one the file declares so, or one the form's choice turned into
 * one, which holds an empty script until something is typed and, as every row does, null
 * for the two actions it is not. A row of another kind holds `script: null`, and a row from
 * a server older than script jobs has no such key at all.
 */
export function usesScript(row: ScheduleRow): boolean {
  if (typeof row.script !== "string") return false;
  return row.script !== "" || (row.prompt === null && row.command === null);
}

/** Which of the three a row does. The script is asked first: its row carries
 *  `prompt: null`, as a command's does. */
export function actionKind(row: ScheduleRow): ActionKind {
  return usesScript(row) ? "script" : usesCommand(row) ? "command" : "prompt";
}

/**
 * A row as the parser wants it: a blank or switched-off key is left out rather than sent
 * as null, so the file holds one timing and one action and nothing it has to explain.
 *
 * A script row goes back with its script character for character, indentation and the last
 * line break included, and with neither a prompt nor a command: the parser takes exactly
 * one of the three. The prompt its output goes on with is optional, and the parser refuses
 * an empty one, so a box left blank sends no key at all.
 */
export function sendableRow(row: ScheduleRow): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const script = usesScript(row);
  for (const key of ["id", "name", "cron", "every", "prompt", "command"] as const) {
    if (script && (key === "prompt" || key === "command")) continue;
    const value = row[key];
    if (typeof value === "string" && value.trim() !== "") out[key] = value;
  }
  if (script) {
    if (row.script?.trim()) out.script = row.script;
    if (row.then_prompt?.trim()) out.then_prompt = row.then_prompt;
  }
  out.enabled = row.enabled;
  out.skills = row.skills;
  // Written in the file, not the form: a row sent without it would lose it.
  if (typeof row.approval_ttl_seconds === "number") out.approval_ttl_seconds = row.approval_ttl_seconds;
  return out;
}
