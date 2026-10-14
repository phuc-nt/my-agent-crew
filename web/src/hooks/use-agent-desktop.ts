// One agent's desktop as the server tells of it now, and the picture a person may try.
//
// The state is read when the card opens, after a save that changes the agent's desktop keys,
// and after each try; never on a timer. Each read sends the helper one state request, and
// nothing changes on the page while nobody looks at the screen it describes.
//
// A try may take a while: the helper has ten seconds a request, three requests for an agent
// with applications. The page gives up after a little more than that, whether or not the
// request itself stops, and an answer arriving after it is not drawn.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { AgentDesktop, ComputerMode, DesktopShot } from "../api/types";
import { vi } from "../i18n/vi";
import { errorText } from "../lib/error-text";

export const DESKTOP_SHOT_WAIT_MS = 35_000;

export interface AgentDesktopController {
  /** The last answer. Null until the first, and for good from a server without the route. */
  desktop: AgentDesktop | null;
  /** The route answered 404: a server older than it, or an agent the crew no longer has. */
  missing: boolean;
  /** Why the state could not be read, as the card says it. */
  readError: string | null;
  shooting: boolean;
  /** The picture the last try took. */
  shot: DesktopShot | null;
  /** Why the last try took none: the server's own sentence for a 409, shown as it is. */
  refused: string | null;
  tryShot: () => void;
}

/** What a try that failed has to say. A 409 is the server's sentence for why there is no
 *  picture; anything else is a request that failed. */
function refusal(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return error.message;
  return vi.connectionsPage.failed(errorText(error));
}

/**
 * `savedMode` and `savedApps` are the agent's desktop keys as its file has them; without a
 * mode, from a server older than the desktop, nothing is read.
 */
export function useAgentDesktop(
  agentId: string,
  savedMode: ComputerMode | undefined,
  savedApps: string[] | undefined,
): AgentDesktopController {
  const [desktop, setDesktop] = useState<AgentDesktop | null>(null);
  const [missing, setMissing] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [shooting, setShooting] = useState(false);
  const [shot, setShot] = useState<DesktopShot | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  // Answers can cross on the wire. Each read takes a number, and one asked no later than
  // what is on screen never replaces it.
  const asked = useRef(0);
  const shown = useRef(0);
  // Each try takes a number too: one given up on, or left behind by the card, draws nothing.
  const attempt = useRef(0);
  const inFlight = useRef<{ control: AbortController; timer: ReturnType<typeof setTimeout> } | null>(null);
  const appsKey = savedApps?.join("\n");

  const read = useCallback(async () => {
    const mine = ++asked.current;
    try {
      const answer = await api.agentDesktop(agentId);
      if (mine <= shown.current) return;
      shown.current = mine;
      setDesktop(answer);
      setReadError(null);
    } catch (e) {
      if (mine <= shown.current) return;
      shown.current = mine;
      if (e instanceof ApiError && e.status === 404) setMissing(true);
      else setReadError(errorText(e));
    }
  }, [agentId]);

  useEffect(() => {
    if (savedMode !== undefined) void read();
  }, [read, savedMode, appsKey]);

  useEffect(
    () => () => {
      attempt.current += 1;
      if (inFlight.current) {
        clearTimeout(inFlight.current.timer);
        inFlight.current.control.abort();
      }
    },
    [],
  );

  const tryShot = useCallback(async () => {
    const mine = ++attempt.current;
    const control = new AbortController();
    const done = (outcome: () => void) => {
      if (attempt.current !== mine) return;
      attempt.current += 1;
      clearTimeout(timer);
      inFlight.current = null;
      outcome();
      setShooting(false);
      // Whatever the outcome, the machine may have changed since it was read.
      void read();
    };
    const timer = setTimeout(() => {
      control.abort();
      done(() => setRefused(vi.desktop.card.gaveUp));
    }, DESKTOP_SHOT_WAIT_MS);
    inFlight.current = { control, timer };
    setShooting(true);
    setShot(null);
    setRefused(null);
    try {
      const answer = await api.tryDesktopScreenshot(agentId, control.signal);
      done(() => setShot(answer));
    } catch (e) {
      done(() => setRefused(refusal(e)));
    }
  }, [agentId, read]);

  return {
    desktop: missing ? null : desktop,
    missing,
    readError: missing ? null : readError,
    shooting,
    shot,
    refused,
    tryShot: () => void tryShot(),
  };
}
