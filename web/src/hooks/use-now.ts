import { useEffect, useState } from "react";

/**
 * The time to read relative labels against, moved on a slow tick.
 *
 * "vừa xong" and "Hôm nay" are claims about the present, and a list left open with nothing
 * arriving would otherwise keep making them for hours, past midnight too. A browser slows
 * or stops the timers of a hidden tab, so coming back into view reads the clock at once
 * rather than showing the old labels until the next tick.
 */
export function useNow(everyMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = () => setNow(new Date());
    const id = window.setInterval(tick, everyMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [everyMs]);
  return now;
}
