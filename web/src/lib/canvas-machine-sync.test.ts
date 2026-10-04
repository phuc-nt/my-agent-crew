import { describe, expect, it } from "vitest";
import { type CanvasDraft, textKey } from "./canvas-draft";
import {
  type Driver,
  conflictAt,
  detailAt,
  drive,
  getsIn,
  lost,
  metaAt,
  openOn,
  putsIn,
  summaryAt,
  typeAndPause,
} from "../test/canvas-driver";
import { type CanvasEffect, type CanvasInput, openState, statusOf } from "./canvas-machine";

const event = (version: number, title = "Ghi chú"): CanvasInput => ({
  type: "event",
  artifact: summaryAt(version, { title }),
});
const deleted: CanvasInput = { type: "event", artifact: { id: "a1", deleted: true } };

function draftOf(base_version: number, base: string, text: string, sent: string[] = []): CanvasDraft {
  return { artifact_id: "a1", base_version, base, text, saved_at: 0, sent: sent.map(textKey) };
}

/** Sends each input in turn and returns every effect they caused. */
function sendAll(canvas: Driver, inputs: CanvasInput[]): CanvasEffect[] {
  return inputs.flatMap((input) => canvas.send(input));
}

describe("a canvas hearing about versions from the stream", () => {
  it("reads nothing when its own save's event comes before or after the reply", () => {
    const early = openOn("a");
    const late = openOn("a");

    const effects = [
      ...sendAll(early, [{ type: "edit", text: "ab" }, { type: "saveDue", reason: "timer" }, event(6)]),
      ...early.send({ type: "saved", meta: metaAt(6) }),
      ...sendAll(late, [{ type: "edit", text: "ab" }, { type: "saveDue", reason: "timer" }]),
      ...late.send({ type: "saved", meta: metaAt(6) }),
      ...late.send(event(6)),
    ];

    expect(getsIn(effects)).toBe(0);
    expect(statusOf(early.state, true)).toBe("saved");
    expect(statusOf(late.state, true)).toBe("saved");
  });

  it("does not call text saved when the agent wrote a newer version during the save", () => {
    const canvas = openOn("ab");
    typeAndPause(canvas, "ab!");
    canvas.send(event(7));

    const effects = canvas.send({ type: "saved", meta: metaAt(6) });
    expect(statusOf(canvas.state, true)).toBe("newer");
    expect(getsIn(effects)).toBe(1);

    canvas.send({ type: "read", detail: detailAt(7, "ab! and more", { head_author: "agent:ming" }) });
    expect(canvas.state.text).toBe("ab! and more");
    expect(canvas.state.base).toEqual({ version: 7, content: "ab! and more", author: "agent:ming" });
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("saves again right after its save lands when a newer version came and the person typed", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send({ type: "edit", text: "abc" });
    canvas.send(event(7));

    expect(putsIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "put", content: "abc", baseVersion: 6, hidden: false },
    ]);
  });

  it("reads a newer version at once when nothing is unsaved", () => {
    const canvas = openOn("a");

    expect(getsIn(canvas.send(event(6)))).toBe(1);
    canvas.send({ type: "read", detail: detailAt(6, "a and b", { head_author: "agent:ming" }) });

    expect(canvas.state.text).toBe("a and b");
    expect(canvas.state.replaced).toMatchObject({ before: "a" });
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("ignores an event for a version it already has, and one for another canvas", () => {
    const canvas = openOn("a");

    expect(sendAll(canvas, [event(5), event(4), { type: "event", artifact: summaryAt(9, { id: "a2" }) }])).toEqual(
      [],
    );
    expect(canvas.state.seen).toBe(5);
  });

  it("only marks a newer version while the person has unsaved text", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });

    expect(canvas.send(event(6))).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("newer");
  });

  it("keeps the title a rename brought while a save was in flight", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(event(5, "Tên mới"));

    canvas.send({ type: "saved", meta: metaAt(6) });

    expect(canvas.state.summary?.title).toBe("Tên mới");
  });

  it("does not bring back an older title from an event that arrives late", () => {
    const canvas = openOn("a");
    canvas.send(event(7, "Tên mới"));
    canvas.send({ type: "read", detail: detailAt(7, "a", { title: "Tên mới" }) });

    canvas.send(event(6, "Tên cũ"));

    expect(canvas.state.summary?.title).toBe("Tên mới");
  });

  it("takes the title of the person's own rename", () => {
    const canvas = openOn("a");

    canvas.send({ type: "renamed", summary: summaryAt(5, { title: "Đổi tên" }) });

    expect(canvas.state.summary?.title).toBe("Đổi tên");
  });

  it("stays deleted when a save in flight lands after the delete", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(deleted);

    expect(canvas.send({ type: "saved", meta: metaAt(6) })).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("gone");
    expect(canvas.state.text).toBe("ab");
  });
});

