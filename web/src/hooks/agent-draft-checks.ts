// What the agent form refuses to send, and how what it does send is shaped.
//
// The server is the authority on every rule here and refuses a bad profile whole. Checking
// the few fields a person types free-hand before the request goes out is what turns
// "Không lưu được: agent coach: schedule needs exactly one of cron / every" into a message
// next to the box that caused it, with the save held until it is fixed.
import type { AgentPatch, DeclaredProfile } from "../api/types";
import { vi } from "../i18n/vi";

/** One schedule as the file declares it: `kind` is derived and never written back. */
export type ScheduleRow = DeclaredProfile["schedules"][number];

export interface RowProblems {
  timing?: string;
  action?: string;
}

export interface DraftProblems {
  chatId?: string;
  memoryConsolidate?: string;
  /** Index-aligned with the draft's rows; a row with nothing wrong has no entry. */
  schedules?: Record<number, RowProblems>;
}

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

const CRON_FIELD = /^[\d*,/-]+$/;
const EVERY = /^(\d+)\s*([smhd])$/i;
const UNIT_SECONDS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400 };

/** The shape `CronSpec.parse` accepts; the ranges are left to the server's 422. */
export function isCronShape(text: string): boolean {
  const fields = text.trim().split(/\s+/);
  return fields.length === 5 && fields.every((field) => CRON_FIELD.test(field));
}

function isEvery(text: string): boolean {
  const match = EVERY.exec(text.trim());
  return match !== null && Number(match[1]) * UNIT_SECONDS[match[2].toLowerCase()] >= 60;
}

function rowProblems(row: ScheduleRow): RowProblems {
  const found: RowProblems = {};
  if (usesEvery(row)) {
    if (!isEvery(row.every ?? "")) found.timing = vi.editor.everyInvalid;
  } else if (!isCronShape(row.cron ?? "")) {
    found.timing = vi.editor.cronInvalid;
  }
  const action = usesCommand(row) ? row.command : row.prompt;
  if (!action?.trim())
    found.action = usesCommand(row) ? vi.editor.commandMissing : vi.editor.promptMissing;
  return found;
}

/**
 * What is wrong with the keys the person changed.
 *
 * Only changed keys: a profile edited by hand may already hold something this form would
 * not have let through, and holding an unrelated save hostage to it helps nobody.
 */
export function draftProblems(draft: AgentPatch, dirty: (keyof AgentPatch)[]): DraftProblems {
  const problems: DraftProblems = {};
  if (dirty.includes("telegram") && draft.telegram) {
    const chatId = draft.telegram.chat_id;
    if (!Number.isSafeInteger(chatId) || chatId === 0) problems.chatId = vi.editor.chatIdInvalid;
  }
  const consolidate = draft.memory_consolidate?.trim() ?? "";
  if (dirty.includes("memory_consolidate") && consolidate && !isCronShape(consolidate))
    problems.memoryConsolidate = vi.editor.cronInvalid;
  if (dirty.includes("schedules")) {
    const rows = (draft.schedules ?? []) as ScheduleRow[];
    const byRow: Record<number, RowProblems> = {};
    rows.forEach((row, at) => {
      const found = rowProblems(row);
      if (found.timing || found.action) byRow[at] = found;
    });
    if (Object.keys(byRow).length > 0) problems.schedules = byRow;
  }
  return problems;
}

export function hasProblems(problems: DraftProblems): boolean {
  return Object.keys(problems).length > 0;
}

/** A row as the parser wants it: a blank or switched-off key is left out rather than sent
 * as null, so the file holds one timing and one action and nothing it has to explain. */
function sendableRow(row: ScheduleRow): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["id", "name", "cron", "every", "prompt", "command"] as const) {
    const value = row[key];
    if (typeof value === "string" && value.trim() !== "") out[key] = value;
  }
  out.enabled = row.enabled;
  out.skills = row.skills;
  return out;
}

/** The PATCH body for the changed keys. An emptied consolidation cron is sent as null,
 * which removes the key, rather than as "" left sitting in the file. */
export function toPatch(draft: AgentPatch, dirty: (keyof AgentPatch)[]): AgentPatch {
  const patch: AgentPatch = {};
  for (const key of dirty) Object.assign(patch, { [key]: draft[key] });
  if ("memory_consolidate" in patch) patch.memory_consolidate = draft.memory_consolidate?.trim() || null;
  if (Array.isArray(patch.schedules))
    patch.schedules = (patch.schedules as ScheduleRow[]).map(sendableRow);
  return patch;
}
