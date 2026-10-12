import { render } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { ScriptStoreSection } from "../components/script-store-section";
import { coachAgent, fakeAgent, FakeBackend } from "./fake-backend";

/** How a sentence names the coach's one schedule, `brief`. */
export const BRIEF = 'lịch "Bản tin sáng"';

/** A crew of two answering `fetch`: the master, and the coach with its schedule `brief`,
 *  "Bản tin sáng". */
export function storeBackend(): FakeBackend {
  const backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  vitest.stubGlobal("fetch", backend.fetch);
  return backend;
}

/** The store screen for one agent, with the function it tells a chosen agent to. */
export function mountStore(backend: FakeBackend, agentId = "coach") {
  const onSelectAgent = vitest.fn();
  const screen = (id: string) => <ScriptStoreSection agents={backend.agents} agentId={id} onSelectAgent={onSelectAgent} />;
  const rendered = render(screen(agentId));
  return { onSelectAgent, show: (id: string) => rendered.rerender(screen(id)) };
}

/** Keeps every request whose "<METHOD> <address>" matches from reaching the backend until
 *  the function it returns is called: the time a slow server leaves a person to act in. */
export function holdRequests(backend: FakeBackend, matches: RegExp): () => void {
  let release = () => {};
  const open = new Promise<void>((resolve) => {
    release = resolve;
  });
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    if (matches.test(`${init.method ?? "GET"} ${String(input)}`)) await open;
    return backend.fetch(input, init);
  });
  return release;
}

/** Keeps each request whose "<METHOD> <address>" matches waiting on its own, holding the
 *  answer the backend gave at the moment it was asked. The list returned grows by one
 *  function per request, in the order they were asked; calling one lets that answer land. */
export function holdEach(backend: FakeBackend, matches: RegExp): Array<() => void> {
  const land: Array<() => void> = [];
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const answered = backend.fetch(input, init);
    if (matches.test(`${init.method ?? "GET"} ${String(input)}`)) await new Promise<void>((resolve) => land.push(resolve));
    return answered;
  });
  return land;
}

/** The requests made to the store's routes, as "<METHOD> <path and query>". */
export function storeRequests(backend: FakeBackend): string[] {
  return backend.requests.filter((asked) => asked.path.includes("/script-store")).map((asked) => `${asked.method} ${asked.path}`);
}

/** Takes rows out behind the screen's back, as a script or another tab would. */
export function takeOut(backend: FakeBackend, agentId: string, namespace: string, key?: string): void {
  const named = new URLSearchParams(key === undefined ? { namespace } : { namespace, key });
  backend.scriptStore.route(`/agents/${agentId}/script-store`, "DELETE", named);
}

/** The keys on screen, top to bottom. */
export const shownKeys = () => [...document.querySelectorAll(".script-store-key")].map((key) => key.textContent);

/** One namespace's card; null once the namespace has left the screen. */
export const namespaceCard = (namespace: string) => document.querySelector(`[data-namespace="${namespace}"]`) as HTMLElement;
