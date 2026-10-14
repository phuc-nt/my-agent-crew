// An agent's browser as the server reports it. Mirrors `server/routes_browser.py`,
// `server/routes_browser_login.py` and the `browser` keys of `agents/profile.py`.

/** What an agent's file says of the browser: none, pages to read, or pages to act on too. */
export type BrowserMode = "off" | "read" | "act";

/** The machine's browser, as `GET /connections` reports it under `browser`. */
export interface BrowserConnection {
  /** `browser_enabled` of the machine's config.yaml. No page sets it. */
  enabled: boolean;
  /** `chromium` is the one the crew installs, `chrome` the machine's own. */
  channel: "chromium" | "chrome";
  installed: boolean;
  /** "" when the server could not read one. */
  version: string;
  /** What keeps a browser from starting: the Python package, the browser itself, or nothing. */
  missing: "" | "playwright" | "browser";
  /** The command that installs what is missing; "" when nothing is, or when it is the
   * machine's own Chrome, which its owner installs. */
  install_command: string;
  /** The ids of the agents whose browser is up now, sorted. */
  running: string[];
}

/** One tab of an agent's browser. The whole address is never sent, only its host. */
export interface BrowserTab {
  /** Stable while the tab lives. */
  id: number;
  /** The name the agent gave the tab. */
  label: string;
  /** Null for a tab a scheduled run opened. */
  conversation_id: string | null;
  /** "" for a blank tab. */
  host: string;
  /** "" when the page has none. */
  title: string;
  idle_seconds: number;
  /** True while a call of the agent uses the tab. */
  busy: boolean;
}

/** The window a person signs in through on the agent's own profile. It shows on the screen
 * of the machine the crew runs on, and the agent has no browser while it is open. */
export interface BrowserLogin {
  open: boolean;
  /** When an open window closes by itself, UTC; null when none is open. */
  until: string | null;
  /** One could be opened now. False while one is open. */
  available: boolean;
  /** What is in the way when it is neither open nor available: "off" (the agent has no
   * browser), "no_console", "locked", "busy", or a value a later server adds. "" otherwise. */
  why: string;
}

/** A host the agent's browser may still be signed in to. A sign read off its cookies, not
 * proof; of a cookie only this name and this moment are ever sent. */
export interface BrowserSignedIn {
  /** A host name, or a pattern of the agent's own list such as `*.shop.example`. */
  host: string;
  /** When the last cookie that counts runs out, UTC; null for a host of the agent's own
   * list that holds nothing. */
  until: string | null;
}

/** `GET /agents/{id}/browser`: the agent's key, the machine's two facts, and what runs. */
export interface AgentBrowser {
  mode: BrowserMode;
  enabled: boolean;
  installed: boolean;
  running: boolean;
  busy: boolean;
  /** Null while nothing runs. */
  idle_seconds: number | null;
  /** Last used first; empty while nothing runs. */
  tabs: BrowserTab[];
  /** Absent from a server older than the window. */
  login?: BrowserLogin;
  /** Null where there is nothing to tell: the agent has no browser, or none has ever closed
   * on its profile and none is up. Absent from a server older than the key. */
  logins?: BrowserSignedIn[] | null;
  /** How many more hosts hold a sign-in than `logins` names: an agent with no hosts of its
   * own is told of the first few by name. Absent from a server older than the key. */
  logins_more?: number;
}
