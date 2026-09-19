import { describe, expect, it } from "vitest";
import { SseParser, readSse } from "./sse";
import type { AgentEvent } from "./types";

const delta = (text: string) => `event: text_delta\ndata: ${JSON.stringify({ type: "text_delta", text })}\n\n`;

describe("SseParser", () => {
  it("emits one event per blank-line separated block", () => {
    const parser = new SseParser();
    const events = parser.push(delta("a") + delta("b"));
    expect(events).toEqual([
      { type: "text_delta", text: "a" },
      { type: "text_delta", text: "b" },
    ]);
  });

  it("buffers partial blocks across chunk boundaries", () => {
    const parser = new SseParser();
    const whole = delta("hello");
    const first = parser.push(whole.slice(0, 20));
    const second = parser.push(whole.slice(20));
    expect(first).toEqual([]);
    expect(second).toEqual([{ type: "text_delta", text: "hello" }]);
  });

  it("accepts CRLF line endings as sent by sse-starlette", () => {
    const parser = new SseParser();
    const crlf = delta("x").replace(/\n/g, "\r\n");
    expect(parser.push(crlf)).toEqual([{ type: "text_delta", text: "x" }]);
  });

  it("joins multi-line data fields and ignores comments and non-data lines", () => {
    const parser = new SseParser();
    const block = `: keep-alive\nevent: done\nid: 3\ndata: {"type":"done",\ndata: "spent_usd":0.1,"unknown_cost_calls":0}\n\n`;
    expect(parser.push(block)).toEqual([{ type: "done", spent_usd: 0.1, unknown_cost_calls: 0 }]);
  });

  it("drops malformed JSON and payloads without a type", () => {
    const parser = new SseParser();
    expect(parser.push("data: {not json}\n\n")).toEqual([]);
    expect(parser.push('data: {"text":"no type"}\n\n')).toEqual([]);
    expect(parser.push("data: 42\n\n")).toEqual([]);
  });

  it("flush returns the trailing block when the stream ends without a blank line", () => {
    const parser = new SseParser();
    expect(parser.push('data: {"type":"error","message":"boom"}')).toEqual([]);
    expect(parser.flush()).toEqual([{ type: "error", message: "boom" }]);
    expect(parser.flush()).toEqual([]);
  });
});

describe("readSse", () => {
  it("decodes a byte stream including multi-byte characters split across chunks", async () => {
    const text = delta("xin chào");
    const bytes = new TextEncoder().encode(text);
    const split = bytes.indexOf(0xc3) + 1; // cut inside the "à" sequence
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split));
        controller.close();
      },
    });
    const seen: AgentEvent[] = [];
    await readSse(body, (e) => seen.push(e));
    expect(seen).toEqual([{ type: "text_delta", text: "xin chào" }]);
  });
});
