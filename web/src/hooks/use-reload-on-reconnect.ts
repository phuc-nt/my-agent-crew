import { useEffect, useRef } from "react";

/**
 * Calls `reload` each time the live stream comes back after a drop. The stream carries
 * runs, not the crew, the schedules or the totals, so a server restarted meanwhile — with
 * a profile edited, a schedule's next run moved — would otherwise leave them as they were
 * when the stream dropped. The first connection is the page loading, which reads them anyway.
 */
export function useReloadOnReconnect(connected: boolean, reload: () => void): void {
  const latest = useRef(reload);
  latest.current = reload;
  const wasConnected = useRef(false);
  useEffect(() => {
    if (!connected) return;
    if (wasConnected.current) latest.current();
    wasConnected.current = true;
  }, [connected]);
}
