import { describe, expect, it } from "vitest";
import { clip } from "./clip-text";

describe("a text cut to a number of UTF-16 units", () => {
  it("is left as it is when it fits, whatever its last unit is", () => {
    expect(clip("", 0)).toBe("");
    expect(clip("abc", 3)).toBe("abc");
    // Half a pair the text came with is not the cut's to take away.
    expect(clip("ab\ud83d", 3)).toBe("ab\ud83d");
  });

  it("keeps the first units and drops the rest", () => {
    expect(clip("abcd", 3)).toBe("abc");
    expect(clip("abc", 0)).toBe("");
  });

  it("drops a pair whole rather than leave its first half at the end", () => {
    expect(clip("ab😀c", 3)).toBe("ab");
    expect(clip("ab😀c", 4)).toBe("ab😀");
    expect(clip("a😀😀", 3)).toBe("a😀");
  });
});
