import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

/** Vite names the built entry chunk after index.html, with its content hash in the name. */
const ENTRY = /\/assets\/index-[\w-]+\.js$/;
// Focus comes and goes all day; one look every half minute still catches a restart.
const THROTTLE_MS = 30_000;

/** The hashed entry script `doc` loads, or null where there is none: the dev server
 *  serves source modules, which change under the page without a new build. */
export function entryScript(doc: Document): string | null {
  for (const script of doc.querySelectorAll("script[type=module][src]")) {
    const src = script.getAttribute("src") ?? "";
    if (ENTRY.test(src)) return src;
  }
  return null;
}

export interface VersionCheck {
  /** The server now serves another build than the one this page runs. */
  stale: boolean;
  /** The version of the build on screen: the server's, from a look that found it serving
   *  this very build. Null until such a look — never the version of another build. */
  pageVersion: string | null;
  /** The server's version at the last look; null when that look failed. */
  serverVersion: string | null;
  /** Looks now, however recently the last look was. */
  check: () => void;
  /** Puts the offer away until a later look finds the other build still served. */
  dismiss: () => void;
}

async function servedEntry(): Promise<string | null> {
  const response = await fetch("/", { cache: "no-store" });
  if (!response.ok) throw new Error(String(response.status));
  return entryScript(new DOMParser().parseFromString(await response.text(), "text/html"));
}

/**
 * Notices when the server was restarted on a newer build than this page runs.
 *
 * An installed app on a phone can stay open for days, calling an API that has moved on
 * under it. The build is told by the hashed entry script, not the version number: the
 * server is often restarted from a working tree whose version was not bumped, and a bump
 * alone changes nothing a reload would bring. Looks on focus, when the tab comes back
 * into view and when the live stream reconnects — a dropped stream is what a restart
 * looks like from here. A look that fails says nothing: a server that is down is not a
 * new build.
 */
export function useVersionCheck(connected: boolean): VersionCheck {
  const [entry] = useState(() => entryScript(document));
  const [pageVersion, setPageVersion] = useState<string | null>(null);
  const [serverVersion, setServerVersion] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const lastLook = useRef(0);

  const check = useCallback(() => {
    lastLook.current = Date.now();
    const version = api.health().then(
      (health) => health.version,
      () => null,
    );
    void version.then(setServerVersion);
    if (!entry) {
      // The dev server has no build to tell apart, so the first version it gives will do.
      void version.then((v) => v && setPageVersion((page) => page ?? v));
      return;
    }
    const served = servedEntry().catch(() => null);
    void Promise.all([version, served]).then(([v, s]) => {
      if (!s) return;
      setStale(s !== entry);
      // A version names the build on screen only when this same look found the server
      // serving it: a page loaded before a restart, or while the server was down, would
      // otherwise take the name of a build it is not running.
      if (s === entry && v) setPageVersion(v);
    });
  }, [entry]);

  useEffect(() => check(), [check]);

  useEffect(() => {
    if (!entry) return;
    const look = () => {
      if (document.visibilityState === "hidden") return;
      if (Date.now() - lastLook.current >= THROTTLE_MS) check();
    };
    window.addEventListener("focus", look);
    document.addEventListener("visibilitychange", look);
    return () => {
      window.removeEventListener("focus", look);
      document.removeEventListener("visibilitychange", look);
    };
  }, [entry, check]);

  // The first connection is the page loading; only a later one follows a drop.
  const wasConnected = useRef(false);
  useEffect(() => {
    if (!connected) return;
    if (wasConnected.current && entry) check();
    wasConnected.current = true;
  }, [connected, entry, check]);

  const dismiss = useCallback(() => setStale(false), []);

  return { stale, pageVersion, serverVersion, check, dismiss };
}
