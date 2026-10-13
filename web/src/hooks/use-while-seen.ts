// A read done again every so often for as long as the page is looked at.
//
// A hidden tab asks nothing, and coming back into view reads at once and starts the clock
// from then. The first read is the caller's own: this only does the ones after it.
import { useEffect } from "react";

export function useWhileSeen(read: () => unknown, everyMs: number, on = true): void {
  useEffect(() => {
    if (!on) return;
    let timer: number | undefined;
    const watch = () => {
      window.clearInterval(timer);
      timer = undefined;
      if (document.visibilityState !== "visible") return;
      timer = window.setInterval(() => void read(), everyMs);
    };
    const seen = () => {
      if (document.visibilityState === "visible") void read();
      watch();
    };
    watch();
    document.addEventListener("visibilitychange", seen);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", seen);
    };
  }, [read, everyMs, on]);
}
