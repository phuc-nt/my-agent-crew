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

  it("is asked of imports only", () => {
    expect(importedFile(call({ path: "notes/a.md" }, "workspace_read"))).toBeNull();
  });
});
