import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { fullStorage, memoryStorage, refusingStorage } from "../test/memory-storage";
import { keys, readJson, readText, writeJson, writeText } from "./local-store";

afterEach(() => vitest.unstubAllGlobals());

describe("this device's small memories", () => {
  it("lists the keys under a prefix and no others", () => {
    writeText("canvas-draft:a1", "one");
    writeText("canvas-draft:a2", "two");
    writeText("composer-draft:c1", "three");

    expect(keys("canvas-draft:").sort()).toEqual(["canvas-draft:a1", "canvas-draft:a2"]);
    expect(keys("nothing:")).toEqual([]);
  });

  it("says a write was kept, and a removal too", () => {
    expect(writeText("note", "kept")).toBe(true);
    expect(writeJson("choice", { width: 480 })).toBe(true);
    expect(readText("note")).toBe("kept");
    expect(readJson("choice")).toEqual({ width: 480 });

    expect(writeText("note", null)).toBe(true);
    expect(readText("note")).toBeNull();
  });

  it("says a write was not kept when the browser refuses storage, and lists nothing", () => {
    refusingStorage();

    expect(writeText("note", "lost")).toBe(false);
    expect(writeJson("choice", 1)).toBe(false);
    expect(keys("")).toEqual([]);
    expect(readText("note")).toBeNull();
  });

  it("says a write was not kept when the quota is used up", () => {
    const store = memoryStorage();
    store.set("old", "before");
    fullStorage(store);

    expect(writeText("note", "x".repeat(10))).toBe(false);
    expect(writeJson("choice", [1, 2])).toBe(false);
    expect(writeText("old", null)).toBe(true);
    expect(store.has("old")).toBe(false);
  });
});
