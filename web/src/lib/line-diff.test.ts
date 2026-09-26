import { describe, expect, it } from "vitest";
import { lineDiff } from "./line-diff";

describe("lineDiff", () => {
  it("keeps unchanged context and marks additions where they land", () => {
    expect(lineDiff("- trà\n- ngủ sớm", "- trà\n- cà phê\n- ngủ sớm")).toEqual([
      { text: "- trà", op: "same" },
      { text: "- cà phê", op: "add" },
      { text: "- ngủ sớm", op: "same" },
    ]);
  });

  it("shows a dropped line as a removal instead of hiding it", () => {
    expect(lineDiff("- trà\n- dị ứng tôm\n- ngủ sớm", "- trà\n- ngủ sớm")).toEqual([
      { text: "- trà", op: "same" },
      { text: "- dị ứng tôm", op: "remove" },
      { text: "- ngủ sớm", op: "same" },
    ]);
  });

  it("reads a changed line as the old one removed, then the new one added", () => {
    expect(lineDiff("a\n\nb", "a\nc")).toEqual([
      { text: "a", op: "same" },
      { text: "b", op: "remove" },
      { text: "c", op: "add" },
    ]);
  });

  it("treats an empty side as all added or all removed", () => {
    expect(lineDiff("", "x\ny").map((l) => l.op)).toEqual(["add", "add"]);
    expect(lineDiff("x\ny", "").map((l) => l.op)).toEqual(["remove", "remove"]);
  });

  it("ignores trailing spaces but keeps indentation as a difference", () => {
    expect(lineDiff("a  \n  b", "a\nb")).toEqual([
      { text: "a", op: "same" },
      { text: "  b", op: "remove" },
      { text: "b", op: "add" },
    ]);
  });
});
