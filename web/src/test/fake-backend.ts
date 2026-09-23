import type {
  ActivityPayload,
  AgentEvent,
  AgentInfo,
  AgentMemory,
  ApprovalInfo,
  ConnectionsInfo,
  Conversation,
  ConversationDetail,
  FactInfo,
  FactType,
  JobInfo,
  MemoryProposal,
  RegistryTool,
  RunInfo,
  SettingsInfo,
  StatsInfo,
  StoredMessage,
  TemplateInfo,
} from "../api/types";
import { FakeWiki } from "./fake-wiki";

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
  shell_ask_patterns: ["rm -rf"],
  tool_output_chars: 4000,
  memory_consolidate: "",
  persona_files: [],
  persona_names: ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md"],
  skills_dirs: ["/h/skills"],
  mode: "assistant",
  delegates: [],
  schedules: [],
  tools: ["write_file"],
  skills: ["core", "writer"],
  is_master: true,
  editable: true,
  telegram: null,
  commands: [],
  hooks: 0,
  kits: [],
  declared: { delegates: [], schedules: [] },
};

export const coderTemplate: TemplateInfo = {
  id: "coder",
  name: "Coder",
  description: "Viết và sửa mã",
  mode: "work",
  tools: ["shell_run", "workspace_write"],
  delegates: [],
};

