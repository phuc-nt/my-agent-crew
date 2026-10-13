// One agent's browser as it runs now, and what a person can do to it at once: stop it, close
// a tab, and open or close the window they sign in through.
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

/** What is in flight: stopping the browser, opening the sign-in window ("login"), closing it
 *  ("done"), the id of the tab being closed, or null. */
export type BrowserPending = "stop" | "login" | "done" | number | null;

export interface AgentBrowserController {
  /** The last answer. Null until the first, and for good from a server without the route. */
  browser: AgentBrowser | null;
  pending: BrowserPending;
  /** What the last action has to say, else why the state could not be read again. */
  note: BrowserNote | null;
  stop: () => void;
  closeTab: (tabId: number) => void;
  /** Opens the sign-in window, on `url` when one is given. True once the server opened it. */
  openLogin: (url: string) => Promise<boolean>;
  closeLogin: () => void;
}

/**
 * What an action that failed has to say. Two refusals are no failure of the request, and the
 * server words each in a sentence of its own, shown as it is: a tab that is gone already
 * (404), and a sign-in window that cannot open now or on that address (409, 422).
 */
function refusal(what: BrowserPending, error: unknown): BrowserNote {
  const status = error instanceof ApiError ? error.status : 0;
  const worded = typeof what === "number" ? status === 404 : what === "login" && (status === 409 || status === 422);
  if (worded) return { tone: "warn", text: errorText(error) };
  return { tone: "danger", text: vi.connectionsPage.failed(errorText(error)) };
}

/**
 * `savedMode` is the agent's `browser` key as its file has it. A save that changes it is
 * read at once: set to off, the server stops the browser there and then.
 */
export function useAgentBrowser(agentId: string, savedMode: BrowserMode | undefined): AgentBrowserController {
  const [browser, setBrowser] = useState<AgentBrowser | null>(null);
  // The route answered 404: a server older than it, or an agent the crew no longer has.
  const [missing, setMissing] = useState(false);
  const [pending, setPending] = useState<BrowserPending>(null);
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
    async (what: BrowserPending, work: () => Promise<unknown>): Promise<boolean> => {
      setPending(what);
      setActed(null);
      let done = true;
      try {
        await work();
      } catch (e) {
        done = false;
        setActed(refusal(what, e));
      }
      // Whatever was asked before the action ended describes the browser before it.
      shown.current = asked.current;
      await read();
      setPending(null);
      return done;
    },
    [read],
  );

  const stop = useCallback(() => void act("stop", () => api.stopAgentBrowser(agentId)), [act, agentId]);
  const closeTab = useCallback(
    (tabId: number) => void act(tabId, () => api.closeAgentBrowserTab(agentId, tabId)),
    [act, agentId],
  );
  const openLogin = useCallback((url: string) => act("login", () => api.openAgentBrowserLogin(agentId, url)), [act, agentId]);
  const closeLogin = useCallback(() => void act("done", () => api.closeAgentBrowserLogin(agentId)), [act, agentId]);

  const note = acted ?? (readError === null ? null : { tone: "danger" as const, text: vi.browser.card.readFailed(readError) });
  const state = { browser: missing ? null : browser, pending, note: missing ? null : note };
  return { ...state, stop, closeTab, openLogin, closeLogin };
}
