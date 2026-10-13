// An agent's browser card drawn against a server of its own, and the ways the tests of its
// sign-in window and of its signed-in hosts read it, hold its answers and turn its clock.
import { act, render, screen } from "@testing-library/react";
import { vi as vitest } from "vitest";
import type { AgentInfo } from "../api/types";
import { BrowserCard } from "../components/agent-editor/browser-card";
import { vi } from "../i18n/vi";
import { FakeBackend, coachAgent, fakeAgent } from "./fake-backend";
import { type BrowserMachine, browserMachine } from "./fake-browser";

export const READ = "/agents/coach/browser";
export const OPEN = `${READ}/login`;
export const DONE = `${READ}/login/done`;
/** Where the server's clock stands until a test turns it: nine in the morning in Hanoi. */
export const NINE = new Date("2026-10-14T02:00:00Z");
/** The server's clock, this many minutes and seconds on. */
export const later = (minutes: number, seconds = 0) => new Date(NINE.getTime() + (minutes * 60 + seconds) * 1000);

let backend: FakeBackend;

/** A crew whose coach acts on pages unless `coach` says otherwise, on a machine that has a
 *  browser unless `machine` does, with a screen a window can be shown on. */
export function crew(coach: Partial<AgentInfo> = {}, machine: Partial<BrowserMachine> = {}): FakeBackend {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, { ...coachAgent, browser: "act", ...coach }];
  backend.browser.machine = browserMachine({ enabled: true, ...machine });
  backend.browser.login.now = () => NINE;
  vitest.stubGlobal("fetch", backend.fetch);
  return backend;
}

/** The card as the coach's page draws it: the level and the hosts are what its file says,
 *  unless a test hands the card hosts of its own. */
export function show(given: { savedHosts?: string[] } = {}) {
  const coach = backend.agents.find((a) => a.id === "coach");
  const hosts = "savedHosts" in given ? given.savedHosts : coach?.browser_hosts;
  return render(<BrowserCard agentId="coach" savedMode={coach?.browser} savedHosts={hosts} />);
}

/** Each request the card made, as its method and path. */
export const sent = () => backend.requests.map((r) => `${r.method} ${r.path}`);
/** What each request to `path` carried. */
export const carried = (path: string) => backend.requests.filter((r) => r.path === path).map((r) => r.body);
/** Lets every answer on its way land, and what it draws be drawn. */
export const settle = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));

export const state = () => screen.getByTestId("browser-state");
export const note = () => screen.getByTestId("browser-note");
export const field = () => screen.getByRole("textbox", { name: vi.browser.login.address });
export const openButton = () => screen.getByRole("button", { name: vi.browser.login.start });
export const doneButton = () => screen.getByRole("button", { name: vi.browser.login.done });
/** What every button on the page reads, top to bottom. */
export const buttons = () => screen.queryAllByRole("button").map((button) => button.textContent);
/** Whether something is in a region that is said aloud when it changes. */
export const saidAloud = (element: Element) => element.closest("[role='status'], [role='alert'], [aria-live]") !== null;

/** Only the page's own clock is the test's to turn; the waits of the test itself stay real. */
export const clock = () => vitest.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
export async function pass(ms: number) {
  act(() => {
    vitest.advanceTimersByTime(ms);
  });
  await settle();
}

/** Answers that can be kept on the wire: each is made up as the server stood when it was
 *  asked, and lands when the test says, the oldest first. */
export function wire() {
  const held: { method: string; land: () => void }[] = [];
  let holding = false;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const answer = await backend.fetch(input, init);
    if (holding) await new Promise<void>((land) => held.push({ method: init.method ?? "GET", land }));
    return answer;
  });
  return {
    hold: () => {
      holding = true;
    },
    waiting: () => held.map((one) => one.method),
    land: async () => {
      held.shift()?.land();
      await settle();
    },
  };
}
