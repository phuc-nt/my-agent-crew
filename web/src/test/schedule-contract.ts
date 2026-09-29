// The server's rules for the profile keys the fakes used to take on trust.
//
// Both fakes once merged a patch into the agent as sent. A schedule row carrying `kind`,
// or both a cron and an interval, was accepted here and refused by the real parser, so
// the editor's own tests passed while every save of a new row failed in production.
// These are the checks `profile_yaml._schedule` and `channels.parse_telegram` make, in
// their order, so a fake refuses what the server refuses and answers with what it would
// declare back.
import type { ScheduleInfo, TelegramBlock } from "../api/types";

type Declared = Omit<ScheduleInfo, "kind">;

const SCHEDULE_KEYS = new Set(["id", "name", "cron", "every", "prompt", "command", "enabled", "skills", "approval_ttl_seconds"]);

type Read<T> = { ok: T } | { error: string };

/** `approval_ttl.parse_approval_ttl`: whole seconds from a minute to half a day, or absent. */
function readTtl(value: unknown, where: string): Read<number | null> {
  if (value === null || value === undefined) return { ok: null };
  if (typeof value !== "number" || !Number.isInteger(value) || value < 60 || value > 43_200)
    return { error: `${where}: approval_ttl_seconds must be whole seconds from 60 to 43200` };
  return { ok: value };
}

/** `texts.RESTART_REASON_SCHEDULES`, word for word: the server's reason for a restart. */
export const SCHEDULES_RESTART_REASON = "Thay đổi lịch chạy chỉ có hiệu lực sau khi khởi động lại máy chủ.";

/** What a save answers in `restart_required`. Only the scheduler is built once, at boot, so
 *  only the two keys it reads ask for a restart — taking a job away as much as adding one,
 *  since the clock keeps the jobs it started with. A bot is rebuilt live. */
export function restartRequired(patch: Record<string, unknown>): string[] {
  return "schedules" in patch || "memory_consolidate" in patch ? [SCHEDULES_RESTART_REASON] : [];
}

/** The rows a patch's `schedules` stands for, as `declared.schedules` reports them. */
export function readSchedules(value: unknown): Read<Declared[]> {
  if (value === null || value === undefined) return { ok: [] };
  if (!Array.isArray(value)) return { error: "schedules must be a list" };
  const rows: Declared[] = [];
  for (const [index, item] of value.entries()) {
    const raw = item as Record<string, unknown>;
    const unknown = Object.keys(raw).filter((key) => !SCHEDULE_KEYS.has(key)).sort();
    if (unknown.length > 0) return { error: `schedule has unknown keys ${JSON.stringify(unknown)}` };
    if (Boolean(raw.cron) === Boolean(raw.every))
      return { error: "schedule needs exactly one of cron / every" };
    if (Boolean(raw.prompt) === Boolean(raw.command))
      return { error: "schedule needs exactly one of prompt / command" };
    const id = String(raw.id || `job-${index}`);
    // `profile_edit.validated`: the scheduler keys jobs by id, so a second one would
    // replace the first without a word.
    if (rows.some((row) => row.id === id)) return { error: `two schedules share the id ${id}` };
    const ttl = readTtl(raw.approval_ttl_seconds, `schedule ${id}`);
    if ("error" in ttl) return ttl;
    rows.push({
      id,
      name: String(raw.name || id),
      cron: (raw.cron as string | undefined) ?? null,
      every: (raw.every as string | undefined) ?? null,
      prompt: (raw.prompt as string | undefined) ?? null,
      command: (raw.command as string | undefined) ?? null,
      enabled: raw.enabled === undefined ? true : Boolean(raw.enabled),
      skills: ((raw.skills as unknown[] | undefined) ?? []).map(String),
      approval_ttl_seconds: ttl.ok,
    });
  }
  return { ok: rows };
}

function readTelegram(value: unknown): Read<TelegramBlock | null> {
  if (value === null || value === undefined) return { ok: null };
  const raw = value as Record<string, unknown>;
  const chatId = raw.chat_id;
  if (typeof chatId !== "number" || !Number.isInteger(chatId))
    return { error: "telegram chat_id must be an integer" };
  const tokenEnv = String(raw.token_env ?? "").trim();
  if (!tokenEnv) return { error: "telegram needs a token_env" };
  if (chatId === 0) return { error: "telegram needs a chat_id" };
  const ttl = readTtl(raw.approval_ttl_seconds, "telegram");
  if ("error" in ttl) return ttl;
  const block: TelegramBlock = { token_env: tokenEnv, chat_id: chatId };
  if (ttl.ok !== null) block.approval_ttl_seconds = ttl.ok;
  return { ok: block };
}

/**
 * The agent a patch turns `agent` into, or the reason the server would refuse it.
 *
 * Keys other than these three are merged as sent, as before. The result is a new object:
 * merging into the one passed in would edit a fixture shared by every later test.
 */
export function applyAgentPatch<T extends object>(agent: T, patch: Record<string, unknown>): Read<T> {
  const next: Record<string, unknown> = { ...agent, ...patch };
  if ("schedules" in patch) {
    const read = readSchedules(patch.schedules);
    if ("error" in read) return read;
    const declared = (agent as { declared?: object }).declared ?? {};
    next.declared = { ...declared, schedules: read.ok };
    next.schedules = read.ok.map((row) => ({ ...row, kind: row.command ? "command" : "prompt" }));
  }
  // A null clears the key, and a cleared consolidation reads back as no cron at all.
  if ("memory_consolidate" in patch) next.memory_consolidate = patch.memory_consolidate ?? "";
  // While consolidation is on its job runs as `memory-consolidate` beside the rows.
  const rows = (next.declared as { schedules?: Declared[] } | undefined)?.schedules ?? [];
  if (next.memory_consolidate && rows.some((row) => row.id === "memory-consolidate"))
    return { error: "two schedules share the id memory-consolidate" };
  if ("telegram" in patch) {
    const read = readTelegram(patch.telegram);
    if ("error" in read) return read;
    next.telegram = read.ok;
  }
  return { ok: next as T };
}