describe("a canvas reading the newest version", () => {
  it("keeps what the person typed while a read was out, and merges it on the next save", () => {
    const canvas = openOn("one\ntwo\nthree");
    canvas.send(event(6));
    canvas.send({ type: "edit", text: "one\ntwo\nthree!" });

    canvas.send({ type: "read", detail: detailAt(6, "one!\ntwo\nthree", { head_author: "agent:ming" }) });
    expect(canvas.state.text).toBe("one\ntwo\nthree!");
    expect(statusOf(canvas.state, true)).toBe("newer");

    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([
      { type: "put", content: "one\ntwo\nthree!", baseVersion: 5, hidden: false },
    ]);
    expect(putsIn(canvas.send(conflictAt(6, "one!\ntwo\nthree")))).toEqual([
      { type: "put", content: "one!\ntwo\nthree!", baseVersion: 6, hidden: false },
    ]);
  });

  it("reads again when a pause in typing finds the text back to its base", () => {
    const canvas = openOn("a");
    canvas.send(event(6));
    canvas.send({ type: "edit", text: "ab" });
    canvas.send({ type: "edit", text: "a" });
    canvas.send({ type: "read", detail: detailAt(6, "a!", { head_author: "agent:ming" }) });
    expect(canvas.state.text).toBe("a");

    expect(getsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toBe(1);
    canvas.send({ type: "read", detail: detailAt(6, "a!", { head_author: "agent:ming" }) });

    expect(canvas.state.text).toBe("a!");
  });

  it("puts off a read asked for during a save, and never sends older text after it", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    expect(getsIn(canvas.send({ type: "resync" }))).toBe(0);
    expect(getsIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toBe(1);

    const effects = canvas.send({ type: "read", detail: detailAt(5, "a") });
    expect(putsIn(effects)).toEqual([]);
    expect(canvas.state.text).toBe("ab");
    expect(canvas.state.base.version).toBe(6);
  });

  it("follows two versions in a row to the newest with one read each", () => {
    const canvas = openOn("a");

    const effects = [
      ...canvas.send(event(6)),
      ...canvas.send(event(7)),
      ...canvas.send({ type: "read", detail: detailAt(6, "a6", { head_author: "agent:ming" }) }),
      ...canvas.send({ type: "read", detail: detailAt(7, "a7", { head_author: "agent:ming" }) }),
    ];

    expect(getsIn(effects)).toBe(2);
    expect(canvas.state.text).toBe("a7");
    expect(canvas.state.base.version).toBe(7);
  });

  it("reads once for a version it hears of twice while the read is out", () => {
    const canvas = openOn("a");

    const effects = [
      ...canvas.send(event(6)),
      ...canvas.send(event(6)),
      ...canvas.send({ type: "read", detail: detailAt(6, "a6", { head_author: "agent:ming" }) }),
    ];

    expect(getsIn(effects)).toBe(1);
    expect(canvas.state.text).toBe("a6");
    expect(canvas.state.base.version).toBe(6);
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("reads again for a version it hears of during a read that was asked for before it", () => {
    const canvas = openOn("a");

    const effects = [
      ...canvas.send({ type: "resync" }),
      ...sendAll(canvas, [event(6), event(6)]),
      ...canvas.send({ type: "read", detail: detailAt(5, "a") }),
      ...canvas.send({ type: "read", detail: detailAt(6, "a6", { head_author: "agent:ming" }) }),
    ];

    expect(getsIn(effects)).toBe(2);
    expect(canvas.state.text).toBe("a6");
    expect(canvas.state.base.version).toBe(6);
  });

  it("reads once for a version heard of twice across a conflict", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "mine");
    canvas.send(conflictAt(6, "theirs"));

    const effects = [
      ...sendAll(canvas, [event(7), event(7)]),
      ...canvas.send({ type: "read", detail: detailAt(7, "theirs too", { head_author: "agent:ming" }) }),
    ];

    expect(getsIn(effects)).toBe(1);
    expect(canvas.state.conflict?.theirs).toMatchObject({ version: 7, content: "theirs too" });
  });

  it("asks for one more read when the stream comes back during a read", () => {
    const canvas = openOn("a");
    canvas.send(event(6));

    expect(getsIn(canvas.send({ type: "resync" }))).toBe(0);
    expect(getsIn(canvas.send({ type: "read", detail: detailAt(6, "a6") }))).toBe(1);
  });

  it("reads when the stream comes back, and does nothing while loading or deleted", () => {
    expect(getsIn(openOn("a").send({ type: "resync" }))).toBe(1);
    expect(drive(openState("a1", null)).send({ type: "resync" })).toEqual([]);

    const gone = openOn("a");
    gone.send(deleted);
    expect(gone.send({ type: "resync" })).toEqual([]);
  });

  it("takes a version that holds a save whose reply was lost as its base", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "edit", text: "abc" });

    const effects = canvas.send({ type: "read", detail: detailAt(6, "ab") });

    expect(canvas.state.base).toEqual({ version: 6, content: "ab", author: "user" });
    expect(canvas.state.unsure).toEqual([]);
    expect(canvas.state.text).toBe("abc");
    expect(putsIn(effects)).toEqual([{ type: "put", content: "abc", baseVersion: 6, hidden: false }]);
  });

  it("drops the draft of a lost save a read shows landed, by the text that landed", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "edit", text: "abc" });

    const effects = canvas.send({ type: "read", detail: detailAt(6, "ab") });

    expect(effects.filter((effect) => effect.type === "dropDraft")).toEqual([{ type: "dropDraft", text: "ab" }]);
  });

  it("calls the text saved once a read shows the lost save landed", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });
    typeAndPause(canvas, "ab");
    canvas.send(lost);

    expect(putsIn(canvas.send({ type: "read", detail: detailAt(6, "ab") }))).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "retry" }))).toEqual([]);
  });

  it("does not send past a stop when a read shows a lost save landed", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "saveDue", reason: "retry" });
    canvas.send({ type: "saveFailed", status: 507, conflict: null, full: { used: 1, cap: 1, largest: [] } });
    canvas.send({ type: "edit", text: "abc" });

    expect(putsIn(canvas.send({ type: "read", detail: detailAt(6, "ab") }))).toEqual([]);
    expect(canvas.state.base.version).toBe(6);
    expect(statusOf(canvas.state, true)).toBe("full");
  });

  it("leaves the text alone when a read brings no newer version", () => {
    const canvas = openOn("a");
    canvas.send({ type: "resync" });

    canvas.send({ type: "read", detail: detailAt(5, "a") });

    expect(canvas.state.replaced).toBeNull();
    expect(statusOf(canvas.state, true)).toBe("saved");
  });
});

