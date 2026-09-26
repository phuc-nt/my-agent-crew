import { useEffect, useState } from "react";
import { vi } from "../i18n/vi";

const SECOND = 1000;
const URGENT_MS = 60 * SECOND;

/** Milliseconds left until `expiresAt`, re-read every second and never below zero; null
 *  when there is no deadline. The instant is UTC, but a difference between two instants
 *  does not depend on the viewer's zone. */
export function useRemaining(expiresAt: string | undefined): number | null {
  const deadline = expiresAt ? Date.parse(expiresAt) : Number.NaN;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (Number.isNaN(deadline)) return;
    setNow(Date.now());
    const timer = window.setInterval(() => {
      const tick = Date.now();
      setNow(tick);
      // Nothing left to count: stop re-rendering a row that already says it is over.
      if (tick >= deadline) window.clearInterval(timer);
    }, SECOND);
    return () => window.clearInterval(timer);
  }, [deadline]);

  return Number.isNaN(deadline) ? null : Math.max(0, deadline - now);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "9:58" — a stopwatch reading, not a relative time: the last minute is counted in seconds
 *  because that is when the person decides whether there is still time to read the request.
 *  The time a request waits is configurable, and a day of it reads "24:00:00", not "1440:00". */
function stopwatch(ms: number): string {
  // Rounded up, so the chip reads 0:01 until the moment it turns into "expired".
  const seconds = Math.ceil(ms / SECOND);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds % 60)}` : `${minutes}:${pad(seconds % 60)}`;
}

/** How long a waiting request has before the server closes it on its own. */
export function ExpiryCountdown({ remaining }: { remaining: number }) {
  const expired = remaining <= 0;
  const tone = expired ? " expired" : remaining <= URGENT_MS ? " urgent" : "";
  return (
    // A timer is not a live region by default, which is right: a reader announcing every
    // second would drown the request it is counting down.
    <span className={`expiry-chip${tone}`} role="timer" data-testid="expiry-countdown">
      {expired ? vi.attentionExpired : vi.attentionExpiresIn(stopwatch(remaining))}
    </span>
  );
}
