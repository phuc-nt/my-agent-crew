import { describe, expect, it } from "vitest";
import { canvasDiff } from "./canvas-diff";

const numbered = (count: number, label = "l") => Array.from({ length: count }, (_, i) => `${label}${i}`);

describe("canvasDiff", () => {
  it("shows the removed lines of a change before the added ones, between unchanged neighbours", () => {
    expect(canvasDiff("a\nb\nc\nd", "a\nX\nY\nd")).toEqual([
      { op: "same", text: "a" },
      { op: "remove", text: "b" },
      { op: "remove", text: "c" },
      { op: "add", text: "X" },
      { op: "add", text: "Y" },
      { op: "same", text: "d" },
    ]);
  });

  it("finds nothing between equal versions", () => {
    expect(canvasDiff("a\nb", "a\nb")).toEqual([]);
  });

  it("folds a long unchanged run between two changes to three lines on each side", () => {
    const before = ["x", ...numbered(10), "y"];
    const after = ["X", ...numbered(10), "Y"];
    expect(canvasDiff(before.join("\n"), after.join("\n"))).toEqual([
      { op: "remove", text: "x" },
      { op: "add", text: "X" },
      { op: "same", text: "l0" },
      { op: "same", text: "l1" },
      { op: "same", text: "l2" },
      { op: "skip", count: 4 },
      { op: "same", text: "l7" },
      { op: "same", text: "l8" },
      { op: "same", text: "l9" },
      { op: "remove", text: "y" },
      { op: "add", text: "Y" },
    ]);
  });

  it("keeps the context after an insertion at the very top", () => {
    const before = [...numbered(10), "y"];
    const after = ["new", ...numbered(10), "Y"];
    expect(canvasDiff(before.join("\n"), after.join("\n"))).toEqual([
      { op: "add", text: "new" },
      { op: "same", text: "l0" },
      { op: "same", text: "l1" },
      { op: "same", text: "l2" },
      { op: "skip", count: 4 },
      { op: "same", text: "l7" },
      { op: "same", text: "l8" },
      { op: "same", text: "l9" },
      { op: "remove", text: "y" },
      { op: "add", text: "Y" },
    ]);
  });

  it("keeps a run of six unchanged lines between two changes whole", () => {
    const before = ["x", ...numbered(6), "y"];
    const after = ["X", ...numbered(6), "Y"];
    const lines = canvasDiff(before.join("\n"), after.join("\n"));
    expect(lines?.filter((line) => line.op === "same")).toHaveLength(6);
    expect(lines?.some((line) => line.op === "skip")).toBe(false);
  });

  it("keeps only the three unchanged lines next to a change at the start and at the end", () => {
    const before = [...numbered(10), "mid", ...numbered(10, "t")];
    const after = [...numbered(10), "MID", ...numbered(10, "t")];
    expect(canvasDiff(before.join("\n"), after.join("\n"))).toEqual([
      { op: "skip", count: 7 },
      { op: "same", text: "l7" },
      { op: "same", text: "l8" },
      { op: "same", text: "l9" },
      { op: "remove", text: "mid" },
      { op: "add", text: "MID" },
      { op: "same", text: "t0" },
      { op: "same", text: "t1" },
      { op: "same", text: "t2" },
      { op: "skip", count: 7 },
    ]);
  });

  it("shows blank lines, trailing spaces and the final newline as changes", () => {
    expect(canvasDiff("a\n\nb", "a\nb")).toEqual([
      { op: "same", text: "a" },
      { op: "remove", text: "" },
      { op: "same", text: "b" },
    ]);
    expect(canvasDiff("a  ", "a")).toEqual([
      { op: "remove", text: "a  " },
      { op: "add", text: "a" },
    ]);
    expect(canvasDiff("a", "a\n")).toEqual([
      { op: "same", text: "a" },
      { op: "add", text: "" },
    ]);
  });

  it("gives null for versions too large to compare under the cap", () => {
    expect(canvasDiff(numbered(50).join("\n"), numbered(50, "L").join("\n"), 100)).toBeNull();
  });
});
