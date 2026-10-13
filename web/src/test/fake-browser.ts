// The browser routes and keys as both fakes answer them, so a screen is tested against one
// set of rules.
//
// It mirrors `server/routes_browser.py`, `server/browser_runtime.py` and `browser/kit.py`:
// the machine's status names whose browser is up in id order, an agent's tabs come last
// used first, a browser that is not up has no tab and no idle time, stopping one says
// whether there was one to stop and closes the window a person has open on its profile, a
// tab that is gone is a 404 in the server's own words, an agent the crew does not have is a
// 404, a save that leaves `browser: off` stops the agent's browser there and then, and a
// browser tool is held only where the machine has a browser to start and the agent's own
// file asks for one. The window a person signs in through is in `fake-browser-login.ts`.
import type { AgentBrowser, BrowserConnection, BrowserMode, BrowserTab, RegistryTool } from "../api/types";
import { FakeBrowserLogin, type LoginAgent } from "./fake-browser-login";

export type BrowserReply = { status: number; body: unknown };

type Refusal = { status: number; detail: string };

/** `texts_browser_web.TAB_UNKNOWN`, word for word. */
export const TAB_UNKNOWN = "Không còn tab này trong trình duyệt của agent.";

/** What `browser: read` brings, in the order `browser/kit.py` names them. */
export const BROWSER_READ_TOOLS = [
  "browser_navigate",
  "browser_snapshot",
  "browser_text",
  "browser_tabs",
  "browser_screenshot",
  "browser_pdf",
];
/** What `browser: act` adds. */
export const BROWSER_ACT_TOOLS = ["browser_act", "browser_download"];
/** The three that go through the gate: one opens an address, the others touch the page. */
const ASKS_FIRST = ["browser_navigate", ...BROWSER_ACT_TOOLS];
/** The two that came with the window a person signs in through. */
const WITH_LOGIN = ["browser_pdf", "browser_download"];

/** What the machine has, without whose browser is up: that is read off the browsers running. */
export type BrowserMachine = Omit<BrowserConnection, "running">;

/** What the fake reads of an agent: the `browser` and `browser_hosts` keys of its file. */
export type BrowserCrewMember = { id: string; browser?: BrowserMode; browser_hosts?: string[] };

/** A machine with the crew's own Chromium installed and the browser left off, which is what
 *  a `config.yaml` that says nothing about it reads as. */
export function browserMachine(overrides: Partial<BrowserMachine> = {}): BrowserMachine {
  return { enabled: false, channel: "chromium", installed: true, version: "141.0.7390.37", missing: "", install_command: "", ...overrides };
}

/** One open tab of a conversation, idle for a few seconds. */
export function browserTab(overrides: Partial<BrowserTab> = {}): BrowserTab {
  return { id: 1, label: "main", conversation_id: "c1", host: "shop.example", title: "Cửa hàng", idle_seconds: 17, busy: false, ...overrides };
}

interface Session {
  busy: boolean;
  idleSeconds: number;
  tabs: BrowserTab[];
}

const ROUTES = { read: "GET", stop: "POST", close: "DELETE", login: "POST", done: "POST" } as const;
const NAMED: Record<string, keyof typeof ROUTES> = { stop: "stop", login: "login", "login/done": "done" };

export class FakeBrowser {
  /** Answer as the server did before it had a browser: no key in `/connections`, no tool
   *  row, and no route here. */
  old = false;
  machine: BrowserMachine = browserMachine();
  /** The crew, each agent with the browser keys of its file. Each fake points it at its own. */
  crew: () => BrowserCrewMember[] = () => [];
  /** What a kind of request is refused with, for as long as a test leaves it set. */
  refuse: Partial<Record<keyof typeof ROUTES, Refusal>> = {};
  /** The windows people sign in through, and what each profile holds. */
  login = new FakeBrowserLogin();
  /** The browsers that are up, by agent. */
  private sessions = new Map<string, Session>();

  /** An agent's browser comes up with these tabs, as its first call starts it. */
  start(agentId: string, tabs: BrowserTab[] = [], state: { busy?: boolean; idleSeconds?: number } = {}): this {
    this.sessions.set(agentId, { busy: state.busy ?? false, idleSeconds: state.idleSeconds ?? 0, tabs: [...tabs] });
    return this;
  }

  running(agentId: string): boolean {
    return this.sessions.has(agentId);
  }

  /** The ids of the tabs an agent's browser has open now, in the order they were opened. */
  tabIds(agentId: string): number[] {
    return (this.sessions.get(agentId)?.tabs ?? []).map((tab) => tab.id);
  }

