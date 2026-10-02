import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { fullStorage, memoryStorage, refusingStorage } from "../test/memory-storage";
import { type CanvasDraft, clearDraft, pruneDrafts, readDraft, textKey, writeDraft } from "./canvas-draft";

const DAY = 24 * 60 * 60 * 1000;
const NOW = Date.parse("2026-10-02T03:00:00Z");

function draft(id: string, overrides: Partial<CanvasDraft> = {}): CanvasDraft {
  return { artifact_id: id, base_version: 3, base: "base", text: "base and more", saved_at: NOW, sent: [], ...overrides };
}

let store: Map<string, string>;

beforeEach(() => {
  store = memoryStorage();
});

afterEach(() => vitest.unstubAllGlobals());

describe("a canvas draft on this device", () => {
  it("reads back the draft of the same canvas only", () => {
    expect(writeDraft(draft("a1"))).toBe(true);

    expect(store.has("canvas-draft:a1")).toBe(true);
    expect(readDraft("a1")).toEqual(draft("a1"));
    expect(readDraft("a2")).toBeNull();
  });

  it("ignores a draft kept under one canvas that names another", () => {
    store.set("canvas-draft:a1", JSON.stringify(draft("a2")));

    expect(readDraft("a1")).toBeNull();
  });

  it("ignores a stored value that is not a draft", () => {
    const broken = [
      "{not json",
      JSON.stringify("text"),
      JSON.stringify({ ...draft("a1"), text: undefined }),
      JSON.stringify({ ...draft("a1"), base: 3 }),
      JSON.stringify({ ...draft("a1"), base_version: 0 }),
      JSON.stringify({ ...draft("a1"), base_version: 2.5 }),
      JSON.stringify({ ...draft("a1"), saved_at: "2026-10-02" }),
      JSON.stringify({ ...draft("a1"), sent: undefined }),
      JSON.stringify({ ...draft("a1"), sent: [3] }),
    ];
    for (const value of broken) {
      store.set("canvas-draft:a1", value);
      expect(readDraft("a1")).toBeNull();
    }
  });

  it("removes the draft once the text is back to its base", () => {
    writeDraft(draft("a1"));

    expect(writeDraft(draft("a1", { text: "base" }))).toBe(true);
    expect(store.has("canvas-draft:a1")).toBe(false);
  });

  it("keeps a draft back at its base while a save it sent may still land", () => {
    expect(writeDraft(draft("a1", { text: "base", sent: [textKey("base and more")] }))).toBe(true);

    expect(readDraft("a1")?.sent).toEqual([textKey("base and more")]);
  });

  it("names a text by its length and a hash, the same for the same words only", () => {
    expect(textKey("base and more")).toBe(textKey("base and more"));
    expect(textKey("base and more")).toMatch(/^13:\d+$/);
    expect(new Set(["ab", "ba", "abc", "", "Ghi chú", "Ghi chu"].map(textKey)).size).toBe(6);
  });

  it("removes the older draft before writing, so a full quota leaves none behind", () => {
    writeDraft(draft("a1", { text: "older words" }));
    fullStorage(store);

    expect(writeDraft(draft("a1", { text: "newer words" }))).toBe(false);
    expect(store.has("canvas-draft:a1")).toBe(false);
  });

  it("keeps nothing and says so where the browser refuses storage", () => {
    refusingStorage();

    expect(writeDraft(draft("a1"))).toBe(false);
    expect(readDraft("a1")).toBeNull();
  });

  it("clears a draft only while it still holds the text that was saved", () => {
    writeDraft(draft("a1", { text: "saved words" }));

    clearDraft("a1", "other words");
    expect(readDraft("a1")?.text).toBe("saved words");

    clearDraft("a1", "saved words");
    expect(readDraft("a1")).toBeNull();
  });

  it("clears a draft whatever it holds when no text is given", () => {
    writeDraft(draft("a1"));

    clearDraft("a1");
    expect(store.has("canvas-draft:a1")).toBe(false);
  });

  it("keeps the ten newest drafts and drops the oldest", () => {
    for (let n = 1; n <= 11; n++) writeDraft(draft(`a${n}`, { saved_at: NOW + n }));

    expect(store.has("canvas-draft:a1")).toBe(false);
    for (let n = 2; n <= 11; n++) expect(store.has(`canvas-draft:a${n}`)).toBe(true);
  });

  it("spares the draft just written even when this device's clock went back", () => {
    for (let n = 1; n <= 10; n++) writeDraft(draft(`a${n}`, { saved_at: NOW + n }));

    writeDraft(draft("late", { saved_at: NOW - DAY }));

    expect(store.has("canvas-draft:late")).toBe(true);
    expect(store.has("canvas-draft:a1")).toBe(false);
    expect(store.has("canvas-draft:a2")).toBe(true);
  });

  it("drops drafts older than thirty days and broken ones, and leaves other memories alone", () => {
    store.set("canvas-draft:old", JSON.stringify(draft("old", { saved_at: NOW - 31 * DAY })));
    store.set("canvas-draft:recent", JSON.stringify(draft("recent", { saved_at: NOW - 29 * DAY })));
    store.set("canvas-draft:broken", "{not json");
    store.set("composer-draft:c1", "a message being written");

    pruneDrafts(NOW);

    expect([...store.keys()].sort()).toEqual(["canvas-draft:recent", "composer-draft:c1"]);
  });
});
