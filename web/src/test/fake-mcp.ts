// The MCP routes as both fakes answer them, so a screen is tested against one set of rules.
//
// It mirrors `server/routes_mcp.py`: the list never carries a header's value or a token, a
// name the file does not declare is a 404, a sign-in is refused with the server's own words
// when the page was not opened on the machine the crew runs on, and signing out leaves the
// server waiting for a sign-in with no tools.
import type { McpServerInfo, McpToolInfo, RegistryTool } from "../api/types";

export type McpReply = { status: number; body: unknown };

/** `texts_mcp.MCP_LOGIN_LOCAL_ONLY`, word for word. */
export const SIGN_IN_LOCAL_ONLY =
  "Chỉ đăng nhập được khi mở trang này trên chính máy đang chạy crew (địa chỉ localhost hoặc 127.0.0.1).";

/** `texts_mcp.MCP_AGENT_UNKNOWN_SERVER`: why an agent's edit is refused. */
export const unknownServer = (name: string) => `Không có máy chủ MCP tên ${name} trong config.yaml.`;

/** Where the fake sends a person to sign in. A spec answers this address itself. */
export const authorizeUrl = (name: string) => `https://auth.example.test/authorize?server=${encodeURIComponent(name)}`;

export function mcpTool(server: string, remote: string, overrides: Partial<McpToolInfo> = {}): McpToolInfo {
  return {
    name: `mcp__${server}__${remote.replace(/[^A-Za-z0-9_]/g, "_")}`,
    remote,
    description: "",
    exposure: "deferred",
    requires_approval: true,
    read_only_hint: false,
    ...overrides,
  };
}

export function mcpServer(overrides: Partial<McpServerInfo> = {}): McpServerInfo {
  return {
    name: "notion",
    url: "https://mcp.notion.com/mcp",
    description: "",
    status: "connected",
    error: "",
    exposure: "deferred",
    signed_in: false,
    uses_key: false,
    env: [],
    agents: [],
    skipped: [],
    tools: [],
    ...overrides,
  };
}

/** The row of `tool_search` (`mcp/tool_search.py`), held by `agents`. */
export function searchTool(agents: string[]): RegistryTool {
  return {
    name: "tool_search",
    description: "Tìm và nạp công cụ của các máy chủ MCP được giao cho bạn.",
    requires_approval: false,
    agents,
    optional: false,
    with_mcp: true,
  };
}

/** The row of `tool_script` (`script/tool.py`), held by `agents`. */
export function scriptTool(agents: string[]): RegistryTool {
  return {
    name: "tool_script",
    description: "Chạy một đoạn script Python ngắn để gọi nhiều công cụ chỉ đọc rồi tự lọc, gộp kết quả.",
    requires_approval: false,
    agents,
    optional: false,
    with_mcp: true,
  };
}

export class FakeMcp {
  /** Set to the server's words to refuse the next sign-in; cleared once it has. */
  refuseSignIn: string | null = null;
  /** What each server reads as once it is tried again, by name: a server that came up, or
   *  one that is still down for another reason. Used once. */
  private next = new Map<string, Partial<McpServerInfo>>();
  /** What the agents go on holding of a server whose try has not ended, by its name. */
  private held = new Map<string, McpToolInfo[]>();

  /** The crew, when the fake has one: who uses a server is then read off the agents'
   *  own lists, as the server reads it, and not off the row a test seeded. */
  crew: (() => { id: string; mcp?: string[] }[]) | null = null;

  constructor(public servers: McpServerInfo[] = []) {}

  private usedBy(name: string, seeded: string[]): string[] {
    if (!this.crew) return seeded;
    return this.crew().filter((a) => (a.mcp ?? []).includes(name)).map((a) => a.id).sort();
  }

