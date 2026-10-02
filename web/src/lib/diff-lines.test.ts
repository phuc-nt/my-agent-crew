import { describe, expect, it } from "vitest";
import { diffLines } from "./diff-lines";

const lines = (text: string) => text.split("\n");

describe("diffLines", () => {
  it("finds nothing between equal texts", () => {
    expect(diffLines(lines("a\nb"), lines("a\nb"))).toEqual([]);
  });

  it("places an insertion, a removal and a replacement where they happen", () => {
    expect(diffLines(lines("a\nb\nc"), lines("a\nx\nb\nc"))).toEqual([{ a: 1, aEnd: 1, b: 1, bEnd: 2 }]);
    expect(diffLines(lines("a\nb\nc"), lines("a\nc"))).toEqual([{ a: 1, aEnd: 2, b: 1, bEnd: 1 }]);
    expect(diffLines(lines("a\nb\nc"), lines("a\ny\nc"))).toEqual([{ a: 1, aEnd: 2, b: 1, bEnd: 2 }]);
  });

  it("keeps changes at the start and at the end apart, with the common lines between them", () => {
    expect(diffLines(lines("a\nb\nc\nd"), lines("x\nb\nc\ny"))).toEqual([
      { a: 0, aEnd: 1, b: 0, bEnd: 1 },
      { a: 3, aEnd: 4, b: 3, bEnd: 4 },
    ]);
  });

  it("counts blank lines, trailing spaces and the final newline as lines", () => {
    expect(diffLines(lines("a\n\nb"), lines("a\nb"))).toEqual([{ a: 1, aEnd: 2, b: 1, bEnd: 1 }]);
    expect(diffLines(lines("a  \nb"), lines("a\nb"))).toEqual([{ a: 0, aEnd: 1, b: 0, bEnd: 1 }]);
    expect(diffLines(lines("a\nb"), lines("a\nb\n"))).toEqual([{ a: 2, aEnd: 2, b: 2, bEnd: 3 }]);
  });

  it("makes an empty side a single change", () => {
    expect(diffLines([], ["x", "y"])).toEqual([{ a: 0, aEnd: 0, b: 0, bEnd: 2 }]);
    expect(diffLines(["x", "y"], [])).toEqual([{ a: 0, aEnd: 2, b: 0, bEnd: 0 }]);
  });

  it("reads two swapped lines as the second text's line first, then the first text's", () => {
    expect(diffLines(["x", "y"], ["y", "x"])).toEqual([
      { a: 0, aEnd: 0, b: 0, bEnd: 1 },
      { a: 1, aEnd: 2, b: 2, bEnd: 2 },
    ]);
  });

  it("matches the longest common run, not the first equal line it meets", () => {
    expect(diffLines(lines("x\na\nb\nc\ny"), lines("z\nc\na\nb\nc\nw"))).toEqual([
      { a: 0, aEnd: 1, b: 0, bEnd: 2 },
      { a: 4, aEnd: 5, b: 5, bEnd: 6 },
    ]);
  });

  it("gives up on a middle larger than the cap, measured after the common head and tail are cut", () => {
    const base = Array.from({ length: 100 }, (_, i) => `line ${i}`);
    const rewritten = base.map((line) => `${line}!`);
    expect(diffLines(base, rewritten, 9_999)).toBeNull();
    expect(diffLines(base, rewritten, 10_000)).toHaveLength(1);
    const oneChange = [...base];
    oneChange[50] = "changed";
    expect(diffLines(base, oneChange, 1)).toEqual([{ a: 50, aEnd: 51, b: 50, bEnd: 51 }]);
  });
});
