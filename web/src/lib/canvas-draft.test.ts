import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { askedToStay } from "../test/close-page";
import { fullStorage, limitedStorage, memoryStorage, refusingStorage } from "../test/memory-storage";
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

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

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

  it("says so where the browser refuses storage, and keeps the draft in this tab alone", () => {
    refusingStorage();

    expect(writeDraft(draft("a1"))).toBe(false);
    expect(readDraft("a1")).toEqual(draft("a1"));
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

describe("a draft the browser's quota has no room for", () => {
  /** What a draft takes of the quota: its key and its text. */
  const sizeOf = (d: CanvasDraft) => `canvas-draft:${d.artifact_id}`.length + JSON.stringify(d).length;
  const bulky = (id: string, savedAt: number, chars = 1000) =>
    draft(id, { saved_at: savedAt, text: "x".repeat(chars) });
  const keptKeys = () => [...store.keys()].sort();

  /** Three drafts, the oldest first, with a quota that holds exactly these. */
  function fillQuota(): CanvasDraft[] {
    const drafts = [bulky("a1", NOW + 1), bulky("a2", NOW + 2), bulky("a3", NOW + 3)];
    for (const d of drafts) writeDraft(d);
    limitedStorage(store, drafts.reduce((sum, d) => sum + sizeOf(d), 0));
    return drafts;
  }

  it("frees the oldest other draft, and no more than it takes", () => {
    fillQuota();

    expect(writeDraft(bulky("a4", NOW + 4))).toBe(true);

    expect(keptKeys()).toEqual(["canvas-draft:a2", "canvas-draft:a3", "canvas-draft:a4"]);
    expect(readDraft("a4")?.text).toHaveLength(1000);
  });

  it("frees a second one when the first leaves too little room, and keeps the newest", () => {
    fillQuota();

    expect(writeDraft(bulky("a4", NOW + 4, 1800))).toBe(true);

    expect(keptKeys()).toEqual(["canvas-draft:a3", "canvas-draft:a4"]);
    expect(readDraft("a4")?.text).toHaveLength(1800);
  });

  it("frees what is no draft before any draft", () => {
    const [a1, a2] = [bulky("a1", NOW + 1), bulky("a2", NOW + 2)];
    writeDraft(a1);
    writeDraft(a2);
    store.set("canvas-draft:junk", "j".repeat(1200));
    limitedStorage(store, sizeOf(a1) + sizeOf(a2) + "canvas-draft:junk".length + 1200);

    expect(writeDraft(bulky("a4", NOW + 4))).toBe(true);

    expect(keptKeys()).toEqual(["canvas-draft:a1", "canvas-draft:a2", "canvas-draft:a4"]);
  });

  it("leaves the others as they were when even removing them all would not make room", () => {
    fillQuota();
    const before = Object.fromEntries(store);

    expect(writeDraft(bulky("a9", NOW + 9, 50_000))).toBe(false);

    expect(Object.fromEntries(store)).toEqual(before);
    expect(readDraft("a9")?.text).toHaveLength(50_000);
  });

  it("touches nothing else while the write fits", () => {
    const [a1] = [bulky("a1", NOW + 1)];
    writeDraft(a1);
    limitedStorage(store, 10 * sizeOf(a1));
    const before = Object.fromEntries(store);

    expect(writeDraft(bulky("a2", NOW + 2))).toBe(true);

    expect(keptKeys()).toEqual(["canvas-draft:a1", "canvas-draft:a2"]);
    expect(store.get("canvas-draft:a1")).toBe(before["canvas-draft:a1"]);
  });
});

describe("a draft the browser refused, held in this tab", () => {
  /** The quota is used up, this tab's draft of a1 was refused, and another tab then stored its own. */
  function heldHereStoredElsewhere(): void {
    fullStorage(store);
    writeDraft(draft("a1", { text: "typed here" }));
    store.set("canvas-draft:a1", JSON.stringify(draft("a1", { text: "typed elsewhere" })));
  }

  it("is read before the one another tab stored for the same canvas", () => {
    heldHereStoredElsewhere();

    expect(readDraft("a1")?.text).toBe("typed here");
    expect(readDraft("a2")).toBeNull();
  });

  it("goes once the browser keeps the draft after all", () => {
    refusingStorage();
    writeDraft(draft("a1"));
    store = memoryStorage();

    expect(writeDraft(draft("a1", { text: "base and much more" }))).toBe(true);

    expect(askedToStay()).toBe(false);
    store.delete("canvas-draft:a1");
    expect(readDraft("a1")).toBeNull();
  });

  it("goes once nothing is left to keep, which a browser refusing storage does not make a failure", () => {
    refusingStorage();
    expect(writeDraft(draft("a2", { text: "base" }))).toBe(true);
    writeDraft(draft("a1"));

    expect(writeDraft(draft("a1", { text: "base" }))).toBe(true);

    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("is cleared only while it still holds the text that was saved", () => {
    refusingStorage();
    writeDraft(draft("a1", { text: "saved words" }));

    clearDraft("a1", "other words");
    expect(readDraft("a1")?.text).toBe("saved words");

    clearDraft("a1", "saved words");
    expect(readDraft("a1")).toBeNull();
  });

  it("is cleared for its own text, leaving what another tab stored with other words", () => {
    heldHereStoredElsewhere();

    clearDraft("a1", "typed here");

    expect(readDraft("a1")?.text).toBe("typed elsewhere");
    expect(askedToStay()).toBe(false);
  });

  it("stays when the text saved is the stored one's", () => {
    heldHereStoredElsewhere();

    clearDraft("a1", "typed elsewhere");

    expect(store.has("canvas-draft:a1")).toBe(false);
    expect(readDraft("a1")?.text).toBe("typed here");
  });

  it("is cleared along with the stored one when no text is given", () => {
    heldHereStoredElsewhere();

    clearDraft("a1");

    expect(store.has("canvas-draft:a1")).toBe(false);
    expect(readDraft("a1")).toBeNull();
  });

  it("has the page ask before it closes until the last of them is gone", () => {
    expect(askedToStay()).toBe(false);
    refusingStorage();
    writeDraft(draft("a1"));
    writeDraft(draft("a2"));
    expect(askedToStay()).toBe(true);

    clearDraft("a1");
    expect(askedToStay()).toBe(true);
    clearDraft("a1");
    expect(askedToStay()).toBe(true);

    clearDraft("a2");
    expect(askedToStay()).toBe(false);
  });

  it("asks nothing for a draft the browser keeps", () => {
    writeDraft(draft("a1"));

    expect(askedToStay()).toBe(false);
  });
});

describe("a draft the browser refuses again and again", () => {
  const big = (id: string, chars: number) => draft(id, { text: "x".repeat(chars) });

  /** Two small drafts and a quota with no room for a large one, and how often the browser is asked. */
  function fullWithOthers() {
    writeDraft(draft("a1", { saved_at: NOW + 1 }));
    writeDraft(draft("a2", { saved_at: NOW + 2 }));
    limitedStorage(store, 2000);
    const spies = (["getItem", "setItem", "removeItem", "key"] as const).map((name) => vitest.spyOn(localStorage, name));
    return { asked: () => spies.reduce((sum, spy) => sum + spy.mock.calls.length, 0) };
  }

  it("is tried once for ten pauses in typing, the other canvases' drafts taken out and put back once", () => {
    const { asked } = fullWithOthers();
    const before = Object.fromEntries(store);
    const put = vitest.spyOn(localStorage, "setItem");

    expect(writeDraft(big("a9", 5000))).toBe(false);
    const first = asked();
    for (let n = 1; n < 10; n++) expect(writeDraft(big("a9", 5000 + (n % 2)))).toBe(false);

    expect(asked()).toBe(first);
    expect(put.mock.calls.filter(([key]) => key !== "canvas-draft:a9").map(([key]) => key)).toEqual([
      "canvas-draft:a1",
      "canvas-draft:a2",
    ]);
    expect(Object.fromEntries(store)).toEqual(before);
    // The tab still holds the newest typing.
    expect(readDraft("a9")?.text).toHaveLength(5001);
  });

  it("is tried again once it is smaller", () => {
    const { asked } = fullWithOthers();
    writeDraft(big("a9", 5000));
    const first = asked();

    expect(writeDraft(big("a9", 4999))).toBe(false);
    expect(asked()).toBeGreaterThan(first);

    expect(writeDraft(big("a9", 1000))).toBe(true);
    expect(store.get("canvas-draft:a9")).toContain("x".repeat(1000));
    expect(askedToStay()).toBe(false);
  });

  it("is tried again after a stored draft was cleared, which may have made room", () => {
    fullWithOthers();
    writeDraft(big("a9", 5000));
    limitedStorage(store, 50_000);
    expect(writeDraft(big("a9", 5000))).toBe(false);

    clearDraft("a2");

    expect(writeDraft(big("a9", 5000))).toBe(true);
  });

  it("is not tried again after a draft held in this tab alone was cleared, which made none", () => {
    const { asked } = fullWithOthers();
    writeDraft(big("a9", 5000));

    clearDraft("a9");
    clearDraft("a3");
    const cleared = asked();

    expect(writeDraft(big("a9", 5000))).toBe(false);
    expect(asked()).toBe(cleared);
  });

  it("does not stand in the way of another canvas's draft, however large", () => {
    fullWithOthers();
    writeDraft(big("a9", 5000));
    limitedStorage(store, 50_000);

    expect(writeDraft(big("a8", 6000))).toBe(true);
    expect(store.has("canvas-draft:a8")).toBe(true);
  });

  it("is tried again once the browser stops refusing storage outright, whatever its size", () => {
    refusingStorage();
    expect(writeDraft(big("a9", 5000))).toBe(false);
    store = memoryStorage();

    expect(writeDraft(big("a9", 6000))).toBe(true);
  });

  it("says so in the console when a draft taken out to make room cannot be put back", () => {
    const error = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    writeDraft(draft("a1", { saved_at: NOW + 1 }));
    writeDraft(draft("a2", { saved_at: NOW + 2 }));
    fullStorage(store);

    expect(writeDraft(big("a9", 5000))).toBe(false);

    expect(error.mock.calls.map(([message]) => message)).toEqual([
      expect.stringContaining("canvas-draft:a1"),
      expect.stringContaining("canvas-draft:a2"),
    ]);
  });

  it("says nothing in the console when they go back as they were", () => {
    const error = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    fullWithOthers();

    expect(writeDraft(big("a9", 5000))).toBe(false);

    expect(error).not.toHaveBeenCalled();
  });
});
