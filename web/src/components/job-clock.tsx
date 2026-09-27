import { vi } from "../i18n/vi";
import { clockTime } from "../lib/relative-time";

interface Props {
  iso: string;
  /** The relative words shown just before, which may already carry the time. */
  words: string;
}

/**
 * The clock time after a relative one on a job row: ", lúc 07:00". The row's times keep a
 * title as well, but a phone never hovers, and "sau 3 giờ" or "Hôm qua" alone leaves the
 * person working out when. Words that already say the time, as a later day's "29/09 07:00"
 * does, get nothing added.
 */
export function AtClock({ iso, words }: Props) {
  const at = clockTime(iso);
  return words.includes(at) ? null : <span>{vi.jobRow.atClock(at)}</span>;
}
