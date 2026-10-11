// One schedule row as the agent form holds it: which of its keys are in use, and what of
// it goes back to the server.
//
// A row keeps the shape the file declares it in, every key present and the ones not in use
// null, so a row nobody touched compares equal to the file and is not counted as a change.
import type { DeclaredProfile } from "../api/types";

/** One schedule as the file declares it: `kind` is derived and never written back. */
export type ScheduleRow = DeclaredProfile["schedules"][number];

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
 * A row that runs a script. Its action is written by hand in `agent.yaml`: the form shows
 * it and never makes one, so only a row the file declared this way is one. Such a row
 * carries `prompt: null` and `command: null`, and a row from a server older than script
 * jobs has no `script` key at all.
 */
export function usesScript(row: ScheduleRow): boolean {
  return typeof row.script === "string" && row.script !== "";
}

/**
 * A row as the parser wants it: a blank or switched-off key is left out rather than sent
 * as null, so the file holds one timing and one action and nothing it has to explain.
 *
 * A script row goes back with the script it came with, character for character, and with
 * neither a prompt nor a command: the parser takes exactly one of the three, and whatever
 * the form sent in place of the script would replace the job the file describes.
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
    out.script = row.script;
    // Allowed beside a script only, and optional there: a row without one sends no key.
    if (typeof row.then_prompt === "string") out.then_prompt = row.then_prompt;
  }
  out.enabled = row.enabled;
  out.skills = row.skills;
  // Written in the file, not the form: a row sent without it would lose it.
  if (typeof row.approval_ttl_seconds === "number") out.approval_ttl_seconds = row.approval_ttl_seconds;
  return out;
}
