import { describe, expect, it } from "vitest";
import { applyEdits, editsFromHunks, mapOffset } from "./line-edits";

describe("editsFromHunks", () => {
  it("replaces each changed range of the first text with the second text's lines", () => {
    const hunks = [
      { a: 0, aEnd: 0, b: 0, bEnd: 2 },
      { a: 3, aEnd: 4, b: 5, bEnd: 5 },
    ];
    expect(editsFromHunks(hunks, ["x", "y", "a", "b", "c"])).toEqual([
      { start: 0, end: 0, lines: ["x", "y"] },
      { start: 3, end: 4, lines: [] },
    ]);
  });
});

describe("applyEdits", () => {
  it("inserts, replaces and removes lines in one pass", () => {
    const edits = [
      { start: 0, end: 0, lines: ["top"] },
      { start: 1, end: 2, lines: ["B", "B2"] },
      { start: 3, end: 4, lines: [] },
    ];
    expect(applyEdits(["a", "b", "c", "d", "e"], edits)).toEqual(["top", "a", "B", "B2", "c", "e"]);
  });

  it("leaves the lines alone without edits", () => {
    expect(applyEdits(["a", "b"], [])).toEqual(["a", "b"]);
  });
});

describe("mapOffset", () => {
  it("moves the cursor down by the lines added above it and keeps its column", () => {
    const before = "a\nb\ncd";
    const after = "x\ny\na\nb\ncd";
    expect(mapOffset(before, after, [{ start: 0, end: 0, lines: ["x", "y"] }], 5)).toBe(9);
  });

  it("moves the cursor down with its line when lines land right above it", () => {
    expect(mapOffset("a\nbc", "a\nx\nbc", [{ start: 1, end: 1, lines: ["x"] }], 3)).toBe(5);
  });

  it("moves the cursor up by the lines removed above it, up to the line right before", () => {
    expect(mapOffset("a\nb\nc\nde", "c\nde", [{ start: 0, end: 2, lines: [] }], 7)).toBe(3);
    expect(mapOffset("a\nb\nc", "c", [{ start: 0, end: 2, lines: [] }], 4)).toBe(0);
  });

  it("leaves the cursor where it was when the change is below it", () => {
    expect(mapOffset("a\nb\nc", "a\nb\nC!", [{ start: 2, end: 3, lines: ["C!"] }], 1)).toBe(1);
  });

  it("does not move a cursor on the last line when lines are added after it", () => {
    expect(mapOffset("a\nb", "a\nb\nc", [{ start: 2, end: 2, lines: ["c"] }], 3)).toBe(3);
  });

  it("keeps the cursor on the same character with changes on both sides of it", () => {
    const edits = [
      { start: 0, end: 1, lines: ["A", "A2"] },
      { start: 2, end: 3, lines: ["D"] },
    ];
    const after = "A\nA2\nbXc\nD";
    expect(mapOffset("a\nbXc\nd", after, edits, 4)).toBe(7);
    expect(after[7]).toBe("c");
  });

  it("puts a cursor inside a replaced range at the end of what replaced it", () => {
    expect(mapOffset("a\nbcd\ne", "a\nXY\nZ\ne", [{ start: 1, end: 2, lines: ["XY", "Z"] }], 3)).toBe(6);
  });

  it("puts a cursor inside a removed range where the removed lines were", () => {
    expect(mapOffset("a\nb\nc", "a\nc", [{ start: 1, end: 2, lines: [] }], 3)).toBe(2);
    expect(mapOffset("a\nb\nc", "a", [{ start: 1, end: 3, lines: [] }], 5)).toBe(1);
  });

  it("keeps the cursor inside the new text when the texts were too large to compare", () => {
    expect(mapOffset("abcdef", "abc", null, 5)).toBe(3);
    expect(mapOffset("abc", "abcdef", null, 2)).toBe(2);
  });
});
