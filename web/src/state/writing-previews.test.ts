import { describe, expect, it } from "vitest";
import type { ToolCall } from "../api/types";
import { applyDelta, bindCalls, type ToolCallDelta, type WritingPreview } from "./writing-previews";

const delta = (partial: Partial<ToolCallDelta> = {}): ToolCallDelta => ({
  type: "tool_call_delta",
  index: 0,
  name: "artifact_create",
  chunk: "",
  attempt: 0,
  ...partial,
});

/** Every event in turn, from no preview at all. */
function feed(events: ToolCallDelta[], from: { previews: WritingPreview[]; seq: number } = { previews: [], seq: 0 }) {
  return events.reduce((state, event) => applyDelta(state.previews, state.seq, event), from);
}

const call = (id: string, name = "artifact_create"): ToolCall => ({ id, name, arguments: {} });

describe("the pieces of a canvas the model is writing", () => {
  it("start a preview at the first piece and add to it at each one after", () => {
    const first = feed([delta({ chunk: '{"ti' })]);
    expect(first).toEqual({
      previews: [{ key: 1, index: 0, name: "artifact_create", text: '{"ti', attempt: 0, callId: null, updates: 1 }],
      seq: 1,
    });

    const second = feed([delta({ chunk: 'tle":"Kế' }), delta({ chunk: ' hoạch"' })], first);
    expect(second).toEqual({
      previews: [
        { key: 1, index: 0, name: "artifact_create", text: '{"title":"Kế hoạch"', attempt: 0, callId: null, updates: 3 },
      ],
      seq: 1,
    });
  });

  it("keep two calls of one answer apart by where they stand in it", () => {
    const { previews, seq } = feed([
      delta({ index: 0, chunk: "a" }),
      delta({ index: 1, name: "artifact_rewrite", chunk: "x" }),
      delta({ index: 0, chunk: "b" }),
      delta({ index: 1, name: "artifact_rewrite", chunk: "y" }),
    ]);
    expect(previews.map((p) => [p.key, p.index, p.name, p.text, p.updates])).toEqual([
      [1, 0, "artifact_create", "ab", 2],
      [2, 1, "artifact_rewrite", "xy", 2],
    ]);
    expect(seq).toBe(2);
  });

  it("take the name a later piece gives the call", () => {
    const { previews } = feed([delta({ chunk: "a" }), delta({ name: "artifact_rewrite", chunk: "b" })]);
    expect(previews).toMatchObject([{ key: 1, name: "artifact_rewrite", text: "ab", updates: 2 }]);
  });

  it("change nothing they were given: every step is a new list", () => {
    const first = feed([delta({ chunk: "a" })]);
    const frozen = structuredClone(first);
    const second = feed([delta({ chunk: "b" })], first);
    expect(first).toEqual(frozen);
    expect(second.previews).not.toBe(first.previews);
    expect(second.previews[0]).not.toBe(first.previews[0]);
  });
});

describe("an answer the model starts over", () => {
  it("drops what the try before had written, and the event that says so makes nothing", () => {
    const written = feed([delta({ chunk: "a" }), delta({ index: 1, chunk: "b" })]);
    const cancelled = feed([delta({ name: "", attempt: 1 })], written);
    expect(cancelled).toEqual({ previews: [], seq: 2 });
  });

  it("builds the next try from nothing, under a key of its own", () => {
    const written = feed([delta({ chunk: "cũ" }), delta({ chunk: " hơn" })]);
    const again = feed([delta({ name: "", attempt: 1 }), delta({ chunk: "mới", attempt: 1 })], written);
    expect(again).toEqual({
      previews: [{ key: 2, index: 0, name: "artifact_create", text: "mới", attempt: 1, callId: null, updates: 1 }],
      seq: 2,
    });
  });

  it("drops the try before even when no event came to say it had ended", () => {
    const written = feed([delta({ chunk: "cũ" })]);
    const again = feed([delta({ chunk: "mới", attempt: 1 })], written);
    expect(again.previews).toMatchObject([{ key: 2, text: "mới", attempt: 1, updates: 1 }]);
  });

  it("drops what a try with a higher number had written: another try is another answer, whichever way the count went", () => {
    const written = feed([delta({ chunk: "cũ", attempt: 2 })]);
    const again = feed([delta({ chunk: "mới", attempt: 0 })], written);
    expect(again.previews).toMatchObject([{ key: 2, text: "mới", attempt: 0, updates: 1 }]);
  });

  it("makes nothing of an event without a name while nothing is being written", () => {
    expect(feed([delta({ name: "", chunk: "rác" })])).toEqual({ previews: [], seq: 0 });
  });

  it("leaves the previews of this try alone when an event without a name belongs to it", () => {
    const written = feed([delta({ chunk: "a" })]);
    const after = feed([delta({ name: "", chunk: "rác" })], written);
    expect(after).toEqual(written);
  });
});

