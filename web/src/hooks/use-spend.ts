import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SpendInfo } from "../api/types";

/** How often the header asks again; the server asks OpenRouter at most once a minute. */
export const SPEND_POLL_MS = 30_000;

/**
 * What each provider has cost, kept fresh for the header: asked on mount, every
 * `SPEND_POLL_MS` while the page is in view, and again the moment it comes back into view.
 * A failed ask keeps the last figures rather than blanking the pill.
 */
export function useSpend(): SpendInfo | null {
  const [spend, setSpend] = useState<SpendInfo | null>(null);
  useEffect(() => {
    let live = true;
    const load = () => {
      if (document.visibilityState === "hidden") return;
      api.spend().then(
        (next) => live && setSpend(next),
        () => undefined,
      );
    };
    load();
    const timer = window.setInterval(load, SPEND_POLL_MS);
    document.addEventListener("visibilitychange", load);
    return () => {
      live = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, []);
  return spend;
}
