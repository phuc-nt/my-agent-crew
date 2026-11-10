import type { AgentInfo } from "./agent-profile";
import type { RouteInfo, SkillInfo, ToolInfo } from "./agents";
import type { BrowserConnection } from "./browser";

/** An API key by the name of its environment variable. The value never leaves the server. */
export interface KeyStatus {
  name: string;
  present: boolean;
}

/** One agent's Telegram block. `configured` is that agent's own token variable. */
export interface TelegramConnection {
  agent_id: string;
  token_env: string;
  configured: boolean;
  /** Only the master's block opens a channel; anyone else's is read and skipped at boot. */
  ignored: boolean;
}

/** Everything the crew talks to on the outside, with no secret among it. */
export interface ConnectionsInfo {
  providers: { name: string; built: boolean }[];
  routes: RouteInfo[];
  /** Where `routes` come from: the MY_AGENT_ROUTES variable (read-only here), `routes`
   * in config.yaml, or the built-in default. The page saves to config.yaml. */
  routes_source: "env" | "config" | "default";
  vision_routes: RouteInfo[];
  audio_routes: RouteInfo[];
  keys: KeyStatus[];
  /** Search backends in priority order, best first. Never empty. */
  search_backends: string[];
  firecrawl_base_url: string;
  ollama_base_url?: string;
  telegram: TelegramConnection[];
  /** The machine's browser. Absent from a server older than the key: nothing is shown. */
  browser?: BrowserConnection;
}

/** Which card of the connections page an environment variable sits on. */
export type CredentialGroup = "model" | "search" | "telegram" | "mcp" | "other";

/**
 * One environment variable the connections page can set. A secret's value never comes
 * back from the server: only whether one is set and where from. A host address does.
 */
export interface CredentialInfo {
  name: string;
  group: CredentialGroup;
  secret: boolean;
  /** Must be an http(s) address. */
  url: boolean;
  present: boolean;
  /** "file": saved in the env file. "process": given to the server when it started, so
   * removing it from here is not possible and a restart may bring the old value back. */
  source: "file" | "process" | null;
  /** A free check can run now: there is a value, or a default to try. */
  checkable: boolean;
  /** The check spends from the key's own quota (a real search), so the button says so. */
  check_spends?: boolean;
  /** False for a name read from the file that the API will not write (lower-case or
   * reserved): it is shown, and edited in the file itself. */
  editable: boolean;
  /** Non-secrets only: the value in use and what applies when none is set. */
  value?: string;
  default?: string;
  /** Telegram only: the agents whose profile names this token. */
  agents?: string[];
  /** MCP only: the servers whose headers read this variable. */
  servers?: string[];
}

export interface CredentialsInfo {
  /** Where the values are kept, for the person who wants to look at it themselves. */
  file: string;
  items: CredentialInfo[];
  /** Saved, but the crew could not be rebuilt from it: why, and a restart will apply it. */
  restart_required: string | null;
}

export interface CredentialCheck {
  ok: boolean;
  detail: string;
}

export interface SettingsInfo {
  home: string;
  workspace_dir: string;
  users_dir: string;
  routes: RouteInfo[];
  providers: string[];
  language: string;
  /** IANA zone from config (`""` = machine zone) and the zone actually in use. */
  timezone: string;
  zone: string;
  cost_cap_usd: number;
  max_steps: number;
  autonomous_default: boolean;
  keys: { openrouter: boolean; brave: boolean; tavily: boolean };
  tools: ToolInfo[];
  skills: SkillInfo[];
  agents: AgentInfo[];
}
