// Where the app is, kept in the URL hash so Back and Forward work and a screen can be
// linked to. A hash needs no server rewrite rule, which matters because the SPA is served
// as a static bundle from the same process as the API.
import { useCallback, useEffect, useState } from "react";

export const MANAGE_SECTIONS = [
  "activity",
  "approvals",
  "crew",
  "tools",
  "jobs",
  "memory",
  "costs",
  "connections",
  "settings",
] as const;

export type ManageSection = (typeof MANAGE_SECTIONS)[number];

export type Route =
  | { kind: "chat"; conversationId: string | null }
  | {
      kind: "manage";
      section: ManageSection;
      /**
       * The one thing the section is opened on, when there is one: an agent under `crew`,
       * a run under `activity`. It rides in the URL rather than in component state so the
       * view can be linked to, survives a reload, and leaves Back meaning "the list I came
       * from". Which section it belongs to says how to read it.
       */
      param?: string;
    };

const DEFAULT_SECTION: ManageSection = "activity";

function isSection(value: string): value is ManageSection {
  return (MANAGE_SECTIONS as readonly string[]).includes(value);
}

/**
 * Read a route out of a hash.
 *
 * Anything unrecognised falls back to the chat with no conversation chosen, so a stale or
 * hand-edited link lands somewhere usable instead of on a blank screen.
 */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "manage") {
    const section = parts[1] ?? "";
    // A third segment names what the section is opened on. An unknown section drops it
    // too: landing on the default section with someone else's id still attached would
    // open something the person did not ask for.
    if (!isSection(section)) return { kind: "manage", section: DEFAULT_SECTION };
    const param = parts[2] ? decodeURIComponent(parts[2]) : undefined;
    return param ? { kind: "manage", section, param } : { kind: "manage", section };
  }
  if (parts[0] === "chat") return { kind: "chat", conversationId: parts[1] ?? null };
  return { kind: "chat", conversationId: null };
}

/** The hash a route is written as; the inverse of `parseRoute`. */
export function routeHash(route: Route): string {
  if (route.kind === "manage") {
    const tail = route.param ? `/${encodeURIComponent(route.param)}` : "";
    return `#/manage/${route.section}${tail}`;
  }
  return route.conversationId ? `#/chat/${route.conversationId}` : "#/chat";
}

export interface RouteController {
  route: Route;
  /** Pushes a history entry, so Back returns to where the person was. */
  navigate: (route: Route) => void;
  /** Rewrites the current entry — for reflecting state the person did not navigate to. */
  replace: (route: Route) => void;
}

export function useRoute(): RouteController {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: Route) => {
    // The state is set here rather than left to the `hashchange` listener: the browser
    // fires that event asynchronously, so waiting for it would leave the screen showing
    // the old route for a frame. The listener still handles Back and Forward, and setting
    // the same route twice is a no-op.
    window.location.hash = routeHash(next);
    setRoute(next);
  }, []);

  const replace = useCallback((next: Route) => {
    const url = `${window.location.pathname}${window.location.search}${routeHash(next)}`;
    window.history.replaceState(null, "", url);
    setRoute(next);
  }, []);

  return { route, navigate, replace };
}
