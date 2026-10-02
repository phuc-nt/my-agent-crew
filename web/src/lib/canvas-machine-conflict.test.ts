import { describe, expect, it } from "vitest";
import {
  conflictAt,
  detailAt,
  getsIn,
  lost,
  metaAt,
  openOn,
  putsIn,
  settledIn,
  summaryAt,
  typeAndPause,
} from "../test/canvas-driver";
import { statusOf } from "./canvas-machine";

const THREE = "one\ntwo\nthree";

/** A canvas in conflict: the person changed line one, the agent's v6 changed it too. */
function inConflict() {
  const canvas = openOn("one\ntwo");
  typeAndPause(canvas, "one!\ntwo");
  canvas.send(conflictAt(6, "one?\ntwo"));
  return canvas;
}

describe("a save that finds the person's own write on the server", () => {
  it("takes it as the base when a retry meets the save whose reply was lost", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "flush", ticket: 1 });

    const effects = canvas.send(conflictAt(6, "ab", "user"));

    expect(canvas.state.base).toEqual({ version: 6, content: "ab", author: "user" });
    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(effects).toContainEqual({ type: "dropDraft", text: "ab" });
    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: 6 }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("sends the rest when the person kept typing on the same line after the lost save", () => {
    const canvas = openOn("hello");
    typeAndPause(canvas, "hello w");
    canvas.send(lost);
    canvas.send({ type: "edit", text: "hello world" });

    expect(putsIn(canvas.send({ type: "saveDue", reason: "retry" }))).toEqual([
      { type: "put", content: "hello world", baseVersion: 5, hidden: false },
    ]);
    const effects = canvas.send(conflictAt(6, "hello w", "user"));

    expect(canvas.state.conflict).toBeNull();
    expect(canvas.state.text).toBe("hello world");
    expect(effects).toContainEqual({ type: "dropDraft", text: "hello w" });
    expect(putsIn(effects)).toEqual([{ type: "put", content: "hello world", baseVersion: 6, hidden: false }]);
  });

  it("does not take a version the agent wrote with the same words for its own", () => {
    const canvas = openOn("one\ntwo");
    typeAndPause(canvas, "one!\ntwo");
    canvas.send(lost);
    canvas.send({ type: "edit", text: "one!!\ntwo" });
    canvas.send({ type: "saveDue", reason: "retry" });

    canvas.send(conflictAt(6, "one!\ntwo", "agent:ming"));

    expect(statusOf(canvas.state, true)).toBe("conflict");
  });
});

describe("a save that meets someone else's newer version", () => {
  it("merges keystrokes typed while the save was out, and sends the merge", () => {
    const canvas = openOn(THREE);
    typeAndPause(canvas, "one!\ntwo\nthree");
    canvas.send({ type: "edit", text: "one!!\ntwo\nthree" });

    const effects = canvas.send(conflictAt(6, "one\ntwo\nthree?"));

    expect(canvas.state.text).toBe("one!!\ntwo\nthree?");
    expect(canvas.state.base).toEqual({ version: 6, content: "one\ntwo\nthree?", author: "agent:ming" });
    expect(canvas.state.replaced).toMatchObject({ before: "one!!\ntwo\nthree" });
    expect(putsIn(effects)).toEqual([{ type: "put", content: "one!!\ntwo\nthree?", baseVersion: 6, hidden: false }]);
  });

  it("merges again when the merged save meets yet another version, and loses nothing", () => {
    const canvas = openOn(THREE);
    typeAndPause(canvas, "one!\ntwo\nthree");
    canvas.send(conflictAt(6, "one\ntwo\nthree?"));

    expect(putsIn(canvas.send(conflictAt(7, "one\ntwo\nthree?\nfour")))).toEqual([
      { type: "put", content: "one!\ntwo\nthree?\nfour", baseVersion: 7, hidden: false },
    ]);
    canvas.send({ type: "saved", meta: metaAt(8) });

    expect(canvas.state.text).toBe("one!\ntwo\nthree?\nfour");
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("settles and drops the draft when the merge is the newer version itself", () => {
    const canvas = openOn("a\nb");
    typeAndPause(canvas, "a!\nb");
    canvas.send({ type: "flush", ticket: 1 });

    const effects = canvas.send(conflictAt(6, "a!\nb\nc"));

    expect(canvas.state.text).toBe("a!\nb\nc");
    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(effects).toContainEqual({ type: "dropDraft" });
    expect(settledIn(effects)).toEqual([{ type: "settle", ticket: 1, version: 6 }]);
    expect(putsIn(effects)).toEqual([]);
  });

  it("opens a conflict when both changed the same lines, and still lets the person type", () => {
    const canvas = inConflict();

    expect(statusOf(canvas.state, true)).toBe("conflict");
    expect(canvas.state.text).toBe("one!\ntwo");
    expect(canvas.state.conflict?.theirs).toEqual({ version: 6, content: "one?\ntwo", author: "agent:ming" });

    canvas.send({ type: "edit", text: "one!!\ntwo" });
    expect(canvas.state.text).toBe("one!!\ntwo");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "manual" }))).toEqual([]);
  });
});

