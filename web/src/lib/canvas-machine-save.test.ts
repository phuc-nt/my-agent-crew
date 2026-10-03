import { describe, expect, it } from "vitest";
import type { StorageFull } from "../api/artifact-types";
import { conflictAt, detailAt, drive, lost, metaAt, openOn, putsIn, typeAndPause } from "../test/canvas-driver";
import { CAPS } from "./canvas-caps";
import { type CanvasInput, openState, statusOf } from "./canvas-machine";

const SIZE_CAP = CAPS.markdown;

const refused = (status: number, full: StorageFull | null = null): CanvasInput => ({
  type: "saveFailed",
  status,
  conflict: null,
  full,
});

describe("autosaving a canvas", () => {
  it("opens loading, then shows the newest version as saved", () => {
    const canvas = drive(openState("a1", null));
    expect(statusOf(canvas.state, true)).toBe("loading");

    canvas.send({ type: "read", detail: detailAt(5, "hello", { head_author: "agent:ming" }) });

    expect(canvas.state.text).toBe("hello");
    expect(canvas.state.base).toEqual({ version: 5, content: "hello", author: "agent:ming" });
    expect(canvas.state.opened).toBe("fresh");
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("ignores typing before the canvas has loaded", () => {
    const canvas = drive(openState("a1", null));

    expect(canvas.send({ type: "edit", text: "early" })).toEqual([]);
    canvas.send({ type: "read", detail: detailAt(5, "hello") });

    expect(canvas.state.text).toBe("hello");
  });

  it("marks a keystroke unsaved and sends nothing until a save falls due", () => {
    const canvas = openOn("hello");

    expect(canvas.send({ type: "edit", text: "hello world" })).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("unsaved");
  });

  it("sends the text with the version it was edited from, then takes the reply as its base", () => {
    const canvas = openOn("hello");

    expect(putsIn(typeAndPause(canvas, "hello world"))).toEqual([
      { type: "put", content: "hello world", baseVersion: 5, hidden: false },
    ]);
    expect(statusOf(canvas.state, true)).toBe("saving");

    const effects = canvas.send({ type: "saved", meta: metaAt(6) });
    expect(effects).toContainEqual({ type: "dropDraft", text: "hello world" });
    expect(canvas.state.base).toEqual({ version: 6, content: "hello world", author: "user" });
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("takes the reply's version as the next base even across a gap", () => {
    const canvas = openOn("hello");
    typeAndPause(canvas, "hello!");

    canvas.send({ type: "saved", meta: metaAt(9) });

    expect(putsIn(typeAndPause(canvas, "hello!!"))).toEqual([
      { type: "put", content: "hello!!", baseVersion: 9, hidden: false },
    ]);
  });

  it("sends nothing when the text is back to its base", () => {
    const canvas = openOn("hello");
    canvas.send({ type: "edit", text: "hello!" });

    expect(putsIn(typeAndPause(canvas, "hello"))).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("saved");
  });

  it("keeps one save in flight and sends what was typed meanwhile once it lands", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    expect(putsIn(typeAndPause(canvas, "abc"))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "blur" }))).toEqual([]);

    expect(putsIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "put", content: "abc", baseVersion: 6, hidden: false },
    ]);
  });

  it("leaves text typed during a save to its own timer when no save fell due meanwhile", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send({ type: "edit", text: "abc" });

    expect(putsIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("unsaved");
  });

  it("holds a save the hidden tab asks for until the one in flight lands", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send({ type: "edit", text: "abc" });
    canvas.send({ type: "visibility", hidden: true });

    expect(putsIn(canvas.send({ type: "saveDue", reason: "hidden" }))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saved", meta: metaAt(6) }))).toEqual([
      { type: "put", content: "abc", baseVersion: 6, hidden: true },
    ]);
  });

  it("marks a save made while the tab is hidden, so it may outlive the page", () => {
    const canvas = openOn("a");
    canvas.send({ type: "edit", text: "ab" });
    canvas.send({ type: "visibility", hidden: true });
    expect(putsIn(canvas.send({ type: "saveDue", reason: "hidden" }))[0].hidden).toBe(true);
    canvas.send({ type: "saved", meta: metaAt(6) });

    canvas.send({ type: "visibility", hidden: false });
    expect(putsIn(typeAndPause(canvas, "abc"))[0].hidden).toBe(false);
  });

  it("stops before sending a text over the size cap, and goes on once it is small enough", () => {
    const canvas = openOn("a");

    expect(putsIn(typeAndPause(canvas, "x".repeat(SIZE_CAP + 1)))).toEqual([]);
    expect(statusOf(canvas.state, true)).toBe("tooLarge");

    canvas.send({ type: "edit", text: "x".repeat(SIZE_CAP) });
    expect(canvas.state.stop).toBeNull();
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toHaveLength(1);
  });

  it("measures the size cap in UTF-8 bytes, not characters", () => {
    const canvas = openOn("a");
    // Three bytes each in UTF-8.
    const text = "ệ".repeat(Math.floor(SIZE_CAP / 3) + 1);

    expect(putsIn(typeAndPause(canvas, text))).toEqual([]);
    expect(canvas.state.stop).toBe("tooLarge");
  });

  it("never has two saves in flight, whatever falls due and whatever comes back", () => {
    const canvas = openOn("a");
    let inFlight = 0;
    let most = 0;
    let ticket = 0;
    const send = (input: CanvasInput) => {
      inFlight += putsIn(canvas.send(input)).length;
      most = Math.max(most, inFlight);
    };
    const everythingFallsDue = () => {
      for (const reason of ["timer", "blur", "hidden", "manual", "retry"] as const) {
        send({ type: "edit", text: `${canvas.state.text}.` });
        send({ type: "saveDue", reason });
      }
      send({ type: "flush", ticket: ++ticket });
      send({ type: "resync" });
    };

    send({ type: "edit", text: "ab" });
    send({ type: "saveDue", reason: "timer" });
    everythingFallsDue();
    inFlight -= 1;
    send(lost);
    everythingFallsDue();
    inFlight -= 1;
    send(refused(503));
    send({ type: "saveDue", reason: "retry" });
    everythingFallsDue();
    inFlight -= 1;
    send({ type: "saved", meta: metaAt(6) });
    everythingFallsDue();

    expect(most).toBe(1);
  });
});

