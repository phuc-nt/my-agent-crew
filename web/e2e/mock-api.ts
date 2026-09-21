import type { Page, Route } from "@playwright/test";

// Every /api call is answered in-browser so the smoke tests measure the real DOM without a backend.
export type Conversation = Record<string, unknown> & { id: string; messages: unknown[]; pending_approval: unknown };

export const defaultAgent = {
  id: "default",
  name: "Agent",
  description: "",
  dir: "/h/agents/default",
  workspace: "/h/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  cost_cap_usd: 1,
  max_steps: 20,
  autonomous: false,
  persona_files: [],
  schedules: [],
  mode: "assistant",
  delegates: [],
  tools: ["write_file"],
  skills: ["core"],
  is_master: true,
  telegram: null,
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

export const settings = {
  home: "/h",
  workspace_dir: "/h/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  providers: ["fake"],
  language: "vi",
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
  let created = conversations.length;
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "POST") posted.push({ path: path + url.search, body: route.request().postDataJSON() });
    if (path === "/settings") return json({ ...settings, agents });
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
    if (/\/(messages|approvals\/[^/]+)$/.test(path) && method === "POST") {
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
