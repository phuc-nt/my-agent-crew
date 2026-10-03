import { describe, expect, it } from "vitest";
import { metaAt, openOn, putsIn, typeAndPause } from "../test/canvas-driver";
import { type CanvasInput, statusOf } from "./canvas-machine";

const KB = 1024;
const MB = 1024 * KB;

/** A 413 as the client reads it: with the limit the server named, unless it named none. */
const tooLarge = (cap?: number): CanvasInput => ({
  type: "saveFailed",
  status: 413,
  conflict: null,
  full: null,
  ...(cap === undefined ? {} : { cap }),
});

describe("the size a save may have, by the kind of canvas", () => {
  it.each([
    ["markdown", 512 * KB],
    ["code", 512 * KB],
    ["mermaid", 512 * KB],
    ["html", 4 * MB],
    ["svg", 2 * MB],
  ])("sends %s text up to %i bytes, and stops one byte over, naming the cap", (kind, cap) => {
    const fitting = openOn("a", 5, { kind });
    expect(putsIn(typeAndPause(fitting, "x".repeat(cap)))).toHaveLength(1);
    expect(fitting.state.stop).toBeNull();

    const over = openOn("a", 5, { kind });
    expect(putsIn(typeAndPause(over, "x".repeat(cap + 1)))).toEqual([]);
    expect(statusOf(over.state, true)).toBe("tooLarge");
    expect(over.state.cap).toBe(cap);
  });

  it("lets an html canvas take a megabyte that a markdown canvas may not", () => {
    const text = "x".repeat(MB);

    expect(putsIn(typeAndPause(openOn("a", 5, { kind: "html" }), text))).toHaveLength(1);
    expect(putsIn(typeAndPause(openOn("a", 5, { kind: "markdown" }), text))).toEqual([]);
  });

  it("holds a canvas of a kind it does not know to the smallest cap", () => {
    expect(putsIn(typeAndPause(openOn("a", 5, { kind: "video" }), "x".repeat(512 * KB)))).toHaveLength(1);

    const over = openOn("a", 5, { kind: "video" });
    expect(putsIn(typeAndPause(over, "x".repeat(600 * KB)))).toEqual([]);
    expect(over.state.cap).toBe(512 * KB);
  });

  it("counts UTF-8 bytes against the cap of an html canvas as well", () => {
    // Three bytes each in UTF-8.
    expect(putsIn(typeAndPause(openOn("a", 5, { kind: "html" }), "ệ".repeat(Math.floor((4 * MB) / 3))))).toHaveLength(1);

    const over = openOn("a", 5, { kind: "html" });
    expect(putsIn(typeAndPause(over, "ệ".repeat(Math.floor((4 * MB) / 3) + 1)))).toEqual([]);
    expect(over.state.stop).toBe("tooLarge");
  });
});

describe("a stop for size", () => {
  it("is lifted once the text fits its kind again, and forgets the cap", () => {
    const canvas = openOn("a", 5, { kind: "html" });
    typeAndPause(canvas, "x".repeat(4 * MB + 1));
    expect(canvas.state.cap).toBe(4 * MB);

    canvas.send({ type: "edit", text: "x".repeat(4 * MB) });

    expect(canvas.state.stop).toBeNull();
    expect(canvas.state.cap).toBeNull();
    expect(statusOf(canvas.state, true)).toBe("unsaved");
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toHaveLength(1);
  });

  it("stays while the edit still does not fit, and keeps saying what the cap is", () => {
    const canvas = openOn("a", 5, { kind: "svg" });
    typeAndPause(canvas, "x".repeat(2 * MB + 1));

    canvas.send({ type: "edit", text: "x".repeat(2 * MB + 2) });

    expect(statusOf(canvas.state, true)).toBe("tooLarge");
    expect(canvas.state.cap).toBe(2 * MB);
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([]);
  });

  it("lifts a stop the server asked for when the text fits the cap its kind has", () => {
    const canvas = openOn("a", 5, { kind: "html" });
    typeAndPause(canvas, "x".repeat(MB));
    canvas.send(tooLarge(512 * KB));
    expect(canvas.state.cap).toBe(512 * KB);

    canvas.send({ type: "edit", text: "x".repeat(MB + 1) });

    expect(canvas.state.stop).toBeNull();
    expect(canvas.state.cap).toBeNull();
  });

  it("is not lifted for a markdown canvas that edits to a megabyte", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(tooLarge());

    canvas.send({ type: "edit", text: "x".repeat(MB) });

    expect(canvas.state.stop).toBe("tooLarge");
  });

  it("is lifted by saving by hand, which sends the text again and forgets the cap", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(tooLarge(3 * MB));
    expect(canvas.state.cap).toBe(3 * MB);

    const effects = canvas.send({ type: "saveDue", reason: "manual" });

    expect(putsIn(effects)).toEqual([{ type: "put", content: "ab", baseVersion: 5, hidden: false }]);
    expect(canvas.state.stop).toBeNull();
    expect(canvas.state.cap).toBeNull();
  });

  it("is lifted by a restore, which replaces the text, and forgets the cap", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(tooLarge(3 * MB));

    canvas.send({ type: "restored", version: 6, content: "a" });

    expect(canvas.state.stop).toBeNull();
    expect(canvas.state.cap).toBeNull();
    expect(statusOf(canvas.state, true)).toBe("saved");
  });
});

describe("a 413 from the server", () => {
  it("names the limit the server gave, over the table's", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");

    canvas.send(tooLarge(3 * MB));

    expect(statusOf(canvas.state, true)).toBe("tooLarge");
    expect(canvas.state.cap).toBe(3 * MB);
  });

  it("names the cap of the canvas's kind when the server gave none", () => {
    const canvas = openOn("<svg/>", 5, { kind: "svg" });
    typeAndPause(canvas, "<svg></svg>");

    canvas.send(tooLarge());

    expect(canvas.state.cap).toBe(2 * MB);
  });

  it("stops the text and sends nothing more until it changes", () => {
    const canvas = openOn("a", 5, { kind: "html" });
    typeAndPause(canvas, "<p>b</p>");

    canvas.send(tooLarge(4 * MB));

    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toEqual([]);
    canvas.send({ type: "edit", text: "<p>c</p>" });
    expect(putsIn(canvas.send({ type: "saveDue", reason: "timer" }))).toHaveLength(1);
  });

  it("leaves no cap behind once a save lands", () => {
    const canvas = openOn("a");
    typeAndPause(canvas, "ab");
    canvas.send(tooLarge(3 * MB));
    canvas.send({ type: "edit", text: "abc" });
    canvas.send({ type: "saveDue", reason: "timer" });

    canvas.send({ type: "saved", meta: metaAt(6) });

    expect(canvas.state.cap).toBeNull();
    expect(statusOf(canvas.state, true)).toBe("saved");
  });
});
