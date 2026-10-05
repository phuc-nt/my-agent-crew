import type { Page, Route } from "@playwright/test";
import type { AgentEvent, AgentInfo, ContentHit, QueuedMessage, WikiPage, WikiPageEdit } from "../src/api/types";
import { fold } from "../src/components/conversation-search";
import { FakeCanvas, type FakeReply } from "../src/test/fake-canvas";
import { applyAgentPatch, restartRequired } from "../src/test/schedule-contract";
import { renderRoute } from "./mock-render";

// Every /api call is answered in-browser so the smoke tests measure the real DOM without a backend.
export type Conversation = Record<string, unknown> & {
  id: string;
  messages: unknown[];
  pending_approval: unknown;
  /** What `stop` answers with and empties: a test's own hang-then-queue route (see
   *  `queue.spec.ts`) pushes onto this array directly, the same object `stop` reads.
   *  Optional like the real `ConversationDetail.queued?`, so every existing fixture that
   *  builds a conversation without it stays valid; `mockApi` fills it in as `[]`. */
  queued?: QueuedMessage[];
};

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
  routes_source: "config",
  vision_routes: [],
  audio_routes: [],
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
  { name: "OPENROUTER_API_KEY", group: "model", secret: true, url: false, present: true, source: "file", checkable: true, editable: true },
  { name: "OLLAMA_BASE_URL", group: "model", secret: false, url: true, present: false, source: null, checkable: true, editable: true, value: "", default: "http://127.0.0.1:11434/v1" },
  { name: "BRAVE_API_KEY", group: "search", secret: true, url: false, present: false, source: null, checkable: false, editable: true },
  { name: "TELEGRAM_BOT_TOKEN", group: "telegram", secret: true, url: false, present: true, source: "file", checkable: true, editable: true, agents: ["default"] },
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

/** Like the server: narrowed before the limit, a conversation with what it delegated. */
function listRuns(runs: object[], params: URLSearchParams): object[] {
  const agent = params.get("agent_id");
  const conv = params.get("conversation_id");
  const limit = Number(params.get("limit") ?? runs.length);
  return (runs as { agent_id: string; conversation_id: string | null; source: string }[])
    .filter((r) => !agent || r.agent_id === agent)
    .filter((r) => !conv || r.conversation_id === conv || r.source === `delegate:${conv}`)
    .slice(0, limit);
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
  /** Each agent's wiki as whole pages; the list and the report are derived from them. */
  wiki?: Record<string, WikiPage[]>;
  /** The universe GET /messages/search filters by query, folded the same way as title search. */
  contentHits?: ContentHit[];
  /** The canvases the canvas routes answer from; a fresh, empty one when omitted. */
  canvas?: FakeCanvas;
  /** How many messages, from the first, the server takes and then fails to answer: the turn
   *  runs and is stored, and the connection drops before a byte of it reaches the page. */
  lostAnswers?: number;
  /** What the prompt preview says a new conversation's first message is read after: the
   *  agent's daily notes. Empty when omitted, as for an agent that has written none. */
  promptOpening?: string;
}

export function sse(events: object[], retryMs = 60_000): string {
  const frames = events.map((e) => `event: ${(e as { type: string }).type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`);
  return `retry: ${retryMs}\r\n\r\n${frames.join("")}`;
}

