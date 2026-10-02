import { describe, expect, it } from "vitest";
import { conflictAt, drive, lost, metaAt, openOn, putsIn, settledIn, typeAndPause } from "../test/canvas-driver";
import { type CanvasInput, SIZE_CAP, openState } from "./canvas-machine";

const refused = (status: number): CanvasInput => ({ type: "saveFailed", status, conflict: null, full: null });
const flush = (ticket = 1): CanvasInput => ({ type: "flush", ticket });

describe("flushing a canvas", () => {
  it("answers at once with the base version when nothing is unsaved", () => {
    const canvas = openOn("hello");

    const effects = canvas.send(flush());

    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: 5 }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("saves unsaved text at once and answers with the version that holds it", () => {
    const canvas = openOn("hello");
    canvas.send({ type: "edit", text: "hello!" });

    const effects = canvas.send(flush());
    expect(putsIn(effects)).toEqual([{ type: "put", content: "hello!", baseVersion: 5, hidden: false }]);
    expect(settledIn(effects)).toEqual([]);

    expect(settledIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "settle", ticket: 1, version: 6 },
    ]);
  });

  it("waits for the save already in flight when it carries the same text", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    expect(putsIn(canvas.send(flush()))).toEqual([]);

    const effects = canvas.send({ type: "saved", meta: metaAt(6) });
    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: 6 }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("does not wait for keystrokes typed after it was called", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });
    canvas.send(flush());
    canvas.send({ type: "edit", text: "abc" });

    const effects = canvas.send({ type: "saved", meta: metaAt(6) });

    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: 6 }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("waits past a save in flight that carries older text, for the save that holds its own", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send({ type: "edit", text: "abc" });
    canvas.send(flush());

    const first = canvas.send({ type: "saved", meta: metaAt(6) });
    expect(settledIn(first)).toEqual([]);
    expect(putsIn(first)).toEqual([{ type: "put", content: "abc", baseVersion: 6, hidden: false }]);

    expect(settledIn(canvas.send({ type: "saved", meta: metaAt(7) }))).toEqual([
      { type: "settle", ticket: 1, version: 7 },
    ]);
  });

  it("answers every caller waiting on the same save", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });
    canvas.send(flush(1));
    canvas.send(flush(2));

    expect(settledIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "settle", ticket: 1, version: 6 },
      { type: "settle", ticket: 2, version: 6 },
    ]);
  });

  it("answers null when the save runs into a conflict", () => {
    const canvas = openOn("one\ntwo");
    canvas.send({ type: "edit", text: "one!\ntwo" });
    canvas.send(flush());

    expect(settledIn(canvas.send(conflictAt(6, "one?\ntwo")))).toEqual([
      { type: "settle", ticket: 1, version: null },
    ]);
  });

  it("answers null when the canvas is deleted while it waits", () => {
    const deleted: CanvasInput = { type: "event", artifact: { id: "a1", deleted: true } };
    for (const ending of [deleted, refused(404)]) {
      const canvas = openOn("a");
      canvas.send({ type: "edit", text: "ab" });
      canvas.send(flush());

      expect(settledIn(canvas.send(ending))).toEqual([{ type: "settle", ticket: 1, version: null }]);
    }
  });

  it("answers null when the server refuses the save", () => {
    for (const status of [413, 507, 422]) {
      const canvas = openOn("a");
      canvas.send({ type: "edit", text: "ab" });
      canvas.send(flush());

      expect(settledIn(canvas.send(refused(status)))).toEqual([{ type: "settle", ticket: 1, version: null }]);
    }
  });

  it("answers null when the first save is lost, and saves at once when called again", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });
    canvas.send(flush(1));

    expect(settledIn(canvas.send(lost))).toEqual([{ type: "settle", ticket: 1, version: null }]);

    expect(putsIn(canvas.send(flush(2)))).toEqual([{ type: "put", content: "ab", baseVersion: 5, hidden: false }]);
    expect(settledIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "settle", ticket: 2, version: 6 },
    ]);
  });

  it("answers null at once for text too large to send", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "x".repeat(SIZE_CAP + 1) });

    const effects = canvas.send(flush());

    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: null }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("answers null at once while saving is stopped, in conflict or deleted", () => {
    const stopped = openOn("a");
    typeAndPause(stopped, "ab");
    stopped.send(refused(422));

    const conflicted = openOn("one\ntwo");
    typeAndPause(conflicted, "one!\ntwo");
    conflicted.send(conflictAt(6, "one?\ntwo"));

    const gone = openOn("a");
    gone.send({ type: "event", artifact: { id: "a1", deleted: true } });

    for (const canvas of [stopped, conflicted, gone]) {
      const effects = canvas.send(flush());
      expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: null }]);
      expect(putsIn(effects)).toEqual([]);
    }
  });

  it("answers 0 before the canvas has loaded, with nothing typed to keep", () => {
    const canvas = drive(openState("a1", null));

    expect(settledIn(canvas.send(flush()))).toEqual([{ type: "settle", ticket: 1, version: 0 }]);
  });
});
