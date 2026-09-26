import { vi } from "../i18n/vi";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Times reach the client in UTC and are read on the viewer's own calendar. "Hôm qua" is
 * about the day the person lived through, not the server's: a message at 23:00 in Hanoi
 * is yesterday's by 00:30, although both instants share a UTC date.
 */
function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "24/09", built by hand: Intl's vi-VN date differs between ICU builds ("24-09" in Node). */
function shortDate(date: Date): string {
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}`;
}

function parse(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Whole local days from today to the instant: 0 today, -1 yesterday, 1 tomorrow. */
export function dayOffset(iso: string, now: Date = new Date()): number | null {
  const date = parse(iso);
  // Rounded, since a day that changes clocks is 23 or 25 hours long.
  return date === null ? null : Math.round((startOfDay(date) - startOfDay(now)) / DAY);
}

export type DayGroup = keyof typeof vi.time.groups;

/** The header a row sorts under. A timestamp a skewed clock put ahead still reads as today. */
export function dayGroup(iso: string, now: Date = new Date()): DayGroup {
  const offset = dayOffset(iso, now);
  if (offset === null) return "older";
  if (offset >= 0) return "today";
  return offset === -1 ? "yesterday" : "older";
}

/** How long ago, in the fewest words that still order a list: "5 phút", "Hôm qua", "12/09". */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const date = parse(iso);
  if (date === null) return iso;
  const ms = now.getTime() - date.getTime();
  if (ms < MINUTE) return vi.time.justNow;
  if (ms < HOUR) return vi.time.minutes(Math.floor(ms / MINUTE));
  const offset = dayOffset(iso, now);
  if (offset === 0) return vi.time.hours(Math.floor(ms / HOUR));
  if (offset === -1) return vi.time.yesterday;
  return shortDate(date);
}

/** How long until something scheduled: "sau 5 phút", "sau 3 giờ", then the date itself. */
export function timeUntil(iso: string, now: Date = new Date()): string {
  const date = parse(iso);
  if (date === null) return iso;
  const ms = date.getTime() - now.getTime();
  if (ms < MINUTE) return vi.time.soon;
  if (ms < HOUR) return vi.time.inMinutes(Math.floor(ms / MINUTE));
  if (ms < DAY) return vi.time.inHours(Math.floor(ms / HOUR));
  return `${shortDate(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
