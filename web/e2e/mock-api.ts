import type { Page, Route } from "@playwright/test";
import type { AgentInfo } from "../src/api/types";

// Every /api call is answered in-browser so the smoke tests measure the real DOM without a backend.
export type Conversation = Record<string, unknown> & { id: string; messages: unknown[]; pending_approval: unknown };

// Annotated rather than inferred: a fixture the compiler does not check against the real
// type drifts silently, and the screens then render fields in a state the backend can
// never produce — a smoke test that passes while proving nothing about them.
export const defaultAgent: AgentInfo = {
  id: "default",
  name: "Agent",
  description: "",
  dir: "/h/agents/default",
  workspace: "/h/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  cost_cap_usd: 1,
  max_steps: 20,
  autonomous: false,
  shell_ask_patterns: [],
  tool_output_chars: 2000,
  memory_consolidate: "",
  persona_files: [],
  persona_names: ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md"],
  skills_dirs: ["/h/skills"],
  schedules: [],
  mode: "assistant",
  delegates: [],
  tools: ["write_file"],
  skills: ["core"],
  is_master: true,
  editable: true,
  telegram: null,
  declared: { delegates: [], schedules: [] },
  commands: [],
  hooks: 0,
  kits: [],
};

export const devAgent = {
  ...defaultAgent,
  is_master: false,
  id: "dev",
  name: "Dev",
  mode: "work",
  cost_cap_usd: 5,
  max_steps: 60,
  delegates: ["coder"],
  tools: [],
};

export const coderTemplate = {
  id: "coder",
  name: "Coder",
  description: "Viết và sửa mã theo yêu cầu.",
  mode: "work",
  tools: ["shell_run", "workspace_write"],
  delegates: [],
};

export const coachAgent = {
  ...defaultAgent,
  is_master: false,
  id: "coach",
  name: "HLV sức khoẻ",
  workspace: "/h/agents/coach/workspace",
  autonomous: true,
  schedules: [{ id: "brief", name: "Bản tin sáng", kind: "prompt", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, enabled: true, skills: ["goodreads"] }],
};

/** The registry as the server reports it: one row per tool, naming the agents that have it. */
export const registryTools = [
  { name: "write_file", description: "Ghi tệp", requires_approval: true, agents: ["default"], optional: false },
  { name: "web_search", description: "Tìm trên web", requires_approval: false, agents: [], optional: true },
];

export const connections = {
  providers: [{ name: "fake", built: true }],
  routes: [{ provider: "fake", model: "echo" }],
  vision_routes: [],
  keys: [
    { name: "OPENROUTER_API_KEY", present: true },
    { name: "BRAVE_API_KEY", present: false },
  ],
  search_backends: ["firecrawl", "duckduckgo"],
  firecrawl_base_url: "http://127.0.0.1:3002",
  telegram: [{ agent_id: "default", token_env: "TELEGRAM_BOT_TOKEN", configured: true, ignored: false }],
};

/** The keys the Connections page lists, as the server describes them: never a secret's value. */
export const credentialItems = [
  { name: "OPENROUTER_API_KEY", group: "model", secret: true, url: false, present: true, source: "file", checkable: true },
  { name: "OLLAMA_BASE_URL", group: "model", secret: false, url: true, present: false, source: null, checkable: true, value: "", default: "http://127.0.0.1:11434/v1" },
  { name: "BRAVE_API_KEY", group: "search", secret: true, url: false, present: false, source: null, checkable: false },
  { name: "TELEGRAM_BOT_TOKEN", group: "telegram", secret: true, url: false, present: true, source: "file", checkable: true, agents: ["default"] },
];

export const settings = {
  home: "/h",
  workspace_dir: "/h/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  providers: ["fake"],
  language: "vi",
  timezone: "Asia/Ho_Chi_Minh",
  zone: "Asia/Ho_Chi_Minh",
  cost_cap_usd: 1,
  max_steps: 20,
  autonomous_default: false,
  keys: { openrouter: false, brave: false, tavily: false },
  tools: [{ name: "write_file", description: "Ghi tệp", requires_approval: true }],
  skills: [{ name: "core", description: "", always: true }],
  agents: [defaultAgent],
};

export function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: null,
    source: "chat",
    title: "Việc",
    status: "done",
    started_at: "2026-09-19T08:00:00Z",
    finished_at: "2026-09-19T08:00:05Z",
    spent_usd: 0.01,
    unknown_cost_calls: 0,
    summary: "Xong.",
    steps: [],
    ...overrides,
  };
}

