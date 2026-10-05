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
    const error = await api.settings().catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 500, message: "Server Error" });
    expect((error as ApiError).detail).toBeUndefined();
  });

  it("keeps a structured error detail beside the message older callers read", async () => {
    const conflict = { head_version: 7, content: "theirs", author: "agent:ming" };
    const full = { used: 900, cap: 1000, largest: [{ id: "a1", title: "Big", size: 600 }] };
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: conflict }, 409));
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: full }, 507));
    const first = await api.settings().catch((e: unknown) => e);
    const second = await api.settings().catch((e: unknown) => e);
    expect(first).toBeInstanceOf(ApiError);
    expect(first).toMatchObject({ status: 409, message: JSON.stringify(conflict), detail: conflict });
    expect(second).toMatchObject({ status: 507, message: JSON.stringify(full), detail: full });
  });

  it("keeps a string detail as both the message and the detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "artifact not found" }, 404));
    await expect(api.settings()).rejects.toMatchObject({
      status: 404,
      message: "artifact not found",
      detail: "artifact not found",
    });
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

  // A message that says nothing of the canvas leaves the server's as it is; one that says
  // "none" closes it. The two must never read alike on the wire.
  it("carries the tab's canvas only when it is given, and a null one as it is", async () => {
    const done = 'event: done\r\ndata: {"type":"done","spent_usd":0,"unknown_cost_calls":0}\r\n\r\n';
    fetchMock.mockImplementation(async () => sseResponse(done));
    const pick = { version: 3, text: "chạy 5 km", line_start: 2, line_end: 2 };

    await api.sendMessage("c1", "none given", () => undefined);
    await api.sendMessage("c1", "none given, with a signal", () => undefined, new AbortController().signal);
    await api.sendMessage("c1", "closed", () => undefined, undefined, { artifact_id: null });
    await api.sendMessage("c1", "open", () => undefined, undefined, { artifact_id: "0123456789ab", selection: null });
    await api.sendMessage("c1", "asking", () => undefined, undefined, { artifact_id: "0123456789ab", selection: pick });

    const bodies = fetchMock.mock.calls.map(([, init]) => String(init?.body));
    expect(bodies[0]).toBe('{"text":"none given"}');
    expect(bodies[1]).toBe('{"text":"none given, with a signal"}');
    expect(JSON.parse(bodies[2])).toEqual({ text: "closed", canvas: { artifact_id: null } });
    expect(JSON.parse(bodies[3])).toEqual({ text: "open", canvas: { artifact_id: "0123456789ab", selection: null } });
    expect(JSON.parse(bodies[4])).toEqual({ text: "asking", canvas: { artifact_id: "0123456789ab", selection: pick } });
  });

  it("posts the decision to the approval endpoint", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse('data: {"type":"done","spent_usd":0,"unknown_cost_calls":0}\n\n'));
    await api.resolveApproval("c1", "ap1", false, () => undefined);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/c1/approvals/ap1");
    expect(JSON.parse(String(init?.body))).toEqual({ approve: false });
  });

  // Stop can only cut a resumed turn if the signal reaches the fetch that streams it.
  it("forwards the abort signal on a decision and on an answer", async () => {
    const done = 'data: {"type":"done","spent_usd":0,"unknown_cost_calls":0}\n\n';
    fetchMock.mockResolvedValueOnce(sseResponse(done)).mockResolvedValueOnce(sseResponse(done));
    const decision = new AbortController();
    const answer = new AbortController();
    await api.resolveApproval("c1", "ap1", true, () => undefined, false, decision.signal);
    await api.answerApproval("c1", "q1", "có", () => undefined, answer.signal);

    const [[, decideInit], [answerUrl, answerInit]] = fetchMock.mock.calls;
    expect(decideInit?.signal).toBe(decision.signal);
    expect(answerUrl).toBe("/api/conversations/c1/approvals/q1/answer");
    expect(JSON.parse(String(answerInit?.body))).toEqual({ answer: "có" });
    expect(answerInit?.signal).toBe(answer.signal);
  });

  it("reads along with a turn under way, and says when there is none to read", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        'event: watching\r\ndata: {"type":"watching","running":true,"detail":{"id":"c1","messages":[]}}\r\n\r\n',
        'event: text_delta\r\ndata: {"type":"text_delta","text":"đang viết"}\r\n\r\n',
      ),
    );
    const seen: AgentEvent[] = [];
    const controller = new AbortController();
    expect(await api.watchTurn("c1", (e) => seen.push(e), controller.signal)).toBe(true);
    expect(seen.map((e) => e.type)).toEqual(["watching", "text_delta"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/c1/turn");
    expect(init?.method).toBeUndefined(); // a read: nothing here starts a turn
    expect(init?.signal).toBe(controller.signal);

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const none: AgentEvent[] = [];
    expect(await api.watchTurn("c1", (e) => none.push(e))).toBe(false);
    expect(none).toEqual([]);

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "not found" }, 404));
    await expect(api.watchTurn("nope", () => undefined)).rejects.toMatchObject({ status: 404 });
  });

  it("rejects a streaming call whose response is an error", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "busy" }, 409));
    await expect(api.sendMessage("c1", "x", () => undefined)).rejects.toMatchObject({
      status: 409,
      message: "busy",
      detail: "busy",
    });
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
    source.emit({ type: "artifact", artifact: { id: "a1", deleted: true }, conversation_ids: [] });
    source.onerror?.();
    expect(seen.map((p) => (p as { type: string }).type)).toEqual(["snapshot", "run", "artifact"]);
    expect(status).toEqual([true, false]);
    stop();
    expect(source.closed).toBe(true);
  });
});
