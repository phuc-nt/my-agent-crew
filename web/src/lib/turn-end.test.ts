import { describe, expect, it } from "vitest";
import type { AgentEvent, ConversationDetail } from "../api/types";
import { endsTurn, turnOver } from "./turn-end";

const detail = {} as ConversationDetail;

describe("the last word of a turn on a stream that reads it", () => {
  it.each<[string, AgentEvent]>([
    ["the turn finished", { type: "done", spent_usd: 0, unknown_cost_calls: 0 }],
    ["the turn gave up", { type: "halted", reason: "max_steps", spent_usd: 0 }],
    ["the turn broke", { type: "error", message: "model down" }],
    [
      "the turn stopped to wait on the person",
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc1", name: "write_file", arguments: {}, reason: "", expires_at: "" },
    ],
  ])("is said when %s", (_name, event) => {
    expect(endsTurn(event)).toBe(true);
  });

  it.each<[string, AgentEvent]>([
    ["a piece of the answer", { type: "text_delta", text: "nửa câu" }],
    ["a thought", { type: "thinking" }],
    [
      "an answer stored, which a tool call may follow",
      { type: "assistant_message", message_id: "m1", content: "xong", tool_calls: [], provider: null, model: null, cost_usd: null },
    ],
    ["a tool called", { type: "tool_call", tool_call_id: "tc1", name: "write_file", arguments: {} }],
    ["a tool that answered", { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "" }],
    ["a tool that failed", { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: false, output: "no" }],
    ["a message put in line", { type: "queued", item_id: 1, kind: "follow_up", position: 1 }],
    ["a turn found going", { type: "watching", running: true, detail }],
  ])("is not said by %s", (_name, event) => {
    expect(endsTurn(event)).toBe(false);
  });

  it("is not said by the server finding nothing going: a turn cut off is spoken of the same way", () => {
    // The word stands in for events the reader was not given. A server on its way out says it
    // of a turn the next server carries on, so it cannot count as that turn's end.
    expect(endsTurn({ type: "watching", running: false, detail })).toBe(false);
  });
});

describe("a turn that is over for good", () => {
  it.each<[string, AgentEvent]>([
    ["finished", { type: "done", spent_usd: 0, unknown_cost_calls: 0 }],
    ["gave up", { type: "halted", reason: "max_steps", spent_usd: 0 }],
    ["broke", { type: "error", message: "model down" }],
  ])("is one that %s", (_name, event) => {
    expect(turnOver(event)).toBe(true);
  });

  it.each<[string, AgentEvent]>([
    [
      "one stopped to wait on the person, which an answer takes up again",
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc1", name: "write_file", arguments: {}, reason: "", expires_at: "" },
    ],
    ["one found going", { type: "watching", running: true, detail }],
    ["one the server finds nothing of, which may have been cut off", { type: "watching", running: false, detail }],
    ["one still writing", { type: "text_delta", text: "nửa câu" }],
    ["one whose message was put in line", { type: "queued", item_id: 1, kind: "follow_up", position: 1 }],
  ])("is not %s", (_name, event) => {
    expect(turnOver(event)).toBe(false);
  });
});
