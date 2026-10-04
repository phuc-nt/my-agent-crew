import { describe, expect, it } from "vitest";
import { IMPORT, argument, importedFile, importsInto } from "./canvas-import-call";

const call = (args: unknown, name = IMPORT) => ({ name, arguments: args });

describe("one argument of a tool call", () => {
  it("is read from the mapping the model sent", () => {
    expect(argument(call({ path: "notes/a.md", id: 7 }), "path")).toBe("notes/a.md");
    expect(argument(call({ path: "notes/a.md", id: 7 }), "id")).toBe(7);
    expect(argument(call({ path: "notes/a.md" }), "title")).toBeUndefined();
  });

  it("is nothing when the call holds no mapping, as one saved by an older version does not", () => {
    for (const args of ["path=notes/a.md", null, undefined, 3]) {
      expect(argument(call(args), "path"), String(args)).toBeUndefined();
    }
  });
});

describe("whether an import reads into a canvas that exists", () => {
  it("does when it names a canvas", () => {
    expect(importsInto(call({ path: "a.md", id: "0123456789ab" }))).toBe(true);
  });

  it("does not when it names none, or names one blank as the server reads a blank", () => {
    for (const args of [{ path: "a.md" }, { path: "a.md", id: null }, { path: "a.md", id: "" }, { path: "a.md", id: "  \n" }]) {
      expect(importsInto(call(args)), JSON.stringify(args)).toBe(false);
    }
  });

  it("reads a blank as Python's strip does, which is not what trim strips", () => {
    // The separators U+001C to U+001F and U+0085 are spaces to the server and none to `trim`.
    for (const id of ["\u{1F}", "\u{1C}\u{1D}\u{1E}", "\u{85}", " \u{A0}\u{3000}\u{2028}\t"]) {
      expect(importsInto(call({ path: "a.md", id })), JSON.stringify(id)).toBe(false);
    }
    // U+FEFF is a space to `trim` and a character to the server, which then looks for that canvas.
    for (const id of ["\u{FEFF}", "\u{200B}", " \u{FEFF} "]) {
      expect(importsInto(call({ path: "a.md", id })), JSON.stringify(id)).toBe(true);
    }
  });

  it("does not for an id that is no text, nor for arguments that are no mapping", () => {
    expect(importsInto(call({ path: "a.md", id: 12 }))).toBe(false);
    expect(importsInto(call("id=0123456789ab"))).toBe(false);
  });

  it("is asked of imports only: a create that carries an id still makes its canvas", () => {
    expect(importsInto(call({ id: "0123456789ab" }, "artifact_create"))).toBe(false);
  });
});

describe("the file an import reads", () => {
  it("is named by the last part of its path", () => {
    expect(importedFile(call({ path: "notes/2026/thuc-don.md" }))).toBe("thuc-don.md");
    expect(importedFile(call({ path: "thuc-don.md" }))).toBe("thuc-don.md");
  });

  it("is the folder a path ends on when the path ends with a slash", () => {
    expect(importedFile(call({ path: "site/trang/" }))).toBe("trang");
  });

  it("has no name when the path is missing, blank, only slashes or no text", () => {
    for (const args of [{}, { path: "" }, { path: " " }, { path: "//" }, { path: 4 }, "path=a.md"]) {
      expect(importedFile(call(args)), JSON.stringify(args)).toBeNull();
    }
  });

  it("has no name when the path is blank as the server reads a blank, which refuses it", () => {
    for (const path of ["\u{1F}", " \n\u{85}", "\u{A0}\u{3000}", "\t "]) {
      expect(importedFile(call({ path })), JSON.stringify(path)).toBeNull();
    }
  });

  it("is a part made of spaces when that is the last one: the server reads the file of that name", () => {
    expect(importedFile(call({ path: "notes/ " }))).toBe(" ");
    expect(importedFile(call({ path: "notes/\u{A0}" }))).toBe("\u{A0}");
    expect(importedFile(call({ path: "notes/plan.md " }))).toBe("plan.md ");
    expect(importedFile(call({ path: " /a.md/" }))).toBe("a.md");
    expect(importedFile(call({ path: "\u{FEFF}" }))).toBe("\u{FEFF}");
  });

  it("is asked of imports only", () => {
    expect(importedFile(call({ path: "notes/a.md" }, "workspace_read"))).toBeNull();
  });
});
