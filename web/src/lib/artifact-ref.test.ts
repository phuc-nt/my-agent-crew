import { describe, expect, it } from "vitest";
import { artifactRef } from "./artifact-ref";

const ID = "0123456789ab";

describe("a path that names a canvas", () => {
  // The table `artifact_ref` is held to in tests/test_telegram_canvas_file.py: the chat and the web
  // read the same line of a reply, and have to make the same thing of it.
  it.each<[string, string | null]>([
    [`artifact:${ID}`, ID],
    [`artifact: ${ID} `, ID],
    ["artifact:0123456789AB", ""],
    ["artifact:", ""],
    ["artifact:0123456789a", ""],
    ["artifact:0123456789abc", ""],
    [`artifact:${ID} v2`, ""],
    ["artifact:../x", ""],
    ["artifact:0123456789ag", ""],
    ["out/brief.pdf", null],
    [`Artifact:${ID}`, null],
    [`notes/artifact:${ID}`, null],
    [` artifact:${ID}`, null],
    ["", null],
  ])("reads %j as %j: the id, nothing for a name no canvas has, null for a file", (path, ref) => {
    expect(artifactRef(path)).toBe(ref);
  });
});