describe("the person settling a conflict", () => {
  it("keeps their own text on top of the newer version", () => {
    const canvas = inConflict();
    canvas.send({ type: "edit", text: "one!!\ntwo" });

    const effects = canvas.send({ type: "keepMine" });

    expect(canvas.state.conflict).toBeNull();
    expect(canvas.state.base.version).toBe(6);
    expect(putsIn(effects)).toEqual([{ type: "put", content: "one!!\ntwo", baseVersion: 6, hidden: false }]);
  });

  it("loads the newer version, and can take their own text back until they type", () => {
    const canvas = inConflict();

    const effects = canvas.send({ type: "loadTheirs" });
    expect(canvas.state.text).toBe("one?\ntwo");
    expect(canvas.state.base.version).toBe(6);
    expect(canvas.state.conflict).toBeNull();
    expect(effects).toContainEqual({ type: "dropDraft" });
    expect(statusOf(canvas.state, true)).toBe("saved");

    canvas.send({ type: "undo" });
    expect(canvas.state.text).toBe("one!\ntwo");
    expect(canvas.state.undo).toBeNull();
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([
      { type: "put", content: "one!\ntwo", baseVersion: 6, hidden: false },
    ]);
  });

  it("forgets the text it could take back once the person types", () => {
    const canvas = inConflict();
    canvas.send({ type: "loadTheirs" });
    canvas.send({ type: "edit", text: "one?\ntwo and more" });

    canvas.send({ type: "undo" });

    expect(canvas.state.text).toBe("one?\ntwo and more");
  });

  it("shows the newest version in the conflict when another one arrives", () => {
    const canvas = inConflict();

    expect(getsIn(canvas.send({ type: "event", artifact: summaryAt(7) }))).toBe(1);
    canvas.send({ type: "read", detail: detailAt(7, "one??\ntwo", { head_author: "agent:ming" }) });

    expect(canvas.state.conflict?.theirs.version).toBe(7);
    expect(canvas.state.text).toBe("one!\ntwo");
    expect(putsIn(canvas.send({ type: "keepMine" }))).toEqual([
      { type: "put", content: "one!\ntwo", baseVersion: 7, hidden: false },
    ]);
  });
});

describe("a conflict during IME composition", () => {
  it("holds the reply until composition ends, then merges", () => {
    const canvas = openOn(THREE);
    typeAndPause(canvas, "one!\ntwo\nthree");
    canvas.send({ type: "composition", composing: true });

    expect(canvas.send(conflictAt(6, "one\ntwo\nthree?"))).toEqual([]);
    expect(canvas.state.text).toBe("one!\ntwo\nthree");
    expect(statusOf(canvas.state, true)).toBe("saving");
    expect(settledIn(canvas.send({ type: "flush", ticket: 1 }))).toEqual([]);

    expect(putsIn(canvas.send({ type: "composition", composing: false }))).toEqual([
      { type: "put", content: "one!\ntwo\nthree?", baseVersion: 6, hidden: false },
    ]);
    expect(settledIn(canvas.send({ type: "saved", meta: metaAt(7) }))).toEqual([
      { type: "settle", ticket: 1, version: 7 },
    ]);
  });

  it("reads a newer version once composition ends on text with nothing unsaved", () => {
    const canvas = openOn("a");
    canvas.send({ type: "composition", composing: true });

    expect(getsIn(canvas.send({ type: "event", artifact: summaryAt(6) }))).toBe(0);
    expect(getsIn(canvas.send({ type: "composition", composing: false }))).toBe(1);
  });

  it("does not replace the text with a read that lands during composition", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });
    canvas.send({ type: "composition", composing: true });

    canvas.send({ type: "read", detail: detailAt(6, "a!", { head_author: "agent:ming" }) });

    expect(canvas.state.text).toBe("a");
    expect(getsIn(canvas.send({ type: "composition", composing: false }))).toBe(1);
  });
});

describe("restoring an older version", () => {
  it("takes the restored version as text and base without waiting for the stream", () => {
    const canvas = openOn("v5 text");
    canvas.send({ type: "flush", ticket: 1 });

    const effects = canvas.send({ type: "restored", version: 9, content: "old text" });

    expect(canvas.state.text).toBe("old text");
    expect(canvas.state.base).toEqual({ version: 9, content: "old text", author: "user" });
    expect(effects).toContainEqual({ type: "dropDraft" });
    expect(putsIn(typeAndPause(canvas, "old text!"))).toEqual([
      { type: "put", content: "old text!", baseVersion: 9, hidden: false },
    ]);
  });

  it("ends a conflict", () => {
    const canvas = inConflict();

    canvas.send({ type: "restored", version: 7, content: "one\ntwo" });

    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(canvas.state.conflict).toBeNull();
  });

  it("ignores a restore reply older than a version it already has", () => {
    const canvas = openOn("a");
    canvas.send({ type: "event", artifact: summaryAt(10) });
    canvas.send({ type: "read", detail: detailAt(10, "a10", { head_author: "agent:ming" }) });

    const effects = canvas.send({ type: "restored", version: 9, content: "old" });

    expect(canvas.state.text).toBe("a10");
    expect(canvas.state.base.version).toBe(10);
    expect(effects).toEqual([]);
  });
});