describe("a save the network or the server lost", () => {
  it("retries after 2, 5, 15 and 30 seconds, then every minute", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    const delays: number[] = [];

    for (let n = 0; n < 6; n++) {
      for (const effect of canvas.send(lost)) if (effect.type === "retryIn") delays.push(effect.ms);
      canvas.send({ type: "saveDue", reason: "retry" });
    }

    expect(delays).toEqual([2000, 5000, 15000, 30000, 60000, 60000]);
  });

  it("says whether this device or the server is out of reach", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);

    expect(statusOf(canvas.state, false)).toBe("offline");
    expect(statusOf(canvas.state, true)).toBe("serverDown");
  });

  it("skips timer and blur saves while a retry waits, then sends the newest text when it is due", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);

    expect(putsIn(typeAndPause(canvas, "abc"))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "blur" }))).toEqual([]);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "retry" }))).toEqual([
      { type: "put", content: "abc", baseVersion: 5, hidden: false },
    ]);
  });

  it("retries at once when the stream comes back or the tab shows", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);

    expect(putsIn(canvas.send({ type: "resync" }))).toEqual([
      { type: "put", content: "ab", baseVersion: 5, hidden: false },
    ]);
  });

  it("ignores a retry timer that fires after a save already went through", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "saveDue", reason: "manual" });
    canvas.send({ type: "saved", meta: metaAt(6) });
    canvas.send({ type: "edit", text: "abc" });

    expect(putsIn(canvas.send({ type: "saveDue", reason: "retry" }))).toEqual([]);
  });

  it("treats a 5xx like a lost reply, and starts again from two seconds once a save goes through", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    expect(canvas.send(refused(503))).toContainEqual({ type: "retryIn", ms: 2000 });
    canvas.send({ type: "saveDue", reason: "retry" });
    canvas.send({ type: "saved", meta: metaAt(6) });
    expect(statusOf(canvas.state, true)).toBe("saved");

    typeAndPause(canvas, "abc");
    expect(canvas.send(lost)).toContainEqual({ type: "retryIn", ms: 2000 });
  });

  it("still sends the text when it went back to its base after a lost save, which may have landed", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "edit", text: "a" });

    expect(statusOf(canvas.state, true)).toBe("serverDown");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "retry" }))).toEqual([
      { type: "put", content: "a", baseVersion: 5, hidden: false },
    ]);
  });
});