export const coachAgent: AgentInfo = {
  ...fakeAgent,
  id: "coach",
  name: "HLV sức khoẻ",
  description: "Theo dõi sức khoẻ",
  workspace: "/tmp/home/agents/coach/workspace",
  autonomous: true,
  is_master: false,
  schedules: [
    { id: "brief", name: "Bản tin sáng", kind: "prompt", cron: "0 7 * * *", every: null, prompt: "Tóm tắt", command: null, enabled: true, skills: ["goodreads"] },
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
  /** Bundled profiles answered by GET /templates; installing one appends to `agents`. */
  templates: TemplateInfo[] = [];
  runs: RunInfo[] = [];
  jobs: JobInfo[] = [];
  /** Rows answered by GET /approvals, newest first. */
  approvals: ApprovalInfo[] = [];
  /** What the last answered question was replied with, so a test can assert the words. */
  lastAnswer: string | null = null;
  stats: StatsInfo = { runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {}, days: [], models: [], pending_proposals: 0 };
  userMd = "";
  facts: FactInfo[] = [];
  agentMemory = new Map<string, AgentMemory>();
  notes = new Map<string, string>();
  proposals: MemoryProposal[] = [];
  settings: SettingsInfo = {
    home: "/tmp/home",
    workspace_dir: "/tmp/home/workspace",
    users_dir: "/tmp/home/users",
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
    skills: [
      { name: "core", description: "Luôn bật", always: true },
      { name: "writer", description: "Viết lách", always: false },
      {
        name: "gws-shared",
        description: "Google Workspace",
        always: false,
        requires_bins: ["gws"],
        cli_help: "gws --help",
        missing_bins: ["gws"],
      },
    ],
    agents: [fakeAgent],
  };
  /** Persona files written by PUT /agents/{id}/files/{name}, keyed "<agent>/<name>". */
  personaFiles = new Map<string, string>();
  connections: ConnectionsInfo = {
    providers: [{ name: "fake", built: true }],
    routes: [{ provider: "fake", model: "echo" }],
    routes_source: "config",
    vision_routes: [],
    keys: [
      { name: "OPENROUTER_API_KEY", present: false },
      { name: "BRAVE_API_KEY", present: false },
      { name: "TAVILY_API_KEY", present: false },
      { name: "FIRECRAWL_API_KEY", present: false },
    ],
    search_backends: ["duckduckgo"],
    firecrawl_base_url: "",
    ollama_base_url: "http://127.0.0.1:11434/v1",
    telegram: [],
  };
  /** The wiki vault, empty until a test puts pages in it. */
  wiki = new FakeWiki();
  /** Set to a message to make the next PATCH refuse, the way a bad field would. */
  refuseEdit: string | null = null;
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

    // Before the rest of /memory: the wiki paths sit under it and would otherwise be
    // swallowed by the note and fact matches.
    const wiki = this.wiki.route(path, method, body ?? {}, url.searchParams, (id) =>
      this.agents.some((a) => a.id === id),
    );
    if (wiki) return wiki;
    const memory = this.memoryRoute(path, method, body, url.searchParams);
    if (memory) return memory;
    if (path === "/settings") return json(this.settings);
    if (path === "/agents" && method === "POST") return this.createAgent(body.agent_id, body.profile);
    if (path === "/agents") return json(this.master());
    if (path === "/templates") return json(this.templates);
    if (path === "/agents/install" && method === "POST") return this.install(body.template, body.agent_id);
    if (path === "/tools") return json(this.tools());
    if (path === "/connections") return json(this.connections);
    if (path === "/connections/routes" && method === "PUT") {
      this.connections = { ...this.connections, routes: body.routes, routes_source: "config" };
      return json({ ...this.connections, restart_required: null });
    }
    // Before the single-agent routes: `/agents/reload` would otherwise read as an agent
    // whose id happens to be "reload".
    if (path === "/agents/reload" && method === "POST") return json({ added: [] });
    const persona = path.match(/^\/agents\/([^/]+)\/files\/([^/]+)$/);
    if (persona && method === "PUT") {
      this.personaFiles.set(`${decodeURIComponent(persona[1])}/${persona[2]}`, body.content);
      return json({ name: persona[2], chars: String(body.content).length });
    }
    if (persona && method === "GET") {
      // A file that was never written reads as empty, the way the server reports one an
      // agent may have but has not created yet.
      const content = this.personaFiles.get(`${decodeURIComponent(persona[1])}/${persona[2]}`) ?? "";
      return json({ name: persona[2], content, chars: content.length });
    }
    const prompted = path.match(/^\/agents\/([^/]+)\/prompt$/)?.[1];
    if (prompted && method === "GET") {
      const agentId = decodeURIComponent(prompted);
      if (!this.agents.some((a) => a.id === agentId)) {
        return json({ detail: "agent not found" }, 404);
      }
      // Assembled from what was written, the way the server rebuilds it every turn: a
      // persona saved a moment ago has to show up in the very next read.
      const sections = [...this.personaFiles]
        .filter(([key]) => key.startsWith(`${agentId}/`))
        .map(([key, content]) => `\n## ${key.split("/")[1]}\n${content}\n`);
      const prompt = `Bạn là một trợ lý.\n${sections.join("")}`;
      return json({ prompt, chars: prompt.length });
    }
    const edited = path.match(/^\/agents\/([^/]+)$/)?.[1];
    if (edited && method === "PATCH") return this.patchAgent(decodeURIComponent(edited), body.profile);
    if (edited && method === "DELETE") return this.deleteAgent(decodeURIComponent(edited));
    if (edited && method === "GET") {
      const found = this.agents.find((a) => a.id === decodeURIComponent(edited));
      return found ? json(found) : json({ detail: "agent not found" }, 404);
    }
    // Ahead of the list route below, so a run id is not read as part of it.
    const oneRun = path.match(/^\/activity\/runs\/([^/]+)$/);
    if (oneRun) {
      const found = this.runs.find((r) => r.id === decodeURIComponent(oneRun[1]));
      return found ? json(found) : json({ detail: "run not found" }, 404);
    }
    if (path === "/activity/runs") return json(this.runs);
    if (path === "/stats") return json(this.stats);
    if (path === "/jobs") return json(this.jobs);
    if (path === "/approvals") {
      // Like the server: narrowing happens here, so the page belongs to the conversation.
      const only = url.searchParams.get("conversation_id");
      return json(only ? this.approvals.filter((a) => a.conversation_id === only) : this.approvals);
    }
    const job = path.match(/^\/jobs\/(.+)\/run$/)?.[1];
    if (job && method === "POST") return json({ job_id: decodeURIComponent(job), status: "started" }, 202);
    const switched = path.match(/^\/jobs\/(.+)\/state$/)?.[1];
    if (switched && method === "PATCH") {
      const found = this.jobs.find((j) => j.id === decodeURIComponent(switched));
      if (!found) return json({ detail: "job not found" }, 404);
      found.paused = !body.enabled;
      found.enabled = body.enabled;
      return json(found);
    }
    const history = path.match(/^\/jobs\/(.+)\/runs$/)?.[1];
    if (history) return json(this.runs.filter((r) => r.source === `job:${decodeURIComponent(history)}`));
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
    // The real server keeps the two closing paths apart and 409s each other's rows, so
    // the fake does too: a card wired to the wrong route must fail here, not in the wild.
    if (conv && /\/approvals\//.test(path) && method === "POST") {
      const c = this.conversations.get(conv)!;
      const answering = path.endsWith("/answer");
      const isQuestion = c.pending_approval?.kind === "question";
      if (answering !== isQuestion) {
        return json({ detail: answering ? "this is a tool call" : "this is a question" }, 409);
      }
      if (answering && !String(body?.answer ?? "").trim()) return json({ detail: "answer is empty" }, 422);
      if (answering) this.lastAnswer = String(body.answer);
      if (body?.always && c.pending_approval) c.auto_approve = [...c.auto_approve, c.pending_approval.tool_name];
      c.pending_approval = null;
      return this.streamTurn();
    }
    if (conv && method === "GET") return json(this.conversations.get(conv));
    if (conv && method === "PATCH") return json(listItem(Object.assign(this.conversations.get(conv)!, body)));
    if (conv && method === "DELETE") {
      this.conversations.delete(conv);
      return new Response(null, { status: 204 });
    }
    return json({ detail: `no route ${method} ${path}` }, 404);
  };

  /** Like the server, the master's `delegates` is everyone else, whatever its profile says. */
  private master(): AgentInfo[] {
    const others = this.agents.filter((a) => !a.is_master).map((a) => a.id);
    return this.agents.map((a) => (a.is_master ? { ...a, delegates: others } : a));
  }

  /** Like the server: the union over the crew, each tool naming the agents that hold it. */
  private tools(): RegistryTool[] {
    const names = [...new Set(this.agents.flatMap((a) => a.tools))].sort();
    return names.map((name) => ({
      name,
      description: this.settings.tools.find((t) => t.name === name)?.description ?? "",
      requires_approval: this.settings.tools.find((t) => t.name === name)?.requires_approval ?? false,
      optional: name === "web_search" || name === "image_read",
      agents: this.agents.filter((a) => a.tools.includes(name)).map((a) => a.id),
    }));
  }

  private createAgent(agentId: string, profile: Record<string, unknown>): Response {
    if (this.agents.some((a) => a.id === agentId))
      return json({ detail: `agent ${agentId} already exists` }, 409);
    const created: AgentInfo = { ...fakeAgent, ...profile, id: agentId, is_master: false };
    this.agents = [...this.agents, created];
    return json({ profile: created, restart_required: [] }, 201);
  }

  private patchAgent(agentId: string, profile: Record<string, unknown>): Response {
    const found = this.agents.find((a) => a.id === agentId);
    if (!found) return json({ detail: `agent ${agentId} not found` }, 404);
    if (this.refuseEdit) return json({ detail: this.refuseEdit }, 422);
    Object.assign(found, profile);
    // Only these three are read at boot, so only these three ask for a restart.
    const restart = ["schedules", "telegram", "memory_consolidate"].filter((k) => k in profile);
    return json({ profile: found, restart_required: restart });
  }

  private deleteAgent(agentId: string): Response {
    const found = this.agents.find((a) => a.id === agentId);
    if (!found) return json({ detail: `agent ${agentId} not found` }, 404);
    if (found.is_master) return json({ detail: "không xoá được agent điều phối" }, 409);
    const users = this.agents.filter((a) => !a.is_master && a.delegates.includes(agentId));
    if (users.length > 0)
      return json({ detail: `${users.map((a) => a.id).join(", ")} đang giao việc cho ${agentId}` }, 409);
    this.agents = this.agents.filter((a) => a.id !== agentId);
    return json({ removed: agentId, kept_at: `/tmp/home/agents/.trash/${agentId}` });
  }

  private install(template: string, agentId?: string): Response {
    const found = this.templates.find((t) => t.id === template);
    if (!found) return json({ detail: `unknown template ${template}` }, 404);
    const id = agentId || found.id;
    if (this.agents.some((a) => a.id === id)) return json({ detail: `agent ${id} already exists` }, 409);
    this.agents = [
      ...this.agents,
      { ...fakeAgent, id, name: found.name, description: found.description, mode: found.mode, tools: found.tools, delegates: found.delegates, is_master: false },
    ];
    return json({ installed: [id], live: [id], needs_restart: false }, 201);
  }

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
      auto_approve: [],
      parent_call_id: "",
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

  /** Every /memory and /agents/{id}/memory route; null when the path is not one of them. */
  private memoryRoute(
    path: string,
    method: string,
    // Parsed request body; each branch knows which fields its own request carries.
    body: {
      user_md: string;
      memory_md: string;
      description: string;
      type: FactType;
      body: string;
      approve: boolean;
    },
    params: URLSearchParams,
  ): Response | null {
    if (path === "/memory/user" && method === "GET") return json(this.userMemory());
    if (path === "/memory/user" && method === "PUT") {
      this.userMd = body.user_md;
      return json(this.userMemory());
    }
    const factName = path.match(/^\/memory\/user\/facts\/(.+)$/)?.[1];
    if (factName && method === "PUT") {
      const fact: FactInfo = {
        name: decodeURIComponent(factName),
        description: body.description,
        type: body.type,
        written_by: "web",
        source: "web",
        updated: "2026-09-20T09:00:00",
        body: body.body,
      };
      this.facts = [fact, ...this.facts.filter((f) => f.name !== fact.name)];
      return json(fact);
    }
    if (factName && method === "DELETE") {
      const name = decodeURIComponent(factName);
      if (!this.facts.some((f) => f.name === name)) return json({ detail: "fact not found" }, 404);
      this.facts = this.facts.filter((f) => f.name !== name);
      return new Response(null, { status: 204 });
    }
    if (path.startsWith("/memory/search")) return json({ hits: this.hits });
    if (path.startsWith("/memory/proposals/") && method === "POST") {
      const id = path.slice("/memory/proposals/".length);
      const found = this.proposals.find((p) => p.id === id);
      if (!found) return json({ detail: "proposal not found" }, 404);
      if (found.status !== "pending") return json({ detail: "already decided" }, 409);
      found.status = body.approve ? "approved" : "rejected";
      found.resolved_at = "2026-09-20T09:00:00";
      this.stats = { ...this.stats, pending_proposals: this.pending().length };
      return json(found);
    }
    if (path.startsWith("/memory/proposals")) {
      const all = params.get("status") === "all";
      return json({ proposals: all ? this.proposals : this.pending() });
    }
    const consolidating = path.match(/^\/agents\/([^/]+)\/memory\/consolidate$/)?.[1];
    if (consolidating && method === "POST") {
      if (this.consolidateBusy) return json({ detail: "đang cô đọng" }, 409);
      this.consolidated.push(consolidating);
      return json({ agent_id: consolidating, run_source: "memory:consolidate" }, 202);
    }
    const agentMemory = path.match(/^\/agents\/([^/]+)\/memory$/)?.[1];
    if (agentMemory) {
      if (!this.agents.some((a) => a.id === agentMemory)) return json({ detail: "agent not found" }, 404);
      if (method === "PUT") this.setAgentMemory(agentMemory, { memory_md: body.memory_md });
      return json(this.readAgentMemory(agentMemory));
    }
    const note = path.match(/^\/agents\/([^/]+)\/memory\/notes\/(.+)$/);
    if (note) {
      const [, agentId, day] = note;
      if (method === "PUT") {
        this.notes.set(`${agentId}/${day}`, body.body);
        const current = this.readAgentMemory(agentId);
        if (!current.notes.some((n) => n.day === day)) {
          this.setAgentMemory(agentId, {
            notes: [{ day, chars: body.body.length, date: day.slice(0, 10) }, ...current.notes],
            note_count: current.note_count + 1,
          });
        }
      }
      return json({ day, body: this.notes.get(`${agentId}/${day}`) ?? "" });
    }
    return null;
  }

  /** Agents a consolidation was asked for, newest last. */
  consolidated: string[] = [];
  /** When true the next consolidation request answers 409, as a running one would. */
  consolidateBusy = false;

  /** Hits returned by the next GET /memory/search. */
  hits: { scope: "user" | "agent"; agent_id: string; file: string; text: string }[] = [];

  readAgentMemory(agentId: string): AgentMemory {
    return this.agentMemory.get(agentId) ?? { memory_md: "", notes: [], note_count: 0 };
  }

  setAgentMemory(agentId: string, patch: Partial<AgentMemory>): void {
    this.agentMemory.set(agentId, { ...this.readAgentMemory(agentId), ...patch });
  }

  addProposal(overrides: Partial<MemoryProposal> = {}): MemoryProposal {
    const proposal: MemoryProposal = {
      id: `p${++this.counter}`,
      agent_id: "default",
      kind: "user_fact",
      name: "ngu-som",
      description: "Ngủ trước 23h",
      type: "preference",
      body: "Ngủ sớm mỗi ngày.",
      previous_body: "",
      status: "pending",
      source: "job",
      created_at: "2026-09-20T07:00:00",
      resolved_at: null,
      ...overrides,
    };
    this.proposals.push(proposal);
    this.stats = { ...this.stats, pending_proposals: this.pending().length };
    return proposal;
  }

  private pending(): MemoryProposal[] {
    return this.proposals.filter((p) => p.status === "pending");
  }

  private userMemory() {
    return {
      user_md: this.userMd,
      facts: this.facts,
      index_md: this.facts.map((f) => `- [${f.description}](${f.name}.md)`).join("\n"),
    };
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

/** The sidebar's view of a conversation: what the list endpoint and the activity
 *  stream both send. */
export function listItem(detail: ConversationDetail): Conversation {
  const { messages: _messages, pending_approval: _pending, ...rest } = detail;
  return rest;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