export async function mockApi(page: Page, options: MockOptions = {}) {
  const turns = options.turns ?? [];
  // `queued` defaults to `[]` on every fixture that omits it, the same as an old server's
  // response would parse to on the client — so `stop`'s own `conv.queued ?? []` never has
  // to special-case a conversation that came from a literal rather than a runtime POST.
  const conversations: Conversation[] = (options.conversations ?? []).map((c) => ({
    ...c,
    queued: c.queued ?? [],
  }));
  const agents = options.agents ?? [defaultAgent];
  // Saved routes live per page, so one test's save never shows in the next.
  let routes = connections.routes;
  const posted: { path: string; body: unknown }[] = [];
  /** The `request_id`s of the messages stored, as "<conversation>/<request_id>". */
  const taken = new Set<string>();
  let lostAnswers = options.lostAnswers ?? 0;
  /** Persona bodies written by PUT, keyed "<agent>/<name>". */
  const personaFiles = new Map<string, string>();
  const credentials: Array<Record<string, unknown> & { name: string; present: boolean; secret: boolean; group: string }> =
    credentialItems.map((c) => ({ ...c }));
  let created = conversations.length;
  // Copied, so a page marked ok in one test is not already ok in the next.
  const wiki = new Map(Object.entries(options.wiki ?? {}).map(([id, pages]) => [id, pages.map((p) => ({ ...p }))]));
  const canvas = options.canvas ?? new FakeCanvas();
  canvas.conversationExists = (id) => conversations.some((c) => c.id === id);
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "POST") posted.push({ path: path + url.search, body: route.request().postDataJSON() });
    if (path === "/settings") return json({ ...settings, agents });
    if (path === "/health") return json({ status: "ok", version: "0.8.0" });
    // A canvas's page is a document with a policy of its own, not one of the JSON routes below.
    const rendered = renderRoute(route, canvas, path, method);
    if (rendered) return rendered;
    if (/^\/artifacts(\/|$)/.test(path)) {
      const reply = canvas.route(path, method, route.request().postDataJSON(), url.searchParams);
      return fulfillCanvas(route, await (reply ?? { status: 404, body: { detail: "Not Found" } }));
    }
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
    if (path === "/connections") return json({ ...connections, routes });
    if (path === "/connections/routes" && method === "PUT") {
      const body = route.request().postDataJSON() as { routes: typeof routes };
      const unknown = body.routes.find((r) => !connections.providers.some((p) => p.name === r.provider));
      if (unknown) return json({ detail: `Chưa lưu: chưa có nhà cung cấp ${unknown.provider}.` }, 409);
      routes = body.routes;
      return json({ ...connections, routes, restart_required: null });
    }
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
        const next = { ...(known ?? { name, group: "other", secret: true, url: false, checkable: false, editable: true }), present: true, source: "file" };
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
      const opening = options.promptOpening ?? "";
      return json({ prompt, chars: prompt.length, opening, opening_chars: opening.length });
    }
    const vault = path.match(/^\/agents\/([^/]+)\/memory\/wiki(?:\/(report)|\/pages\/([^/]+))?$/);
    if (vault && (method === "GET" || method === "PUT")) {
      const pages = wiki.get(decodeURIComponent(vault[1])) ?? [];
      if (vault[2]) {
        const questions = pages.flatMap((p) => p.questions.map((question) => ({ slug: p.slug, question })));
        return json({ problems: [], questions });
      }
      if (vault[3]) {
        const slug = decodeURIComponent(vault[3]);
        const at = pages.findIndex((p) => p.slug === slug);
        if (at < 0) return json({ detail: `unknown page ${slug}` }, 404);
        // Only the fields sent change, as the server merges a partial edit.
        if (method === "PUT") pages[at] = { ...pages[at], ...(route.request().postDataJSON() as WikiPageEdit) };
        return json(pages[at]);
      }
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const summaries = pages
        .filter((p) => `${p.title}\n${p.body}`.toLowerCase().includes(q))
        .map((p) => ({ slug: p.slug, kind: p.kind, title: p.title, status: p.status, updated: p.updated, sources: p.sources, question_count: p.questions.length }));
      return json({ pages: summaries, kinds: [...new Set(summaries.map((p) => p.kind))], count: summaries.length });
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
      const { profile } = route.request().postDataJSON() as { profile: Record<string, unknown> };
      const patched = applyAgentPatch(agents[at], profile);
      if ("error" in patched) return json({ detail: patched.error }, 422);
      agents[at] = patched.ok;
      return json({ profile: agents[at], restart_required: restartRequired(profile) });
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
    if (path === "/activity/runs") return json(listRuns(options.runs ?? [], url.searchParams));
    if (path === "/activity/stream")
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(options.stream ?? [{ type: "snapshot", runs: options.runs ?? [] }]) });
    if (path === "/stats")
      return json(options.stats ?? { runs: 0, model_calls: 0, spent_usd: 0, unknown_cost_calls: 0, by_agent: {}, by_model: {}, by_day: {}, days: [], models: [], purposes: [] });
    if (path === "/jobs") return json(options.jobs ?? []);
    if (path === "/approvals") return json([]);
    if (path === "/messages/search") {
      const needle = fold((url.searchParams.get("q") ?? "").trim());
      const hits = needle === "" ? [] : (options.contentHits ?? []).filter((h) => fold(`${h.title} ${h.snippet}`).includes(needle));
      return json({ hits });
    }
    if (/^\/jobs\/.+\/run$/.test(path) && method === "POST") return json({ job_id: path.slice(6, -4), status: "started" }, 202);
    if (/^\/jobs\/.+\/state$/.test(path) && method === "PATCH") {
      const { enabled } = route.request().postDataJSON() as { enabled: boolean };
      const job = (options.jobs ?? []).find((j) => (j as { id: string }).id === path.slice(6, -6));
      return job ? json({ ...job, enabled, paused: !enabled }) : json({ detail: "job not found" }, 404);
    }
    if (/^\/jobs\/.+\/runs$/.test(path)) return json([]);
    // Matched after the three suffixed routes above so a bare job id is not read as one of
    // them; a profile job (`origin: "profile"`) is never offered the delete button in the
    // first place, so this mock does not need to reject one the way the real server's 409
    // does — nothing here ever sends that request. Spliced in place, not filtered into a
    // copy, so a spec holding the same `jobs` array it passed to `mockApi` sees the removal.
    if (/^\/jobs\/.+$/.test(path) && method === "DELETE") {
      const id = path.slice(6);
      const list = options.jobs ?? [];
      const index = list.findIndex((j) => (j as { id: string }).id === id);
      if (index === -1) return json({ detail: "job not found" }, 404);
      list.splice(index, 1);
      return route.fulfill({ status: 204 });
    }
    if (path === "/conversations" && method === "GET") {
      const agentId = url.searchParams.get("agent_id");
      return json(agentId ? conversations.filter((c) => c.agent_id === agentId) : conversations);
    }
    if (path === "/conversations" && method === "POST") {
      const conv: Conversation = {
        id: `c${++created}`, agent_id: "default", channel: "", title: "", created_at: "", updated_at: "", autonomous: false, cost_cap_usd: 1,
        skills: [], auto_approve: [], spent_usd: 0, unknown_cost_calls: 0, status: "idle", over_budget: false, messages: [], pending_approval: null,
        queued: [], forked_from: "",
        ...(route.request().postDataJSON() ?? {}),
      };
      conversations.push(conv);
      return json(conv, 201);
    }
    // Stop: hands back whatever a test's own hang-then-queue route pushed onto this
    // conversation's `queued`, then empties it — the one thing the base handler cannot do
    // per-test, since the queue is state shared between that route and this one.
    const stopped = path.match(/^\/conversations\/([^/]+)\/stop$/)?.[1];
    if (stopped && method === "POST") {
      const conv = conversations.find((c) => c.id === decodeURIComponent(stopped));
      if (!conv) return json({ detail: "not found" }, 404);
      const cleared = conv.queued ?? [];
      conv.queued = [];
      return json({ cleared, cancelled: false });
    }
    // A question closes by its own `/answer` route, not by the approve/deny one, so the
    // pattern has to reach it — otherwise answering in the browser 404s here and the
    // test passes for a card that would never work against the real server.
    const sendingMessage = /\/messages$/.test(path) && method === "POST";
    if (sendingMessage || (/\/approvals\/[^/]+(\/answer)?$/.test(path) && method === "POST")) {
      // A decided request is closed on the server, so a page that reads the conversation
      // again (the attention list does, to see whether the turn paused anew) must not find it.
      const decided = conversations.find((c) => path.startsWith(`/conversations/${c.id}/approvals/`));
      if (decided) decided.pending_approval = null;
      const sent = sendingMessage ? conversations.find((c) => path.startsWith(`/conversations/${c.id}/messages`)) : undefined;
      if (sent) {
        // The canvas the tab had open goes with the message, as the server takes it: a selection
        // the note would drop refuses the message before it is stored or a turn is spent on it.
        const { canvas: carried, request_id: name } = route.request().postDataJSON() as { canvas?: unknown; request_id?: string };
        // A send the server took before starts nothing: it is answered with the conversation
        // as it stands, ahead of anything that could refuse a new message.
        if (name && taken.has(`${sent.id}/${name}`)) {
          const standing = [{ type: "watching", running: false, detail: sent }];
          return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(standing) });
        }
        const refusal = canvas.applyMessageCanvas(sent.id, carried);
        if (refusal) return fulfillCanvas(route, refusal);
        if (name) taken.add(`${sent.id}/${name}`);
      }
      const events = turns.shift() ?? [];
      if (sendingMessage) {
        // Persists the sent text and any assistant reply into `conv.messages`, the way the
        // real server would: `resolveMessageId` (see `use-fork.ts`) falls back to a fresh
        // `GET /conversations/{id}` for a bubble still carrying its optimistic `local-N` id,
        // and that read has to find the same rows the thread already shows, or every fork
        // attempted right after a send would 404 its own message out from under itself.
        if (sent) {
          const { text } = route.request().postDataJSON() as { text: string };
          const nextSeq = () => (sent.messages as { seq: number }[]).reduce((n, m) => Math.max(n, m.seq), 0) + 1;
          const nextId = () => String((sent.messages as { id: string }[]).reduce((n, m) => Math.max(n, Number(m.id) || 0), 0) + 1);
          // The note a turn streams back for its message is the one the server stored with it.
          const note = (events as AgentEvent[]).find((event) => event.type === "user_context");
          sent.messages.push({
            id: nextId(), seq: nextSeq(), role: "user", content: text, tool_calls: [],
            tool_call_id: null, name: null, provider: null, model: null, cost_usd: null, created_at: "",
            ...(note?.type === "user_context" ? { context: note.context } : {}),
          });
          for (const event of events as { type: string }[]) {
            if (event.type !== "assistant_message") continue;
            const e = event as Extract<AgentEvent, { type: "assistant_message" }>;
            sent.messages.push({
              id: nextId(), seq: nextSeq(), role: "assistant", content: e.content, tool_calls: e.tool_calls,
              tool_call_id: null, name: null, provider: e.provider, model: e.model, cost_usd: e.cost_usd, created_at: "",
            });
          }
        }
      }
      if (sent && lostAnswers > 0) {
        lostAnswers -= 1;
        return route.abort("connectionreset");
      }
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) });
    }
    // Rewind and fork: a new conversation holding a copy of every message before the cut,
    // with that message's own text handed back as `draft` — matches the real route's
    // response shape closely enough for `fork.spec.ts`, which only ever looks at the
    // fork's own row and draft; the store's atomicity and usage-neutrality guarantees are
    // exercised against the real server in the Python test suite, not re-proven here.
    const forking = path.match(/^\/conversations\/([^/]+)\/fork$/)?.[1];
    if (forking && method === "POST") {
      const source = conversations.find((c) => c.id === decodeURIComponent(forking));
      if (!source) return json({ detail: "conversation not found" }, 404);
      const { before_message_id } = route.request().postDataJSON() as { before_message_id: number };
      const messages = source.messages as { id: unknown; role: string; content: string }[];
      const cutIndex = messages.findIndex((m) => String(m.id) === String(before_message_id));
      if (cutIndex === -1) return json({ detail: "message not found" }, 404);
      const cut = messages[cutIndex];
      if (cut.role !== "user") return json({ detail: "cut message must be a saved user message" }, 400);
      const FORK_TITLE_SUFFIX = "(nhánh)"; // texts_fork.py's FORK_TITLE_SUFFIX
      const title = String(source.title ?? "");
      const suffixed = title === "" ? "" : title.endsWith(FORK_TITLE_SUFFIX) ? title : `${title} ${FORK_TITLE_SUFFIX}`;
      const fork: Conversation = {
        ...source,
        id: `c${++created}`,
        title: suffixed,
        channel: "",
        autonomous: false,
        auto_approve: [],
        parent_call_id: "",
        forked_from: source.id,
        spent_usd: 0,
        unknown_cost_calls: 0,
        summary: "",
        messages: messages.slice(0, cutIndex),
        pending_approval: null,
        queued: [],
      };
      conversations.push(fork);
      return json({ ...fork, draft: cut.content }, 201);
    }
    // Before the conversation routes below, which match on the start of the path alone and
    // would answer a read of the open canvas with the conversation.
    const focusing = path.match(/^\/conversations\/([^/]+)\/canvas$/)?.[1];
    if (focusing) {
      const id = decodeURIComponent(focusing);
      if (!conversations.some((c) => c.id === id)) return json({ detail: "conversation not found" }, 404);
      return fulfillCanvas(route, await canvas.focusRoute(id, method, route.request().postDataJSON()));
    }
    // Reading along with a turn under way: none is, unless a spec serves one in the page
    // (see `served-turn.ts`). Before the conversation routes below, which match on the start
    // of the path alone and would answer with the conversation.
    const watched = path.match(/^\/conversations\/([^/]+)\/turn$/)?.[1];
    if (watched && method === "GET") {
      const known = conversations.some((c) => c.id === decodeURIComponent(watched));
      return known ? route.fulfill({ status: 204 }) : json({ detail: "conversation not found" }, 404);
    }
    const conv = conversations.find((c) => path.startsWith(`/conversations/${c.id}`));
    if (conv && method === "GET") return json(conv);
    if (conv && method === "PATCH") {
      Object.assign(conv, route.request().postDataJSON());
      // Derived from the cap on the server, so a raised cap lifts the block here too.
      const cap = Number(conv.cost_cap_usd);
      conv.over_budget = cap > 0 && Number(conv.spent_usd) >= cap;
      return json(conv);
    }
    return json({ detail: "no route" }, 404);
  });
  return { posted, conversations, canvas };
}

/** A canvas reply as the browser would get it; a lost one fails the request. */
function fulfillCanvas(route: Route, reply: FakeReply) {
  if (reply === "lost") return route.abort("failed");
  if (reply.text !== undefined) {
    return route.fulfill({ status: reply.status, contentType: "text/plain; charset=utf-8", body: reply.text });
  }
  if (reply.status === 204) return route.fulfill({ status: 204 });
  return route.fulfill({ status: reply.status, contentType: "application/json", body: JSON.stringify(reply.body) });
}
