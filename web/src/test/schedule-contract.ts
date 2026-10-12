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

const SCHEDULE_KEYS = new Set([
  "id", "name", "cron", "every", "prompt", "command", "script", "then_prompt", "enabled", "skills", "approval_ttl_seconds",
]);

/** The values `script_calls` takes in an agent's file. */
const SCRIPT_CALLS = ["none", "read_only", "gated"];

type Read<T> = { ok: T } | { error: string };

/** `script.limits.MAX_SOURCE_CHARS`: the longest script the parser reads, in characters. */
const MAX_SCRIPT_CHARS = 20_000;

/** `profile_yaml._script`: what is wrong with a script job's own two keys, as far as that
 *  can be said without Python. Whether the script is one Python reads is the server's. */
function scriptError(raw: Record<string, unknown>, where: string): string | null {
  const { script, then_prompt: then } = raw;
  if (then !== undefined && then !== null && !(typeof then === "string" && then.trim()))
    return `${where}: then_prompt must be a non-empty string`;
  if (!script) return null;
  if (typeof script !== "string" || !script.trim()) return `${where}: script must be a non-empty string`;
  if (Array.from(script).length > MAX_SCRIPT_CHARS)
    return `${where}: script is longer than ${MAX_SCRIPT_CHARS} characters`;
  return null;
}

/** `approval_ttl.parse_approval_ttl`: whole seconds from a minute to half a day, or absent. */
function readTtl(value: unknown, where: string): Read<number | null> {
  if (value === null || value === undefined) return { ok: null };
  if (typeof value !== "number" || !Number.isInteger(value) || value < 60 || value > 43_200)
    return { error: `${where}: approval_ttl_seconds must be whole seconds from 60 to 43200` };
  return { ok: value };
}

/**
 * The jobs list once an agent's schedules were saved. The scheduler takes the rows up at
 * once, so the list follows the file: a job of origin `profile` for every row the agent now
 * declares, a row it already had kept in its place with its last run and its pause, and one
 * no longer declared gone. A job made from chat, the memory pass and the jobs of other
 * agents are not the rows' to move.
 */
export function jobsAfterSave<J extends object>(jobs: J[], agent: { id: string; schedules: ScheduleInfo[] }): J[] {
  type Row = Record<string, unknown>;
  const own = (job: Row) => job.agent_id === agent.id && job.origin !== "chat" && job.kind !== "consolidate";
  const rows: Row[] = agent.schedules.map((row) => {
    const id = `${agent.id}/${row.id}`;
    const before = (jobs as Row[]).find((job) => job.id === id);
    const fresh = { next_run: null, last_run: null, running: false, paused: false, failing: null };
    return { ...fresh, ...before, ...row, id, schedule_id: row.id, agent_id: agent.id, origin: "profile" };
  });
  const kept = (jobs as Row[]).flatMap((job) => (own(job) ? rows.filter((row) => row.id === job.id) : [job]));
  const added = rows.filter((row) => !(jobs as Row[]).some((job) => job.id === row.id));
  return [...kept, ...added] as J[];
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
    // A job nudges the agent, runs a command or runs a script: one of the three, never two.
    if ([raw.prompt, raw.command, raw.script].filter(Boolean).length !== 1)
      return { error: "schedule needs exactly one of prompt / command / script" };
    // The prompt a script's output goes on with; beside a prompt or a command it has
    // nothing to go on with, and a form that sent one there has mixed two rows up.
    if (raw.then_prompt !== undefined && raw.then_prompt !== null && !raw.script)
      return { error: "schedule takes then_prompt only beside script" };
    const id = String(raw.id || `job-${index}`);
    const unread = scriptError(raw, `schedule ${id}`);
    if (unread) return { error: unread };
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
      script: (raw.script as string | undefined) ?? null,
      then_prompt: (raw.then_prompt as string | undefined) ?? null,
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
    next.schedules = read.ok.map((row) => ({ ...row, kind: row.script ? "script" : row.command ? "command" : "prompt" }));
  }
  // The list the file now writes; a null clears the key, which reads back as no list.
  if ("tools" in patch) next.declared = { ...(next.declared as object), tools: patch.tools ?? [] };
  // The agents the file now names, which the form reads back; a null names nobody.
  if ("delegates" in patch) {
    next.delegates = patch.delegates ?? [];
    next.declared = { ...(next.declared as object), delegates: next.delegates };
  }
  // The answer to a save already says which names a list has a say over for the agent as
  // it now is. The one name a save moves here is `delegate`: there exactly while the agent
  // hands work out, which the master, a work agent and one naming delegates do.
  if (Array.isArray(next.listable_tools) && ("mode" in patch || "delegates" in patch)) {
    const hands = next.is_master === true || next.mode === "work" || ((next.delegates ?? []) as string[]).length > 0;
    const others = (next.listable_tools as string[]).filter((name) => name !== "delegate");
    next.listable_tools = hands ? [...others, "delegate"].sort() : others;
  }
  // A null clears the key: no server at all, as the profile reads once the key is gone.
  if ("mcp" in patch) next.mcp = patch.mcp ?? [];
  // The two script switches take their own values and nothing else: a label or a string
  // standing in for the boolean is refused. A null clears the key, which reads back as
  // what the crew runs an agent as when its file says neither.
  if ("script_calls" in patch) {
    if (patch.script_calls !== null && !SCRIPT_CALLS.includes(patch.script_calls as string))
      return { error: "script_calls must be none, read_only or gated" };
    next.script_calls = patch.script_calls ?? "read_only";
  }
  if ("script_llm" in patch) {
    if (patch.script_llm !== null && typeof patch.script_llm !== "boolean")
      return { error: "script_llm must be true or false" };
    next.script_llm = patch.script_llm ?? true;
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