  /** The `browser` key of GET /connections; nothing from a server older than it. */
  status(): BrowserConnection | undefined {
    if (this.old) return undefined;
    const running = this.crew().map((agent) => agent.id).filter((id) => this.sessions.has(id)).sort();
    return { ...this.machine, running };
  }

  /** What a save of an agent leaves: one whose file now says off has its browser stopped. */
  saved(agentId: string, mode: BrowserMode | undefined): void {
    if ((mode ?? "off") === "off") this.stop(agentId);
  }

  /** The rows GET /tools adds to the crew's own. No list of an agent's gives these: each is
   *  held by the agents whose file asks for a browser, on a machine that has one to start. */
  registryTools(): RegistryTool[] {
    if (this.old || !this.machine.enabled || !this.machine.installed) return [];
    const crew = this.crew();
    const holders = (name: string) =>
      crew.filter((a) => a.browser === "act" || (a.browser === "read" && !BROWSER_ACT_TOOLS.includes(name))).map((a) => a.id).sort();
    return [...BROWSER_READ_TOOLS, ...BROWSER_ACT_TOOLS]
      .filter((name) => !this.login.old || !WITH_LOGIN.includes(name))
      .map((name) => ({
        name,
        description: "",
        requires_approval: ASKS_FIRST.includes(name),
        agents: holders(name),
        optional: false,
        with_browser: true,
      }))
      .filter((row) => row.agents.length > 0)
      .sort((a, b) => (a.name < b.name ? -1 : 1));
  }

  /** Answers one of the five routes, or nothing for a path that is not the browser's. */
  route(path: string, method: string, body?: unknown): BrowserReply | null {
    const match = path.match(/^\/agents\/([^/]+)\/browser(?:\/(stop|login|login\/done)|\/tabs\/([^/]+))?$/);
    if (!match) return null;
    const agentId = decodeURIComponent(match[1]);
    const what = match[2] ? NAMED[match[2]] : match[3] === undefined ? "read" : "close";
    const signsIn = what === "login" || what === "done";
    if (this.old || (signsIn && this.login.old)) return { status: 404, body: { detail: "Not Found" } };
    if (method !== ROUTES[what]) return { status: 405, body: { detail: "Method Not Allowed" } };
    // The tab's id is read as a number before the route's own code runs.
    if (what === "close" && !/^-?\d+$/.test(match[3])) {
      return { status: 422, body: { detail: [{ type: "int_parsing", loc: ["path", "tab_id"] }] } };
    }
    const refused = this.refuse[what];
    if (refused) return { status: refused.status, body: { detail: refused.detail } };
    const agent = this.crew().find((a) => a.id === agentId);
    if (!agent) return { status: 404, body: { detail: `unknown agent ${agentId}` } };
    const session = this.sessions.get(agentId);
    if (what === "read") return { status: 200, body: this.told(agent, session) };
    if (what === "stop") return { status: 200, body: { stopped: this.stop(agentId) } };
    if (what === "login") return this.login.open(this.member(agent), body, () => this.stop(agentId));
    if (what === "done") return this.login.done(this.member(agent));

    const tabId = Number(match[3]);
    if (!session || !session.tabs.some((tab) => tab.id === tabId)) return { status: 404, body: { detail: TAB_UNKNOWN } };
    session.tabs = session.tabs.filter((tab) => tab.id !== tabId);
    return { status: 200, body: { closed: tabId } };
  }

  /** Stops the agent's browser and closes the window open on its profile. Whether there was
   *  either to stop. A browser that goes down leaves what it held written beside its profile. */
  private stop(agentId: string): boolean {
    const closed = this.login.close(agentId);
    const stopped = this.sessions.delete(agentId);
    if (stopped) this.login.closed(agentId);
    return closed || stopped;
  }

  /** An agent as the windows are told of it. It has a browser where the machine has one to
   *  start and its own file asks for one. */
  private member(agent: BrowserCrewMember): LoginAgent {
    const session = this.sessions.get(agent.id);
    const reads = this.machine.enabled && this.machine.installed && (agent.browser ?? "off") !== "off";
    return { id: agent.id, hosts: agent.browser_hosts ?? [], reads, up: session !== undefined, busy: session?.busy ?? false };
  }

  private told(agent: BrowserCrewMember, session: Session | undefined): AgentBrowser {
    // Last used first, and of two used at the same moment the one opened later.
    const tabs = [...(session?.tabs ?? [])].sort((a, b) => a.idle_seconds - b.idle_seconds || b.id - a.id);
    return {
      mode: agent.browser ?? "off",
      enabled: this.machine.enabled,
      installed: this.machine.installed,
      running: session !== undefined,
      busy: session?.busy ?? false,
      idle_seconds: session ? session.idleSeconds : null,
      tabs,
      ...this.login.told(this.member(agent)),
    };
  }
}