describe("a save the server refused", () => {
  it("takes a 404 as the canvas being deleted, keeps the text and sends nothing more", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(refused(404));

    expect(statusOf(canvas.state, true)).toBe("gone");
    expect(canvas.state.text).toBe("ab");
    expect(canvas.send({ type: "edit", text: "abc" })).toEqual([]);
    expect(canvas.state.text).toBe("ab");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "manual" }))).toEqual([]);
  });

  it("stops on a 413 until the text changes", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(refused(413));

    expect(statusOf(canvas.state, true)).toBe("tooLarge");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([]);
    expect(putsIn(typeAndPause(canvas, "abc"))).toHaveLength(1);
  });

  it("stops on a 507, keeping the store's largest canvases, until a manual save", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    const full = { used: 10, cap: 10, largest: [{ id: "a9", title: "Lớn", size: 9 }] };

    canvas.send(refused(507, full));

    expect(statusOf(canvas.state, true)).toBe("full");
    expect(canvas.state.full).toEqual(full);
    canvas.send({ type: "edit", text: "abc" });
    for (const reason of ["timer", "blur", "hidden", "retry"] as const) {
      expect(putsIn(canvas.send({ type: "saveDue", reason }))).toEqual([]);
    }
    expect(putsIn(canvas.send({ type: "saveDue", reason: "manual" }))).toHaveLength(1);
    expect(canvas.state.stop).toBeNull();
    expect(canvas.state.full).toBeNull();
  });

  it("lifts a stop once the text is back to its base, with nothing left to save", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(refused(507, { used: 10, cap: 10, largest: [] }));

    canvas.send({ type: "edit", text: "a" });

    expect(statusOf(canvas.state, true)).toBe("saved");
    expect(canvas.state.full).toBeNull();
  });

  it("stops on a 422 or any other 4xx until a manual save", () => {
    for (const status of [422, 400, 403]) {
      const canvas = openOn("a");
      typeAndPause(canvas, "ab");

      canvas.send(refused(status));

      expect(statusOf(canvas.state, true)).toBe("invalid");
      expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([]);
      expect(putsIn(canvas.send({ type: "saveDue", reason: "manual" }))).toHaveLength(1);
    }
  });

  it("does not take a 409 without the newest version for a conflict", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(refused(409));

    expect(statusOf(canvas.state, true)).toBe("invalid");
  });

  it("clears the retry count once the server answers at all", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(lost);
    canvas.send({ type: "saveDue", reason: "retry" });

    canvas.send(refused(422));

    expect(canvas.state.failures).toBe(0);
    expect(statusOf(canvas.state, false)).toBe("invalid");
  });

  it("keeps a conflict apart from the other refusals", () => {
    const canvas = openOn("one\ntwo");
    typeAndPause(canvas, "one!\ntwo");

    canvas.send(conflictAt(6, "one?\ntwo"));

    expect(statusOf(canvas.state, true)).toBe("conflict");
    expect(canvas.state.stop).toBeNull();
  });
});
