// One agent's browser as it runs now, and the two things a person can do to it at once.
//
// Nobody tells the page when a browser starts, when a tab opens or when an idle one is
// stopped, so the state is read again every few seconds for as long as the page is looked
// at. A hidden tab asks nothing, and coming back into view reads at once.
//
// The state belongs to one agent: the card that uses this is keyed by the agent's id, so
// another agent starts from nothing rather than from the last one's answer.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { AgentBrowser, BrowserMode } from "../api/types";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";
import { useWhileSeen } from "./use-while-seen";

export const BROWSER_POLL_MS = 5_000;

export interface BrowserNote {
  tone: "warn" | "danger";
  text: string;
}

export interface AgentBrowserController {
  /** The last answer. Null until the first, and for good from a server without the route. */
  browser: AgentBrowser | null;
  /** What is in flight: "stop", the id of the tab being closed, or null. */
  pending: "stop" | number | null;
  /** What the last action has to say, else why the state could not be read again. */
  note: BrowserNote | null;
  stop: () => void;
  closeTab: (tabId: number) => void;
}

/**
 * `savedMode` is the agent's `browser` key as its file has it. A save that changes it is
 * read at once: set to off, the server stops the browser there and then.
 */
export function useAgentBrowser(agentId: string, savedMode: BrowserMode | undefined): AgentBrowserController {
  const [browser, setBrowser] = useState<AgentBrowser | null>(null);
  // The route answered 404: a server older than it, or an agent the crew no longer has.
  const [missing, setMissing] = useState(false);
  const [pending, setPending] = useState<"stop" | number | null>(null);
  const [acted, setActed] = useState<BrowserNote | null>(null);
  const [readError, setReadError] = useState<string | null>(null);
  // Answers can cross on the wire. Each read takes a number, and one asked no later than
  // what is on screen never replaces it.
  const asked = useRef(0);
  const shown = useRef(0);

  const read = useCallback(async () => {
    const mine = ++asked.current;
    try {
      const answer = await api.agentBrowser(agentId);
      if (mine <= shown.current) return;
      shown.current = mine;
      setBrowser(answer);
      setReadError(null);
    } catch (e) {
      if (mine <= shown.current) return;
      if (e instanceof ApiError && e.status === 404) {
        setMissing(true);
        setBrowser(null);
      } else setReadError(errorText(e));
    }
  }, [agentId]);

  useEffect(() => {
    void read();
  }, [read, savedMode]);

  useWhileSeen(read, BROWSER_POLL_MS, !missing);

  const act = useCallback(
    async (what: "stop" | number, work: () => Promise<unknown>) => {
      setPending(what);
      setActed(null);
      try {
        await work();
      } catch (e) {
        // A tab that is gone already is no failure of the request: the server says so in its
        // own sentence, and the read below shows the tabs there are.
        const gone = what !== "stop" && e instanceof ApiError && e.status === 404;
        setActed(
          gone ? { tone: "warn", text: errorText(e) } : { tone: "danger", text: vi.connectionsPage.failed(errorText(e)) },
        );
      }
      // Whatever was asked before the action ended describes the browser before it.
      shown.current = asked.current;
      await read();
      setPending(null);
    },
    [read],
  );

  const stop = useCallback(() => void act("stop", () => api.stopAgentBrowser(agentId)), [act, agentId]);
  const closeTab = useCallback(
    (tabId: number) => void act(tabId, () => api.closeAgentBrowserTab(agentId, tabId)),
    [act, agentId],
  );

  const note = acted ?? (readError === null ? null : { tone: "danger" as const, text: vi.browser.card.readFailed(readError) });
  return { browser: missing ? null : browser, pending, note: missing ? null : note, stop, closeTab };
}
