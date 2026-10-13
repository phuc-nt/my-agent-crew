// An agent's browser as the server reports it. Mirrors `server/routes_browser.py` and the
// `browser` keys of `agents/profile.py`.

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
}
