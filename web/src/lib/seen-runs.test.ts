import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";

const KEY = "attention.seen";
let store: Map<string, string>;

function memoryStorage() {
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    clear: () => store.clear(),
  });
}

function refusedStorage() {
  const refuse = () => {
    throw new DOMException("denied", "SecurityError");
  };
  vitest.stubGlobal("localStorage", { getItem: refuse, setItem: refuse, clear: refuse });
}

/** A fresh copy of the module, as a new page load would see it. */
async function freshStore() {
  vitest.resetModules();
  return import("./seen-runs");
}

beforeEach(() => {
  store = new Map();
  memoryStorage();
});

afterEach(() => vitest.unstubAllGlobals());

describe("the runs marked as read", () => {
  it("keeps a dismissal past a reload of the page", async () => {
    (await freshStore()).markSeen("r1");

    expect(JSON.parse(store.get(KEY) ?? "null")).toEqual(["r1"]);
    expect((await freshStore()).seenRuns()).toEqual(["r1"]);
  });

  it("keeps only the most recent hundred, so the list cannot grow without end", async () => {
    const { markSeen, seenRuns } = await freshStore();
    for (let i = 0; i < 105; i++) markSeen(`r${i}`);

    expect(seenRuns()).toHaveLength(100);
    expect(seenRuns()[0]).toBe("r5");
    expect(JSON.parse(store.get(KEY) ?? "[]")).toHaveLength(100);
  });

  it("tells subscribers once per new dismissal, and not for one already made", async () => {
    const { markSeen, subscribeSeen } = await freshStore();
    const listener = vitest.fn();
    const stop = subscribeSeen(listener);

    markSeen("r1");
    markSeen("r1");
    stop();
    markSeen("r2");

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("follows a dismissal made in another tab", async () => {
    const { seenRuns, subscribeSeen } = await freshStore();
    expect(seenRuns()).toEqual([]);
    const listener = vitest.fn();
    subscribeSeen(listener);

    store.set(KEY, JSON.stringify(["elsewhere"]));
    window.dispatchEvent(new StorageEvent("storage", { key: KEY }));

    expect(listener).toHaveBeenCalled();
    expect(seenRuns()).toEqual(["elsewhere"]);
  });

  // A private window or blocked site data refuses storage outright; dismissing still has
  // to work for as long as the tab is open.
  it("still dismisses when the browser refuses storage", async () => {
    refusedStorage();
    const { markSeen, seenRuns } = await freshStore();

    expect(seenRuns()).toEqual([]);
    markSeen("r1");

    expect(seenRuns()).toEqual(["r1"]);
  });

  it("starts empty from a value it cannot read", async () => {
    store.set(KEY, "{not json");
    expect((await freshStore()).seenRuns()).toEqual([]);

    store.set(KEY, JSON.stringify({ r1: true }));
    expect((await freshStore()).seenRuns()).toEqual([]);

    store.set(KEY, JSON.stringify(["r1", 7, null]));
    expect((await freshStore()).seenRuns()).toEqual(["r1"]);
  });
});
