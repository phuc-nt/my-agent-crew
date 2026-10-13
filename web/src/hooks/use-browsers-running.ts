// Whose browser is up now, for the machine's card on the connections page.
//
// The rest of that page changes only by the page's own doing, and is read once. This does
// not: an agent's call brings its browser up, an idle one stops by itself, and a person stops
// one from the agent's own page. So it is read when the card is drawn, however long ago the
// page's own answer came, and again every few seconds while the page is looked at.
//
// Only this one fact is taken of each answer: the routes a person may be half way through
// changing on the same page are left as they are. A machine with no browser to start has
// none up, and is asked nothing.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { BrowserConnection } from "../api/types";
import { BROWSER_POLL_MS } from "./use-agent-browser";
import { useWhileSeen } from "./use-while-seen";

/** The ids of the agents whose browser is up: the page's own answer until a newer one. */
export function useBrowsersRunning(browser: BrowserConnection): string[] {
  const [read, setRead] = useState<string[] | null>(null);
  const startable = browser.enabled && browser.installed;
  // Answers can cross on the wire: one asked no later than what is on screen never replaces it.
  const asked = useRef(0);
  const shown = useRef(0);

  const look = useCallback(async () => {
    const mine = ++asked.current;
    try {
      const answer = (await api.connections()).browser;
      if (mine <= shown.current || !answer) return;
      shown.current = mine;
      setRead(answer.running);
    } catch {
      // What is on screen stays: the next read says, and the page's own reads report a
      // server that does not answer.
    }
  }, []);

  useEffect(() => {
    if (startable) void look();
  }, [look, startable]);
  useWhileSeen(look, BROWSER_POLL_MS, startable);

  return startable ? (read ?? browser.running) : browser.running;
}
