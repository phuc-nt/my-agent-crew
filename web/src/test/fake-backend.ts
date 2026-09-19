import type { AgentEvent, Conversation, ConversationDetail, SettingsInfo, StoredMessage } from "../api/types";

/** In-memory stand-in for the FastAPI server, wired to `fetch` in component tests. */
export class FakeBackend {
  conversations = new Map<string, ConversationDetail>();
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
  };
  /** Events streamed by the next POST /messages or /approvals call. */
  nextTurn: AgentEvent[] = [];
  requests: { method: string; path: string; body: unknown }[] = [];
  private counter = 0;

  fetch = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const path = String(input).replace(/^\/api/, "");
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(String(init.body)) : null;
    this.requests.push({ method, path, body });
    const conv = path.match(/^\/conversations\/([^/]+)/)?.[1];

    if (path === "/settings") return json(this.settings);
    if (path === "/conversations" && method === "GET") return json([...this.conversations.values()].map(summary));
    if (path === "/conversations" && method === "POST") return json(summary(this.create(body ?? {})), 201);
    if (conv && !this.conversations.has(conv)) return json({ detail: "not found" }, 404);
    if (conv && path.endsWith("/messages") && method === "POST") {
      const c = this.conversations.get(conv)!;
      if (c.status === "awaiting_approval") return json({ detail: "conversation is awaiting approval" }, 409);
      c.messages.push(storedMessage("user", body.text));
      return this.streamTurn();
    }
    if (conv && /\/approvals\//.test(path) && method === "POST") return this.streamTurn();
    if (conv && method === "GET") return json(this.conversations.get(conv));
    if (conv && method === "PATCH") return json(summary(Object.assign(this.conversations.get(conv)!, body)));
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

function summary(detail: ConversationDetail): Conversation {
  const { messages: _messages, pending_approval: _pending, ...rest } = detail;
  return rest;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
