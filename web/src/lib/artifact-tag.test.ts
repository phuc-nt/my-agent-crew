import { describe, expect, it } from "vitest";
import { isArtifactId, parseArtifactTag } from "./artifact-tag";

const ID = "0123456789ab";

describe("the tag that opens the result of a canvas write", () => {
  it("reads the canvas and the version a write made", () => {
    expect(parseArtifactTag(`[artifact ${ID} v1]\nThe canvas "Ghi chú" was made.`)).toEqual({
      id: ID,
      version: 1,
      unchanged: false,
    });
    expect(parseArtifactTag(`[artifact ${ID} v12]`)).toEqual({ id: ID, version: 12, unchanged: false });
  });

  it("reads a write that left the canvas as it was", () => {
    expect(parseArtifactTag(`[artifact ${ID} v3 unchanged]\nNothing to change.`)).toEqual({
      id: ID,
      version: 3,
      unchanged: true,
    });
  });

  it("finds no tag where a result has none", () => {
    expect(parseArtifactTag(null)).toBeNull();
    expect(parseArtifactTag("")).toBeNull();
    expect(parseArtifactTag("artifact_edit failed: the text to replace was not found")).toBeNull();
  });

  it("takes the tag only at the very start", () => {
    expect(parseArtifactTag(`Done. [artifact ${ID} v1]`)).toBeNull();
    expect(parseArtifactTag(`\n[artifact ${ID} v1]`)).toBeNull();
    expect(parseArtifactTag(` [artifact ${ID} v1]`)).toBeNull();
    expect(parseArtifactTag(`done\n[artifact ${ID} v1]`)).toBeNull();
  });

  it("takes only the ids the server makes", () => {
    expect(parseArtifactTag("[artifact 0123456789a v1]")).toBeNull();
    expect(parseArtifactTag("[artifact 0123456789abc v1]")).toBeNull();
    expect(parseArtifactTag("[artifact 0123456789AB v1]")).toBeNull();
    expect(parseArtifactTag("[artifact 0123456789ag v1]")).toBeNull();
    expect(parseArtifactTag("[artifact ../0123456789 v1]")).toBeNull();
  });

  it("takes only a tag that is whole", () => {
    expect(parseArtifactTag(`[artifact ${ID}]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v1 changed]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v1 unchanged extra]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v1unchanged]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v1`)).toBeNull();
    expect(parseArtifactTag(`artifact ${ID} v1]`)).toBeNull();
  });

  it("takes only a version a number can hold exactly", () => {
    expect(parseArtifactTag(`[artifact ${ID} v9007199254740991]`)).toMatchObject({ version: 9007199254740991 });
    expect(parseArtifactTag(`[artifact ${ID} v9007199254740993]`)).toBeNull();
    expect(parseArtifactTag(`[artifact ${ID} v${"9".repeat(400)}]`)).toBeNull();
  });
});

describe("the ids the server makes", () => {
  it("accepts twelve lower-case hex digits and nothing else", () => {
    expect(isArtifactId(ID)).toBe(true);
    expect(isArtifactId("ffffffffffff")).toBe(true);
    for (const bad of ["", "a1", "..", "../x", "0123456789a", "0123456789abc", "0123456789AB", "0123456789a/", "012345678 ab"]) {
      expect(isArtifactId(bad), JSON.stringify(bad)).toBe(false);
    }
  });

  it("refuses an id with a line break after it", () => {
    expect(isArtifactId(`${ID}\n`)).toBe(false);
  });
});
