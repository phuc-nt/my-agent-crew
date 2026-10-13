// When a schedule's timing, as typed, is one the server's parser takes.

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

export function isEvery(text: string): boolean {
  const match = EVERY.exec(text.trim());
  return match !== null && Number(match[1]) * UNIT_SECONDS[match[2].toLowerCase()] >= 60;
}