  /** The rows GET /tools adds: a tool is listed once an agent holds it, and a hidden one
   *  is handed to nobody. An agent with a tool that is not declared up front holds the
   *  search for it too, and one with a tool that only reads and is opened for scripts
   *  holds the script tool as well (`mcp/handout.py`). */
  registryTools(): RegistryTool[] {
    const searching = new Set<string>();
    const scripting = new Set<string>();
    const rows = this.servers.flatMap((server) => {
      const agents = this.usedBy(server.name, server.agents);
      // The agents are handed what a try found only once it has ended (`mcp_lifecycle`).
      const tools = server.status === "idle" ? (this.held.get(server.name) ?? server.tools) : server.tools;
      const handed = tools.filter((tool) => tool.exposure !== "hidden");
      if (handed.some((tool) => tool.exposure !== "direct")) for (const agent of agents) searching.add(agent);
      // A tool that asks first is never a script's to call, whatever it is opened as.
      if (handed.some((tool) => tool.exposure === "codemode" && !tool.requires_approval))
        for (const agent of agents) scripting.add(agent);
      return handed.map((tool) => ({
        name: tool.name,
        description: tool.description,
        requires_approval: tool.requires_approval,
        agents,
        optional: false,
        server: server.name,
        exposure: tool.exposure,
      }));
    });
    const held = rows.filter((row) => row.agents.length > 0);
    const companions = [
      ...(searching.size > 0 ? [searchTool([...searching].sort())] : []),
      ...(scripting.size > 0 ? [scriptTool([...scripting].sort())] : []),
    ];
    return [...companions, ...held];
  }

  /** The next reconnect of `name`, or the next read of the list after a key changed, finds it so. */
  becomes(name: string, change: Partial<McpServerInfo>): void {
    this.next.set(name, change);
  }

  /** A try of `name` begins, as `hub._connect` begins one: the list names the server as being
   *  tried, with no tool, while the agents keep the ones it had until the try ends. */
  tries(name: string): void {
    const server = this.servers.find((s) => s.name === name);
    if (!server) return;
    this.held.set(name, server.tools);
    this.change(name, { status: "idle", tools: [], skipped: [] });
  }

  /** What `mcp_lifecycle.retry_loop` does when a key changes: try the servers that wait. */
  wake(): void {
    for (const server of this.servers) if (server.status === "idle" || server.status === "failed") this.settle(server.name);
  }

  /** The profile rule: an edit that leaves a name the file does not declare is refused. */
  refusal(mcp: unknown): string | null {
    const names = Array.isArray(mcp) ? (mcp as string[]) : [];
    const stray = names.find((name) => !this.servers.some((s) => s.name === name));
    return stray === undefined ? null : unknownServer(stray);
  }

  route(path: string, method: string): McpReply | null {
    if (path === "/mcp" && method === "GET") return this.list();
    const match = path.match(/^\/mcp\/([^/]+)\/(reconnect|login)$/);
    if (!match) return null;
    const name = decodeURIComponent(match[1]);
    const server = this.servers.find((s) => s.name === name);
    if (!server) return { status: 404, body: { detail: `Không có máy chủ MCP tên ${name}.` } };
    if (match[2] === "reconnect" && method === "POST") {
      this.settle(name);
      return this.list();
    }
    if (match[2] === "login" && method === "POST") {
      const refused = this.refuseSignIn;
      this.refuseSignIn = null;
      if (refused) return { status: 409, body: { detail: refused } };
      return { status: 200, body: { authorize_url: authorizeUrl(name) } };
    }
    if (match[2] === "login" && method === "DELETE") {
      this.change(name, { signed_in: false, status: "signed_out", error: "", tools: [], skipped: [] });
      return this.list();
    }
    return null;
  }

  /** The person came back from the authorization server: the sign-in is kept and the server
   *  connects, as `sign_in.finish` leaves it. */
  signedIn(name: string, tools: McpToolInfo[] = []): void {
    this.change(name, { signed_in: true, status: "connected", error: "", tools });
  }

  private list(): McpReply {
    const servers = this.servers.map((s) => ({ ...s, agents: this.usedBy(s.name, s.agents) }));
    return { status: 200, body: { servers } };
  }

  private settle(name: string): void {
    const change = this.next.get(name);
    this.next.delete(name);
    if (change) this.change(name, change);
  }

  private change(name: string, change: Partial<McpServerInfo>): void {
    this.servers = this.servers.map((s) => (s.name === name ? { ...s, ...change } : s));
  }
}