describe("the answer a step ends with", () => {
  it("gives each preview the call that stands where it stood, when that call is the same tool", () => {
    const { previews } = feed([delta({ index: 0, chunk: "a" }), delta({ index: 1, name: "artifact_rewrite", chunk: "b" })]);
    const bound = bindCalls(previews, [call("w1"), call("w2", "artifact_rewrite")]);
    expect(bound.map((p) => [p.key, p.callId, p.text])).toEqual([
      [1, "w1", "a"],
      [2, "w2", "b"],
    ]);
  });

  it("drops a preview whose call turned out to be another tool", () => {
    const { previews } = feed([delta({ chunk: '{"content":"bí mật' })]);
    expect(bindCalls(previews, [call("w1", "workspace_write")])).toEqual([]);
    // Another tool that writes a canvas is another tool all the same.
    expect(bindCalls(previews, [call("w1", "artifact_rewrite")])).toEqual([]);
  });

  it("drops a preview the answer has no call for at its place", () => {
    const { previews } = feed([delta({ index: 1, chunk: "a" })]);
    expect(bindCalls(previews, [call("w1")])).toEqual([]);
    expect(bindCalls(previews, [])).toEqual([]);
  });

  it("drops the previews of the step before: their calls have been answered", () => {
    const first = feed([delta({ chunk: "a" })]);
    const bound = bindCalls(first.previews, [call("w1")]);
    expect(bound).toMatchObject([{ key: 1, callId: "w1" }]);

    expect(bindCalls(bound, [call("w9")])).toEqual([]);
  });
});

describe("the step after one that wrote a canvas", () => {
  it("starts a preview of its own beside the one already given its call, though both stood first and tried once", () => {
    const first = feed([delta({ chunk: "một" })]);
    const bound = { previews: bindCalls(first.previews, [call("w1")]), seq: first.seq };

    // A step counts its tries from nothing again: the try alone does not tell two steps apart.
    const next = feed([delta({ chunk: "hai" })], bound);
    expect(next.previews.map((p) => [p.key, p.callId, p.text, p.updates])).toEqual([
      [1, "w1", "một", 1],
      [2, null, "hai", 1],
    ]);

    const more = feed([delta({ chunk: " ba" })], next);
    expect(more.previews.map((p) => [p.key, p.text])).toEqual([
      [1, "một"],
      [2, "hai ba"],
    ]);
  });

  it("goes on adding to its own preview when the one given its call was written in another try", () => {
    const first = feed([delta({ chunk: "một", attempt: 1 })]);
    const bound = { previews: bindCalls(first.previews, [call("w1")]), seq: first.seq };

    const next = feed([delta({ chunk: "hai" }), delta({ chunk: " ba" })], bound);

    expect(next.previews.map((p) => [p.key, p.callId, p.text, p.updates])).toEqual([
      [1, "w1", "một", 1],
      [2, null, "hai ba", 2],
    ]);
  });

  it("keeps the preview already given its call when the new step starts over", () => {
    const first = feed([delta({ chunk: "một" })]);
    const bound = { previews: bindCalls(first.previews, [call("w1")]), seq: first.seq };
    const next = feed([delta({ chunk: "hai" }), delta({ name: "", attempt: 1 })], bound);
    expect(next.previews.map((p) => [p.key, p.callId])).toEqual([[1, "w1"]]);
  });
});