export interface MockOptions {
  /** Event lists streamed by successive POST /messages or /approvals calls. */
  turns?: object[][];
  agents?: object[];
  runs?: object[];
  jobs?: object[];
  stats?: object;
  /** Activity payloads delivered on the SSE stream right after it opens. */
  stream?: object[];
  conversations?: Conversation[];
  templates?: object[];
  tools?: object[];
}

export function sse(events: object[], retryMs = 60_000): string {
  const frames = events.map((e) => `event: ${(e as { type: string }).type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`);
  return `retry: ${retryMs}\r\n\r\n${frames.join("")}`;
}

export async function mockApi(page: Page, options: MockOptions = {}) {
  const turns = options.turns ?? [];
  const conversations = options.conversations ?? [];
  const agents = options.agents ?? [defaultAgent];
  const posted: { path: string; body: unknown }[] = [];
  /** Persona bodies written by PUT, keyed "<agent>/<name>". */
  const personaFiles = new Map<string, string>();
  const credentials: Array<Record<string, unknown> & { name: string; present: boolean; secret: boolean; group: string }> =
    credentialItems.map((c) => ({ ...c }));
  let created = conversations.length;
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "POST") posted.push({ path: path + url.search, body: route.request().postDataJSON() });
    if (path === "/settings") return json({ ...settings, agents });
    // Before the list route below, which matches on path alone: a POST to the same path
    // would otherwise be answered with the crew and never create anything.
    if (path === "/agents" && method === "POST") {
      const { agent_id, profile } = route.request().postDataJSON() as { agent_id: string; profile: object };
      if (agents.some((a) => (a as { id: string }).id === agent_id)) return json({ detail: `agent ${agent_id} already exists` }, 409);
      const made = { ...defaultAgent, ...profile, id: agent_id, is_master: false };
      agents.push(made);
      return json({ profile: made, restart_required: [] }, 201);
    }
    // Like the server, the master is reported as able to hand work to everyone else.
    if (path === "/agents") {
      const others = agents.filter((a) => !(a as { is_master?: boolean }).is_master).map((a) => (a as { id: string }).id);
      return json(agents.map((a) => ((a as { is_master?: boolean }).is_master ? { ...a, delegates: others } : a)));
    }
    if (path === "/templates") return json(options.templates ?? []);
    if (path === "/agents/install" && method === "POST") {
      const { template } = route.request().postDataJSON() as { template: string };
      const found = (options.templates ?? []).find((t) => (t as { id: string }).id === template);
      if (!found) return json({ detail: `unknown template ${template}` }, 404);
      if (agents.some((a) => (a as { id: string }).id === template)) return json({ detail: `agent ${template} already exists` }, 409);
      agents.push({ ...defaultAgent, ...found, is_master: false });
      return json({ installed: [template], live: [template], needs_restart: false }, 201);
    }
    if (path === "/tools") return json(options.tools ?? registryTools);
    if (path === "/connections") return json(connections);
    const credential = path.match(/^\/credentials(?:\/([^/]+))?(\/check)?$/);
    if (credential) {
      const name = credential[1] && decodeURIComponent(credential[1]);
      const answer = () => json({ file: "/h/env", items: credentials, restart_required: null });
      if (!name) return answer();
      const at = credentials.findIndex((c) => c.name === name);
      if (credential[2]) {
        if (at < 0 || !credentials[at].present) return json({ detail: `${name} chưa được đặt.` }, 409);
        return json({ ok: true, detail: "Khoá hợp lệ." });
      }
      if (method === "PUT") {
        const { value } = route.request().postDataJSON() as { value: string };
        const known = at >= 0 ? credentials[at] : undefined;
        const next = { ...(known ?? { name, group: "other", secret: true, url: false, checkable: false }), present: true, source: "file" };
        // Only what is not a secret comes back, as on the server.
        if (!next.secret) Object.assign(next, { value });
        if (known) credentials[at] = next;
        else credentials.push(next);
        return answer();
      }
      if (method === "DELETE") {
        if (at < 0 || !credentials[at].present) return json({ detail: `${name} chưa được đặt.` }, 404);
        if (credentials[at].group === "other") credentials.splice(at, 1);
        else credentials[at] = { ...credentials[at], present: false, source: null, ...(credentials[at].secret ? {} : { value: "" }) };
        return answer();
      }
    }
    // Ahead of the single-agent routes, or the id reads as "reload".
    if (path === "/agents/reload" && method === "POST") return json({ added: [] });
    const persona = path.match(/^\/agents\/([^/]+)\/files\/([^/]+)$/);
    if (persona) {
      const key = `${decodeURIComponent(persona[1])}/${persona[2]}`;
      if (method === "PUT") {
        const { content } = route.request().postDataJSON() as { content: string };
        personaFiles.set(key, content);
        return json({ name: persona[2], chars: content.length });
      }
      // Never written reads as empty, the way the server reports a file an agent may
      // have but has not created yet.
      const content = personaFiles.get(key) ?? "";
      return json({ name: persona[2], content, chars: content.length });
    }
    const prompted = path.match(/^\/agents\/([^/]+)\/prompt$/);
    if (prompted) {
      const agentId = decodeURIComponent(prompted[1]);
      // Assembled from what was written, the way the server rebuilds it every turn.
      const sections = [...personaFiles]
        .filter(([key]) => key.startsWith(`${agentId}/`))
        .map(([key, content]) => `\n## ${key.split("/")[1]}\n${content}\n`);
      const prompt = `Bạn là một trợ lý.\n${sections.join("")}`;
      return json({ prompt, chars: prompt.length });
    }
    const single = path.match(/^\/agents\/([^/]+)$/);
    if (single && (method === "PATCH" || method === "DELETE")) {
      const at = agents.findIndex((a) => (a as { id: string }).id === single[1]);
      if (at < 0) return json({ detail: `unknown agent ${single[1]}` }, 404);
      if (method === "DELETE") {
        const [gone] = agents.splice(at, 1);
        const id = (gone as { id: string }).id;
        return json({ removed: id, kept_at: `/h/removed/${id}` });
      }
      const { profile } = route.request().postDataJSON() as { profile: object };
      agents[at] = { ...agents[at], ...profile };
      return json({ profile: agents[at], restart_required: [] });
    }
    if (single && method === "GET") {
      const found = agents.find((a) => (a as { id: string }).id === single[1]);
      return found ? json(found) : json({ detail: `unknown agent ${single[1]}` }, 404);
    }
    // Ahead of the list route below, so a run id is not read as part of it.
    const oneRun = path.match(/^\/activity\/runs\/([^/]+)$/);
    if (oneRun) {
      // Decoded, as the real route does: the client encodes the id on its way out.
      const wanted = decodeURIComponent(oneRun[1]);
      const found = (options.runs ?? []).find((r) => (r as { id: string }).id === wanted);
      return found ? json(found) : json({ detail: "run not found" }, 404);
    }
    if (path === "/activity/runs") return json(options.runs ?? []);
    if (path === "/activity/stream")
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(options.stream ?? [{ type: "snapshot", runs: options.runs ?? [] }]) });
    if (path === "/stats")
      return json(options.stats ?? { runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {}, days: [], models: [] });
    if (path === "/jobs") return json(options.jobs ?? []);
    if (path === "/approvals") return json([]);
    if (/^\/jobs\/.+\/run$/.test(path) && method === "POST") return json({ job_id: path.slice(6, -4), status: "started" }, 202);
    if (/^\/jobs\/.+\/state$/.test(path) && method === "PATCH") {
      const { enabled } = route.request().postDataJSON() as { enabled: boolean };
      const job = (options.jobs ?? []).find((j) => (j as { id: string }).id === path.slice(6, -6));
      return job ? json({ ...job, enabled, paused: !enabled }) : json({ detail: "job not found" }, 404);
    }
    if (/^\/jobs\/.+\/runs$/.test(path)) return json([]);
    if (path === "/conversations" && method === "GET") {
      const agentId = url.searchParams.get("agent_id");
      return json(agentId ? conversations.filter((c) => c.agent_id === agentId) : conversations);
    }
    if (path === "/conversations" && method === "POST") {
      const conv: Conversation = {
        id: `c${++created}`, agent_id: "default", channel: "", title: "", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 1,
        skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null,
        ...(route.request().postDataJSON() ?? {}),
      };
      conversations.push(conv);
      return json(conv, 201);
    }
    // A question closes by its own `/answer` route, not by the approve/deny one, so the
    // pattern has to reach it — otherwise answering in the browser 404s here and the
    // test passes for a card that would never work against the real server.
    if (/\/(messages|approvals\/[^/]+(\/answer)?)$/.test(path) && method === "POST") {
      const events = turns.shift() ?? [];
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) });
    }
    const conv = conversations.find((c) => path.startsWith(`/conversations/${c.id}`));
    if (conv && method === "GET") return json(conv);
    if (conv && method === "PATCH") return json(Object.assign(conv, route.request().postDataJSON()));
    return json({ detail: "no route" }, 404);
  });
  return { posted, conversations };
}
