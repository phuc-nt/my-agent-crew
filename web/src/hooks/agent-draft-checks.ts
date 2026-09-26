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
  /**
   * A box the save needs is still empty. It holds the save like any other problem, but is
   * not called an error until a save is tried: a row just added is empty, not wrong.
   */
  unfilled?: true;
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

/** The box a row's timing is typed in, and the one its action is. */
const timingOf = (row: ScheduleRow) => (usesEvery(row) ? row.every : row.cron) ?? "";
const actionOf = (row: ScheduleRow) => (usesCommand(row) ? row.command : row.prompt) ?? "";

// Minute, hour, day, month, weekday: the ranges `CronSpec.parse` holds each field to.
const CRON_RANGES = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 7],
] as const;
const CRON_PART = /^(?:\*|(\d+)(?:-(\d+))?)(?:\/(\d+))?$/;
const EVERY = /^(\d+)\s*([smhd])$/i;
const UNIT_SECONDS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400 };

/** One field: `*`, `n` or `a-b`, each with an optional `/step`, comma-separated. */
function isCronField(text: string, low: number, high: number): boolean {
  return text.split(",").every((part) => {
    const match = CRON_PART.exec(part);
    if (!match) return false;
    const [, from, to, step] = match;
    const start = from === undefined ? low : Number(from);
    const end = from === undefined ? high : Number(to ?? from);
    return low <= start && start <= end && end <= high && (step === undefined || Number(step) >= 1);
  });
}

/** What `CronSpec.parse` accepts, ranges included: the server's refusal of hour 25 would
 * come back in English at the top of the page rather than next to the box. */
export function isCron(text: string): boolean {
  const fields = text.trim().split(/\s+/);
  return fields.length === 5 && fields.every((field, at) => isCronField(field, CRON_RANGES[at][0], CRON_RANGES[at][1]));
}

function isEvery(text: string): boolean {
  const match = EVERY.exec(text.trim());
  return match !== null && Number(match[1]) * UNIT_SECONDS[match[2].toLowerCase()] >= 60;
}

/** What is wrong with a row; a box still blank is named only when `reveal` says so. */
function rowProblems(row: ScheduleRow, reveal: boolean, unfilled: () => void): RowProblems {
  const found: RowProblems = {};
  const timing = timingOf(row);
  if (!timing.trim() && !reveal) unfilled();
  else if (usesEvery(row) ? !isEvery(timing) : !isCron(timing))
    found.timing = usesEvery(row) ? vi.editor.everyInvalid : vi.editor.cronInvalid;
  if (actionOf(row).trim()) return found;
  if (!reveal) unfilled();
  else found.action = usesCommand(row) ? vi.editor.commandMissing : vi.editor.promptMissing;
  return found;
}

/**
 * What is wrong with the keys the person changed.
 *
 * Only changed keys: a profile edited by hand may already hold something this form would
 * not have let through, and holding an unrelated save hostage to it helps nobody.
 *
 * A box the person has not filled yet — a new row's cron, the chat id of a channel just
 * turned on — is `unfilled` until `reveal` (a save was tried), and named after that.
 * `base` is what the file holds, which tells an emptied chat id from one never set.
 */
export function draftProblems(
  draft: AgentPatch,
  dirty: (keyof AgentPatch)[],
  base: AgentPatch = {},
  reveal = false,
): DraftProblems {
  const problems: DraftProblems = {};
  const unfilled = () => {
    problems.unfilled = true;
  };
  if (dirty.includes("telegram") && draft.telegram) {
    const chatId = draft.telegram.chat_id;
    if (chatId === 0 && !base.telegram?.chat_id && !reveal) unfilled();
    else if (!Number.isSafeInteger(chatId) || chatId === 0) problems.chatId = vi.editor.chatIdInvalid;
  }
  const consolidate = draft.memory_consolidate?.trim() ?? "";
  if (dirty.includes("memory_consolidate") && consolidate && !isCron(consolidate))
    problems.memoryConsolidate = vi.editor.cronInvalid;
  if (dirty.includes("schedules")) {
    const rows = (draft.schedules ?? []) as ScheduleRow[];
    const byRow: Record<number, RowProblems> = {};
    rows.forEach((row, at) => {
      const found = rowProblems(row, reveal, unfilled);
      if (found.timing || found.action) byRow[at] = found;
    });
    if (Object.keys(byRow).length > 0) problems.schedules = byRow;
  }
  return problems;
}

/** Anything that holds the save, whether or not it is on screen yet. */
export function hasProblems(problems: DraftProblems): boolean {
  return Object.keys(problems).length > 0;
}

/** Anything named next to a box: what the banner and the disabled save button stand for. */
export function problemsShown(problems: DraftProblems): boolean {
  return Object.keys(problems).some((key) => key !== "unfilled");
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
