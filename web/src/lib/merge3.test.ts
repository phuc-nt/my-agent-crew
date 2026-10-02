import { describe, expect, it } from "vitest";
import { merge3 } from "./merge3";

const numbered = (count: number, label = "l") => Array.from({ length: count }, (_, i) => `${label}${i}`);

describe("merge3", () => {
  it("takes the server's change when the person changed nothing", () => {
    expect(merge3("a\nb", "a\nb", "a\nB")).toEqual({
      ok: true,
      text: "a\nB",
      edits: [{ start: 1, end: 2, lines: ["B"] }],
    });
  });

  it("keeps the person's change when the server changed nothing", () => {
    expect(merge3("a\nb", "a\nb!", "a\nb")).toEqual({ ok: true, text: "a\nb!", edits: [] });
  });

  it("merges two edits far apart in a long text under the default cap", () => {
    const base = numbered(5000, "dòng ");
    const mine = [...base];
    mine[10] = "người sửa";
    const theirs = [...base];
    theirs[4990] = "agent sửa";
    const expected = [...mine];
    expected[4990] = "agent sửa";
    expect(merge3(base.join("\n"), mine.join("\n"), theirs.join("\n"))).toEqual({
      ok: true,
      text: expected.join("\n"),
      edits: [{ start: 4990, end: 4991, lines: ["agent sửa"] }],
    });
  });

  it("gives the server's changes in the person's line numbers", () => {
    const base = numbered(10);
    const mine = ["m0", "m1", ...base.slice(0, 8), "M8", "l9"];
    const theirs = ["l0", "l1", "l2", "l4", "T5", "l6", "l7", "l8", "l9"];
    expect(merge3(base.join("\n"), mine.join("\n"), theirs.join("\n"))).toEqual({
      ok: true,
      text: ["m0", "m1", "l0", "l1", "l2", "l4", "T5", "l6", "l7", "M8", "l9"].join("\n"),
      edits: [
        { start: 5, end: 6, lines: [] },
        { start: 7, end: 8, lines: ["T5"] },
      ],
    });
  });

  it("refuses a rewrite of the lines right before the server's insertion", () => {
    const base = numbered(20);
    const mine = [...base.slice(0, 10), "x", "y", "z", ...base.slice(13)];
    const theirs = [...base.slice(0, 13), "new", ...base.slice(13)];
    expect(merge3(base.join("\n"), mine.join("\n"), theirs.join("\n"))).toEqual({ ok: false });
  });

  it("refuses two additions at the end, with or without a final newline", () => {
    expect(merge3("a\n", "a\nb\n", "a\nc\n")).toEqual({ ok: false });
    expect(merge3("a", "a\nb", "a\nc")).toEqual({ ok: false });
  });

  it("refuses edits of neighbouring lines", () => {
    expect(merge3("a\nb\nc\nd", "a\nB\nc\nd", "a\nb\nC\nd")).toEqual({ ok: false });
  });

  it("keeps the final newline, or its absence, of each side", () => {
    expect(merge3("a\nb\nc\n", "A\nb\nc\n", "a\nb\nC\n")).toEqual({
      ok: true,
      text: "A\nb\nC\n",
      edits: [{ start: 2, end: 3, lines: ["C"] }],
    });
    expect(merge3("a\nb\nc", "A\nb\nc", "a\nb\nC")).toMatchObject({ ok: true, text: "A\nb\nC" });
    expect(merge3("a\nb\nc\n", "a\nb\nc", "A\nb\nc\n")).toMatchObject({ ok: true, text: "A\nb\nc" });
  });

  it("does not double an edit both sides made", () => {
    expect(merge3("a\nb\nc", "a\nB\nc", "a\nB\nc")).toEqual({ ok: true, text: "a\nB\nc", edits: [] });
  });

  it("refuses a line one side removed and the other edited", () => {
    expect(merge3("a\nb\nc", "a\nc", "a\nB\nc")).toEqual({ ok: false });
    expect(merge3("a\nb\nc", "a\nB\nc", "a\nc")).toEqual({ ok: false });
  });

  it("refuses when either side changed too much to compare under the cap", () => {
    const base = numbered(50).join("\n");
    const rewritten = numbered(50, "L").join("\n");
    expect(merge3(base, rewritten, base, 100)).toEqual({ ok: false });
    expect(merge3(base, base, rewritten, 100)).toEqual({ ok: false });
    expect(merge3(base, base, rewritten, 2500)).toMatchObject({ ok: true, text: rewritten });
  });
});
