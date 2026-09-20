import type {
  ActivityPayload,
  AgentEvent,
  AgentInfo,
  Conversation,
  ConversationDetail,
  JobInfo,
  RunInfo,
  SettingsInfo,
  StatsInfo,
  StoredMessage,
} from "../api/types";

export const fakeAgent: AgentInfo = {
  id: "default",
  name: "Agent",
  description: "",
  dir: "/tmp/home",
  workspace: "/tmp/home/workspace",
  routes: [{ provider: "fake", model: "echo" }],
  cost_cap_usd: 1,
  max_steps: 20,
  autonomous: false,
  persona_files: [],
  schedules: [],
  tools: ["write_file"],
  skills: ["core", "writer"],
};

export const coachAgent: AgentInfo = {
  ...fakeAgent,
  id: "coach",
  name: "HLV sức khoẻ",
  description: "Theo dõi sức khoẻ",
  workspace: "/tmp/home/agents/coach/workspace",
  autonomous: true,
  schedules: [
    { id: "brief", name: "Bản tin sáng", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, enabled: true },
  ],
};

export function fakeRun(overrides: Partial<RunInfo> = {}): RunInfo {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: "c1",
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

/** In-memory stand-in for the FastAPI server, wired to `fetch` in component tests. */
export class FakeBackend {
  conversations = new Map<string, ConversationDetail>();
  agents: AgentInfo[] = [fakeAgent];
  runs: RunInfo[] = [];
  jobs: JobInfo[] = [];
  stats: StatsInfo = { runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {} };
  settings: SettingsInfo = {
    home: "/tmp/home",
    workspace_dir: "/tmp/home/workspace",
    routes: [{ provider: "fake", model: "echo" }],
    providers: ["fake"],
    language: "vi",
    cost_cap_usd: 1,
    max_steps: 20,
    autonomous_default: false,
    keys: { openrouter: false, brave: false, tavily: false },
    tools: [{ name: "write_file", description: "Ghi tệp", requires_approval: true }],
    skills: [
      { name: "core", description: "Luôn bật", always: true },
      { name: "writer", description: "Viết lách", always: false },
    ],
    agents: [fakeAgent],
  };
  /** What the next POST /summary writes onto the conversation. */
  nextSummary = "Bản tóm tắt mới.";

  /** Events streamed by the next POST /messages or /approvals call. */
  nextTurn: AgentEvent[] = [];
  requests: { method: string; path: string; body: unknown }[] = [];
  private counter = 0;

  fetch = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const url = new URL(String(input), "http://fake");
    const path = url.pathname.replace(/^\/api/, "");
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(String(init.body)) : null;
    this.requests.push({ method, path: path + url.search, body });
    const conv = path.match(/^\/conversations\/([^/]+)/)?.[1];

    if (path === "/settings") return json(this.settings);
    if (path === "/agents") return json(this.agents);
    if (path === "/activity/runs") return json(this.runs);
    if (path === "/stats") return json(this.stats);
    if (path === "/jobs") return json(this.jobs);
    const job = path.match(/^\/jobs\/(.+)\/run$/)?.[1];
    if (job && method === "POST") return json({ job_id: decodeURIComponent(job), status: "started" }, 202);
    if (path === "/conversations" && method === "GET") {
      const agentId = url.searchParams.get("agent_id");
      const all = [...this.conversations.values()].map(listItem);
      return json(agentId ? all.filter((c) => c.agent_id === agentId) : all);
    }
    if (path === "/conversations" && method === "POST") return json(listItem(this.create(body ?? {})), 201);
    if (conv && !this.conversations.has(conv)) return json({ detail: "not found" }, 404);
    if (conv && path.endsWith("/messages") && method === "POST") {
      const c = this.conversations.get(conv)!;
      if (c.status === "awaiting_approval") return json({ detail: "conversation is awaiting approval" }, 409);
      c.messages.push(storedMessage("user", body.text));
      return this.streamTurn();
    }
    if (conv && path.endsWith("/summary") && method === "POST") {
      const c = this.conversations.get(conv)!;
      c.summary = this.nextSummary;
      return json({ id: conv, summary: c.summary }, 202);
    }
    if (conv && /\/approvals\//.test(path) && method === "POST") return this.streamTurn();
    if (conv && method === "GET") return json(this.conversations.get(conv));
    if (conv && method === "PATCH") return json(listItem(Object.assign(this.conversations.get(conv)!, body)));
    if (conv && method === "DELETE") {
      this.conversations.delete(conv);
      return new Response(null, { status: 204 });
    }
    return json({ detail: `no route ${method} ${path}` }, 404);
  };

  create(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
    const id = `c${++this.counter}`;
    const detail: ConversationDetail = {
      id,
      agent_id: "default",
      channel: "",
      title: "",
      created_at: "2026-09-19T00:00:00Z",
      updated_at: "2026-09-19T00:00:00Z",
      autonomous: false,
      cost_cap_usd: 1,
      skills: [],
      spent_usd: 0,
      unknown_cost_calls: 0,
      status: "idle",
      over_budget: false,
      summary: "",
      messages: [],
      pending_approval: null,
      ...overrides,
    };
    this.conversations.set(id, detail);
    return detail;
  }

  private streamTurn(): Response {
    const events = this.nextTurn;
    this.nextTurn = [];
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const e of events) controller.enqueue(encoder.encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`));
        controller.close();
      },
    });
    return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
  }
}

/** Minimal EventSource the activity hook can subscribe to; tests push payloads through `emit`. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, handler: (event: MessageEvent<string>) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }

  open(): void {
    this.onopen?.();
  }

  emit(payload: ActivityPayload): void {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    for (const handler of this.listeners.get(payload.type) ?? []) handler(event);
  }

  close(): void {
    this.closed = true;
  }
}

export function storedMessage(role: StoredMessage["role"], content: string, extra: Partial<StoredMessage> = {}): StoredMessage {
  return {
    id: `m-${content.length}-${Math.random().toString(36).slice(2, 6)}`,
    seq: 0,
    role,
    content,
    tool_calls: [],
    tool_call_id: null,
    name: null,
    provider: null,
    model: null,
    cost_usd: null,
    created_at: "2026-09-19T00:00:00Z",
    ...extra,
  };
}

function listItem(detail: ConversationDetail): Conversation {
  const { messages: _messages, pending_approval: _pending, ...rest } = detail;
  return rest;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
