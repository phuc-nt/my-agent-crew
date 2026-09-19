import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { ApiError, api } from "./client";
import type { AgentEvent } from "./types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function sseResponse(...blocks: string[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const block of blocks) controller.enqueue(new TextEncoder().encode(block));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

const fetchMock = vitest.fn<typeof fetch>();
vitest.stubGlobal("fetch", fetchMock);

afterEach(() => fetchMock.mockReset());

describe("api", () => {
  it("prefixes /api and parses JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: "c1" }]));
    const list = await api.listConversations();
    expect(list).toEqual([{ id: "c1" }]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/conversations");
  });

  it("sends PATCH bodies as JSON", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "c1", title: "new" }));
    await api.patchConversation("c1", { title: "new" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/c1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ title: "new" });
  });

  it("throws ApiError with the server detail on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "conversation is busy" }, 409));
    const failure = api.createConversation();
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(api.createConversation().catch((e: ApiError) => [e.status, e.message])).resolves.toEqual([
      409,
      "conversation is busy",
    ]).catch(() => undefined);
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce(new Response("nope", { status: 500, statusText: "Server Error" }));
    await expect(api.settings()).rejects.toMatchObject({ status: 500, message: "Server Error" });
  });

  it("returns undefined for 204 responses", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api.deleteConversation("c1")).resolves.toBeUndefined();
  });

  it("streams SSE events from sendMessage and forwards the abort signal", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        'event: text_delta\r\ndata: {"type":"text_delta","text":"hi"}\r\n\r\n',
        'event: done\r\ndata: {"type":"done","spent_usd":0,"unknown_cost_calls":0}\r\n\r\n',
      ),
    );
    const seen: AgentEvent[] = [];
    const controller = new AbortController();
    await api.sendMessage("c1", "hello", (e) => seen.push(e), controller.signal);
    expect(seen.map((e) => e.type)).toEqual(["text_delta", "done"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/c1/messages");
    expect(init?.signal).toBe(controller.signal);
    expect(JSON.parse(String(init?.body))).toEqual({ text: "hello" });
  });

  it("posts the decision to the approval endpoint", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse('data: {"type":"done","spent_usd":0,"unknown_cost_calls":0}\n\n'));
    await api.resolveApproval("c1", "ap1", false, () => undefined);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/c1/approvals/ap1");
    expect(JSON.parse(String(init?.body))).toEqual({ approve: false });
  });

  it("rejects a streaming call whose response is an error", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "busy" }, 409));
    await expect(api.sendMessage("c1", "x", () => undefined)).rejects.toMatchObject({ status: 409, message: "busy" });
  });
});

describe("activity api", () => {
  it("builds query strings and file urls without empty params", async () => {
    const { agentFileUrl } = await import("./client");
    expect(agentFileUrl("health coach", "out/a b.png")).toBe("/api/agents/health%20coach/files?path=out%2Fa+b.png");
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    await api.listRuns({ limit: 5, agent_id: undefined });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/activity/runs?limit=5");
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    await api.listConversations("coach");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/conversations?agent_id=coach");
    fetchMock.mockResolvedValueOnce(jsonResponse({ job_id: "coach/brief", status: "started" }, 202));
    await api.runJob("coach/brief");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/jobs/coach/brief/run");
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");
  });

  it("subscribes to the activity stream by event name and closes on unsubscribe", async () => {
    const { subscribeActivity } = await import("./client");
    const { FakeEventSource } = await import("../test/fake-backend");
    vitest.stubGlobal("EventSource", FakeEventSource);
    const seen: unknown[] = [];
    const status: boolean[] = [];
    const stop = subscribeActivity((p) => seen.push(p), (ok) => status.push(ok));
    const source = FakeEventSource.instances.at(-1)!;
    expect(source.url).toBe("/api/activity/stream");
    source.open();
    source.emit({ type: "snapshot", runs: [] });
    source.emit({ type: "run", run: { id: "r" } as never });
    source.onerror?.();
    expect(seen.map((p) => (p as { type: string }).type)).toEqual(["snapshot", "run"]);
    expect(status).toEqual([true, false]);
    stop();
    expect(source.closed).toBe(true);
  });
});
