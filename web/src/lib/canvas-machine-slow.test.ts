import { describe, expect, it } from "vitest";
import { conflictAt, lost, metaAt, openOn, putsIn, settledIn, typeAndPause } from "../test/canvas-driver";
import { type CanvasInput, statusOf } from "./canvas-machine";

/** The deadline of the save in flight came with no reply. */
const timedOut: CanvasInput = { type: "saveTimedOut" };

const retry: CanvasInput = { type: "saveDue", reason: "retry" };

describe("a save still unanswered at its deadline", () => {
  it("is retried after two seconds, its text kept as maybe on the server", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    const effects = canvas.send(timedOut);

    expect(effects).toContainEqual({ type: "retryIn", ms: 2000 });
    expect(putsIn(effects)).toEqual([]);
    expect(canvas.state.saving).toBeNull();
    expect(canvas.state.unsure).toEqual(["ab"]);
    expect(canvas.state.failures).toBe(1);
  });

  it("says the network is slow while the device is online, and offline when it is not", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(timedOut);

    expect(statusOf(canvas.state, true)).toBe("slow");
    expect(statusOf(canvas.state, false)).toBe("offline");
  });

  it("sends the text again when the retry falls due, and goes on saying the network is slow until one lands", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(timedOut);

    expect(putsIn(canvas.send(retry))).toEqual([{ type: "put", content: "ab", baseVersion: 5, hidden: false }]);
    expect(canvas.state.saving).toEqual(expect.objectContaining({ content: "ab", baseVersion: 5 }));
    expect(statusOf(canvas.state, true)).toBe("slow");
  });

  it("skips timer and blur saves while the retry waits, as it does for a lost one", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(timedOut);

    expect(putsIn(typeAndPause(canvas, "abc"))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "blur" }))).toEqual([]);
    expect(putsIn(canvas.send(retry))).toEqual([{ type: "put", content: "abc", baseVersion: 5, hidden: false }]);
  });

  it("waits longer after each one in a row, as for lost saves", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    const delays: number[] = [];

    for (let n = 0; n < 4; n++) {
      for (const effect of canvas.send(timedOut)) if (effect.type === "retryIn") delays.push(effect.ms);
      canvas.send(retry);
    }

    expect(delays).toEqual([2000, 5000, 15000, 30000]);
  });

  it("is told apart from a lost save by the status of the next one", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(timedOut);
    canvas.send(retry);
    canvas.send(lost);
    expect(statusOf(canvas.state, true)).toBe("serverDown");
    expect(canvas.state.slow).toBe(false);

    canvas.send(retry);
    canvas.send(timedOut);
    expect(statusOf(canvas.state, true)).toBe("slow");
  });

  it("does not leave the network slow once a save goes through", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(timedOut);
    canvas.send(retry);

    canvas.send({ type: "saved", meta: metaAt(6) });

    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("answers a waiting flush with null, as a lost save does", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });
    canvas.send({ type: "flush", ticket: 1 });

    const effects = canvas.send(timedOut);

    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: null }]);
  });

  it("counts the text it carried as the person's own when the retry meets it on the server", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(timedOut);
    canvas.send({ type: "edit", text: "abc" });
    canvas.send(retry);

    // The first save had landed as version 6; the retry named version 5 as its base.
    const effects = canvas.send(conflictAt(6, "ab", "user"));

    expect(canvas.state.conflict).toBeNull();
    expect(putsIn(effects)).toEqual([{ type: "put", content: "abc", baseVersion: 6, hidden: false }]);
  });

  it("settles as saved when the retry finds the same text on the server", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(timedOut);
    canvas.send(retry);

    canvas.send(conflictAt(6, "ab", "user"));

    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(canvas.state.base).toEqual({ version: 6, content: "ab", author: "user" });
    expect(canvas.state.unsure).toEqual([]);
  });

  it("is ignored when the canvas was deleted while the save was out: no retry is ever set", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send({ type: "event", artifact: { id: "a1", deleted: true } });
    const gone = canvas.state;

    expect(canvas.send(timedOut)).toEqual([]);

    expect(canvas.state).toEqual(gone);
    expect(canvas.state.failures).toBe(0);
    expect(canvas.state.retrying).toBe(false);
    expect(statusOf(canvas.state, true)).toBe("gone");
  });

  it("is ignored when no save is out", () => {
    const canvas = openOn("a");
    const before = canvas.state;

    expect(canvas.send(timedOut)).toEqual([]);
    expect(canvas.state).toEqual(before);

    typeAndPause(canvas, "ab");
    canvas.send({ type: "saved", meta: metaAt(6) });
    const after = canvas.state;

    expect(canvas.send(timedOut)).toEqual([]);
    expect(canvas.state).toEqual(after);
    expect(statusOf(canvas.state, true)).toBe("saved");
  });
});