describe("a canvas whose read failed", () => {
  it("says it could not load, and loads again when the stream comes back", () => {
    const canvas = drive(openState("a1", null));

    canvas.send({ type: "readFailed", status: 500 });
    expect(statusOf(canvas.state, true)).toBe("loadFailed");

    expect(getsIn(canvas.send({ type: "resync" }))).toBe(1);
    expect(statusOf(canvas.state, true)).toBe("loading");
    canvas.send({ type: "read", detail: detailAt(5, "hello") });
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("opens a canvas deleted before it loaded with the draft kept on this device", () => {
    const withDraft = drive(openState("a1", draftOf(3, "a", "a and mine")));
    const without = drive(openState("a1", null));

    withDraft.send({ type: "readFailed", status: 404 });
    without.send({ type: "readFailed", status: 404 });

    expect(statusOf(withDraft.state, true)).toBe("gone");
    expect(withDraft.state.text).toBe("a and mine");
    expect(without.state.text).toBe("");
  });

  it("keeps the text when a later read fails, and goes deleted on a 404", () => {
    const canvas = openOn("a");
    canvas.send(event(6));
    canvas.send({ type: "readFailed", status: 500 });
    expect(canvas.state.reading).toBeNull();
    expect(canvas.state.text).toBe("a");

    expect(getsIn(canvas.send({ type: "resync" }))).toBe(1);
    canvas.send({ type: "readFailed", status: 404 });
    expect(statusOf(canvas.state, true)).toBe("gone");
  });
});

describe("opening a canvas with a draft on this device", () => {
  it("drops a draft that holds the newest version's text", () => {
    const canvas = drive(openState("a1", draftOf(3, "a", "hello")));

    const effects = canvas.send({ type: "read", detail: detailAt(5, "hello") });

    expect(effects).toContainEqual({ type: "dropDraft" });
    expect(canvas.state.opened).toBe("fresh");
  });

  it("brings back a draft written on the newest version as unsaved text", () => {
    const canvas = drive(openState("a1", draftOf(5, "hello", "hello there")));
    canvas.send({ type: "read", detail: detailAt(5, "hello") });

    expect(canvas.state.text).toBe("hello there");
    expect(canvas.state.opened).toBe("draft");
    expect(statusOf(canvas.state, true)).toBe("unsaved");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([
      { type: "put", content: "hello there", baseVersion: 5, hidden: false },
    ]);
  });

  it("merges a draft written on an older version into the newest one", () => {
    const canvas = drive(openState("a1", draftOf(3, "one\ntwo\nthree", "one!\ntwo\nthree")));

    canvas.send({ type: "read", detail: detailAt(5, "one\ntwo\nthree?") });

    expect(canvas.state.text).toBe("one!\ntwo\nthree?");
    expect(canvas.state.base.version).toBe(5);
    expect(canvas.state.opened).toBe("merged");
  });

  it("opens fresh when the merged draft is the newest version already", () => {
    const canvas = drive(openState("a1", draftOf(3, "one\ntwo", "one!\ntwo")));

    const effects = canvas.send({ type: "read", detail: detailAt(5, "one!\ntwo\nthree") });

    expect(effects).toContainEqual({ type: "dropDraft" });
    expect(canvas.state.opened).toBe("fresh");
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("opens a conflict when the draft and the newest version changed the same lines", () => {
    const canvas = drive(openState("a1", draftOf(3, "one\ntwo", "one!\ntwo")));

    canvas.send({ type: "read", detail: detailAt(5, "one?\ntwo", { head_author: "agent:ming" }) });

    expect(canvas.state.opened).toBe("conflict");
    expect(canvas.state.text).toBe("one!\ntwo");
    expect(canvas.state.base).toEqual({ version: 3, content: "one\ntwo", author: "user" });
    expect(canvas.state.conflict?.theirs).toEqual({ version: 5, content: "one?\ntwo", author: "agent:ming" });
    expect(statusOf(canvas.state, true)).toBe("conflict");
  });

  it("takes the person's own save that was out when the page closed, and keeps what they typed after it", () => {
    const canvas = drive(openState("a1", draftOf(5, "a", "abc", ["ab"])));

    canvas.send({ type: "read", detail: detailAt(6, "ab") });

    expect(canvas.state.opened).toBe("draft");
    expect(canvas.state.text).toBe("abc");
    expect(canvas.state.base).toEqual({ version: 6, content: "ab", author: "user" });
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([
      { type: "put", content: "abc", baseVersion: 6, hidden: false },
    ]);
  });

  it("brings back the base the person went back to after a save that landed", () => {
    const canvas = drive(openState("a1", draftOf(5, "before", "before", ["after"])));

    canvas.send({ type: "read", detail: detailAt(6, "after") });

    expect(canvas.state.text).toBe("before");
    expect(statusOf(canvas.state, true)).toBe("unsaved");
  });

  it("does not take a version the agent wrote with the same words for the person's own save", () => {
    const canvas = drive(openState("a1", draftOf(5, "a", "abc", ["ab"])));

    canvas.send({ type: "read", detail: detailAt(6, "ab", { head_author: "agent:ming" }) });

    expect(statusOf(canvas.state, true)).toBe("conflict");
  });

  it("ignores a draft kept for another canvas", () => {
    const canvas = drive(openState("a1", { ...draftOf(5, "hello", "not this one"), artifact_id: "a2" }));

    canvas.send({ type: "read", detail: detailAt(5, "hello") });

    expect(canvas.state.text).toBe("hello");
    expect(canvas.state.opened).toBe("fresh");
  });
});

describe("a canvas hearing about versions before it loaded", () => {
  it("reads once more after the first read when the stream already named a newer version", () => {
    const canvas = drive(openState("a1", null));
    canvas.send(event(7));

    expect(getsIn(canvas.send({ type: "read", detail: detailAt(6, "a6") }))).toBe(1);
    expect(statusOf(canvas.state, true)).toBe("newer");
  });

  it("opens deleted when the delete arrives before the first read", () => {
    const canvas = drive(openState("a1", draftOf(3, "a", "a and mine")));
    canvas.send(deleted);

    expect(canvas.send({ type: "read", detail: detailAt(5, "a") })).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("gone");
    expect(canvas.state.text).toBe("a and mine");
  });
});
