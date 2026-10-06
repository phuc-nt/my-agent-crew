// The MCP servers of `config.yaml` and what the owner can do with one: try it again, sign
// in, sign out.
//
// The list is read once and again after each action. A server that is being tried reads
// as `idle`, and nobody tells the page when the try ends, so the list is read again every
// couple of seconds until it has: a card must not sit on "connecting" for a server that
// came up a moment later. A key that changed makes the crew try the servers that are down
// on its own time, so those are watched the same way for a short while. Each row also names
// the agents that use the server, which no try changes: the page says when the crew did.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { McpServerInfo } from "../api/types";
import { errorText } from "../lib/error-text";

export const POLL_MS = 2_000;
/** Reads a server that is being tried is worth: past the longest a try takes. */
export const TRY_POLLS = 20;
/** Reads a server that is down is worth after a key changed. */
export const KEY_POLLS = 5;

export interface McpController {
  servers: McpServerInfo[];
  /** Why the list could not be read; null once it has been. */
  error: string | null;
  refresh: () => Promise<void>;
  /** A key was saved or removed: read the list, and watch the servers that are down. */
  keysChanged: () => Promise<void>;
  /** An agent was written, made or removed: read the list, which says who uses each server.
   *  No server is tried for it, so what is being watched stays as it is. */
  crewChanged: () => Promise<void>;
  /** Rejects with the request's error, which the card puts in words. */
  reconnect: (name: string) => Promise<void>;
  /** Sends the person to the address the server answers. Rejects when it refuses to. */
  signIn: (name: string) => Promise<void>;
  signOut: (name: string) => Promise<void>;
}

type Watch = { left: number; down: boolean };

/** What the servers hand out, as one value: it changes when a tool comes, goes or reads
 *  another way. A server with no tools adds nothing to it, so a list that holds none reads
 *  like no list at all. It is one half of what makes the list of every tool stale, and
 *  says nothing of a try that ended with no tool: `standing` is the whole of it. */
export const handedOut = (servers: McpServerInfo[]): string =>
  JSON.stringify(servers.flatMap((server) => server.tools));

/** Where the servers stand, as one value: what they hand out, and how the last try of each
 *  ended. It changes when either does, which is when the list of every tool has gone stale.
 *  The tools alone do not tell: a server is listed with none for as long as it is tried,
 *  while the agents keep the ones it had, and with none still when the try fails and they
 *  lose them. A server that is being tried adds nothing of its own, so a list read before
 *  any try has ended reads like no list at all. */
export const standing = (servers: McpServerInfo[]): string =>
  JSON.stringify([
    handedOut(servers),
    servers.filter((server) => server.status !== "idle").map((server) => [server.name, server.status]),
  ]);

const leavePage = (url: string) => window.location.assign(url);

export function useMcpServers(leave: (url: string) => void = leavePage): McpController {
  const [servers, setServers] = useState<McpServerInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [watch, setWatch] = useState<Watch>({ left: TRY_POLLS, down: false });
  // Answers can cross on the wire: only the request made last says what the list is.
  const latest = useRef(0);

  const take = useCallback(async (ask: () => Promise<{ servers: McpServerInfo[] }>) => {
    const mine = ++latest.current;
    const answer = await ask();
    if (mine !== latest.current) return;
    setServers(answer.servers);
    setError(null);
  }, []);

  const read = useCallback(async () => {
    try {
      await take(api.mcpServers);
    } catch (e) {
      setError(errorText(e));
    }
  }, [take]);

  const refresh = useCallback(async () => {
    setWatch({ left: TRY_POLLS, down: false });
    await read();
  }, [read]);

  const keysChanged = useCallback(async () => {
    setWatch({ left: KEY_POLLS, down: true });
    await read();
  }, [read]);

  useEffect(() => {
    void read();
  }, [read]);

  const unsettled = servers.some((s) => s.status === "idle" || (watch.down && s.status === "failed"));
  useEffect(() => {
    if (!unsettled || watch.left <= 0) return;
    const timer = window.setTimeout(() => {
      setWatch((w) => ({ ...w, left: w.left - 1 }));
      void read();
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [unsettled, watch, read]);

  // A request that changes one server answers the whole list as it left it, and another
  // server may still be being tried there: the watch starts over.
  const change = useCallback(
    async (ask: () => Promise<{ servers: McpServerInfo[] }>) => {
      setWatch({ left: TRY_POLLS, down: false });
      await take(ask);
    },
    [take],
  );

  const reconnect = useCallback((name: string) => change(() => api.mcpReconnect(name)), [change]);

  const signIn = useCallback(
    async (name: string) => {
      const { authorize_url } = await api.mcpSignIn(name);
      leave(authorize_url);
    },
    [leave],
  );

  const signOut = useCallback((name: string) => change(() => api.mcpSignOut(name)), [change]);

  return { servers, error, refresh, keysChanged, crewChanged: read, reconnect, signIn, signOut };
}
