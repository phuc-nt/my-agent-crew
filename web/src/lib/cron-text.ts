// A schedule's timing in words: the shapes people actually write, read the way the
// scheduler reads them (minute hour day month weekday, local time, 0 and 7 both Sunday).
//
// Anything outside those shapes comes back exactly as written. A paraphrase that is
// nearly right — "every day" for a cron that also names a month — is worse than the raw
// string, because it is the one the person believes.
import { vi } from "../i18n/vi";

const words = vi.jobRow.cron;
const pad = (n: number) => String(n).padStart(2, "0");

/** A plain number within `low..high`, or null. */
function num(text: string, low: number, high: number): number | null {
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  return n >= low && n <= high ? n : null;
}

/**
 * The N of a `*` + `/N` step that divides `cycle` (60 minutes, 24 hours), or null.
 *
 * The scheduler restarts a step at every hour or midnight, so `*` + `/7` fires at :56
 * and again at :00. Only a divisor keeps every gap equal, which "every N" promises.
 */
function step(text: string, cycle: number): number | null {
  const match = /^\*\/(\d+)$/.exec(text);
  const n = match ? num(match[1], 1, cycle - 1) : null;
  return n !== null && cycle % n === 0 ? n : null;
}

/** Plain numbers separated by commas, each in range, or null. */
function list(text: string, low: number, high: number): number[] | null {
  const values = text.split(",").map((part) => num(part, low, high));
  return values.every((v) => v !== null) ? (values as number[]) : null;
}

/** The weekdays a field names through numbers, lists and ranges; 7 is folded onto Sunday. */
function weekdays(text: string): Set<number> | null {
  const days = new Set<number>();
  for (const part of text.split(",")) {
    const [from, to = from] = part.split("-");
    const start = num(from, 0, 7);
    const end = num(to, 0, 7);
    if (start === null || end === null || start > end) return null;
    for (let day = start; day <= end; day++) days.add(day % 7);
  }
  return days;
}

function onDays(days: Set<number>, time: string): string {
  if (days.size === 7) return words.daily(time);
  const key = [...days].sort().join(",");
  if (key === "1,2,3,4,5") return words.weekdays(time);
  if (key === "0,6") return words.weekend(time);
  // Monday first and Sunday last, the order a week is read in.
  const names = [1, 2, 3, 4, 5, 6, 0].filter((day) => days.has(day)).map((day) => words.days[day]);
  return words.weekly(names.join(", "), time);
}

/** The hourly shapes: every minute, every N minutes, every hour or every N hours. */
function repeating(minute: string, hour: string): string | null {
  if (hour === "*") {
    if (minute === "*") return words.every(1, words.units.m);
    const minutes = step(minute, 60);
    if (minutes !== null) return words.every(minutes, words.units.m);
  }
  const hours = hour === "*" ? 1 : step(hour, 24);
  const at = num(minute, 0, 59);
  if (hours === null || at === null) return null;
  const every = words.every(hours, words.units.h);
  return at === 0 ? every : words.atMinute(every, at);
}

/** "Mỗi ngày 07:00" for `0 7 * * *`; the cron itself for a shape not listed here. */
export function cronText(cron: string): string {
  const fields = cron.trim().split(/\s+/);
  if (fields.length !== 5) return cron;
  const [minute, hour, day, month, weekday] = fields;
  if (month !== "*") return cron;
  if (day === "*" && weekday === "*") {
    const often = repeating(minute, hour);
    if (often !== null) return often;
  }
  const at = num(minute, 0, 59);
  const hours = list(hour, 0, 23);
  if (at === null || hours === null) return cron;
  const time = hours.map((h) => `${pad(h)}:${pad(at)}`).join(", ");
  if (day === "*") {
    const days = weekday === "*" ? new Set([0, 1, 2, 3, 4, 5, 6]) : weekdays(weekday);
    return days ? onDays(days, time) : cron;
  }
  const date = num(day, 1, 31);
  return date !== null && weekday === "*" ? words.monthly(date, time) : cron;
}

/** "Mỗi 30 phút" for the `every: 30m` shorthand, in the units the scheduler accepts. */
export function everyText(every: string): string {
  const match = /^(\d+)\s*([smhd])$/.exec(every.trim().toLowerCase());
  return match ? words.every(Number(match[1]), words.units[match[2]]) : every;
}

/** A schedule's timing in words, whichever of the two keys it is written with. */
export function scheduleText(cron: string | null, every: string | null): string {
  if (cron) return cronText(cron);
  return every ? everyText(every) : "";
}
