import type { ToolInfo } from "./agents";

/** One tool in the crew's registry, with the agents whose toolbox actually holds it. */
export interface RegistryTool extends ToolInfo {
  agents: string[];
  /** Needs an API key: absent without one, even for an agent that names it. */
  optional: boolean;
  /** Only on a tool of an MCP server: the server's name, and how far the tool is let in. */
  server?: string;
  exposure?: McpExposure;
  /** Only on `tool_search`: an agent holds it while it has MCP tools that are not declared
   * up front, whatever its allow-list and mode say. */
  with_mcp?: boolean;
  /** Only on `tool_script`: an agent holds it while it has a tool a script may call, one of
   * its own that only reads or an MCP tool listed as read-only and not hidden, whatever
   * its allow-list and mode say. */
  with_reads?: boolean;
  /** Only on the eight `browser_*` tools: the agent's `browser` key alone brings them,
   * whatever its allow-list and mode say. */
  with_browser?: boolean;
}

/**
 * How far a server's tool is let in. `direct` is declared to the model every turn;
 * `deferred` and `codemode` are held back until the agent asks for them, and a `codemode`
 * tool the owner listed as read-only is named in the description of the script tool; any
 * read-only tool can be called from a script, however far it is let in, except `hidden`,
 * which is handed to nobody. Must match the exposures in the backend's `mcp/config.py`.
 */
export type McpExposure = "direct" | "deferred" | "codemode" | "hidden";

/** Never tried or being tried, working, waiting for the owner to sign in, and tried
 * without success. Must match the statuses in the backend's `mcp/hub.py`. */
export type McpStatus = "idle" | "connected" | "signed_out" | "failed";

export interface McpToolInfo {
  /** The name an agent calls it by: `mcp__<server>__<tool>`. */
  name: string;
  /** The name the server knows it by. */
  remote: string;
  description: string;
  exposure: McpExposure;
  requires_approval: boolean;
  /** What the server says of its own tool. Shown, never what decides the approval. */
  read_only_hint: boolean;
  /** Set when the tool's parameter schema was folded before the model was told of it: the
   * schema's length in characters as the server sent it and as the model reads it. Null
   * for a schema passed on whole; an older server leaves the key out, which reads the same. */
  folded?: { from: number; to: number } | null;
}

/** One MCP server of `config.yaml` as GET /api/mcp reports it. No header value and no
 * token is among it. */
export interface McpServerInfo {
  name: string;
  url: string;
  description: string;
  status: McpStatus;
  /** Why it is not connected, or what the last sign-in ended in; "" when nothing is wrong. */
  error: string;
  exposure: McpExposure;
  /** A sign-in is kept for it. */
  signed_in: boolean;
  /** The file gives it an Authorization header, so it never signs in. */
  uses_key: boolean;
  /** The environment variables its headers are read from. */
  env: string[];
  agents: string[];
  /** Tools left out because another took the name they come to. */
  skipped: string[];
  tools: McpToolInfo[];
}
