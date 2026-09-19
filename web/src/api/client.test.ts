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
