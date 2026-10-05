import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { LIVE_PREVIEW_KEY as KEY, freshLivePreview } from "../test/live-preview";
import { fullStorage, memoryStorage, refusingStorage } from "../test/memory-storage";
import { useLivePreview } from "./use-live-preview";

let store: Map<string, string>;

beforeEach(() => {
  store = freshLivePreview();
});

afterEach(() => {
  cleanup();
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
});

const use = () => renderHook(() => useLivePreview());
type View = ReturnType<typeof use>;

const choose = (view: View, enabled: boolean) => act(() => view.result.current.set(enabled));
const read = (view: View) => ({ enabled: view.result.current.enabled, tabOnly: view.result.current.tabOnly });

/** Another tab changed the stored choice, which this one hears of as a `storage` event. */
function fromAnotherTab(word: string | null) {
  act(() => {
    if (word === null) store.delete(KEY);
    else store.set(KEY, word);
    window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
  });
}

describe("whether a canvas being written is shown on this device", () => {
  it("is on, with nothing stored, until the person says otherwise", () => {
    expect(read(use())).toEqual({ enabled: true, tabOnly: false });
    expect(store.size).toBe(0);
  });

  it("stores the one word off when it is turned off, and nothing else", () => {
    const view = use();

    choose(view, false);

    expect(read(view)).toEqual({ enabled: false, tabOnly: false });
    expect([...store]).toEqual([[KEY, "off"]]);
  });

  it("is off on a page that finds the word stored, and stores nothing once turned on again", () => {
    store.set(KEY, "off");
    const view = use();
    expect(read(view)).toEqual({ enabled: false, tabOnly: false });

    choose(view, true);

    expect(read(view)).toEqual({ enabled: true, tabOnly: false });
    expect(store.size).toBe(0);
  });

  it.each(["on", "OFF", "", "false"])("stays on over a stored word that is not off: %j", (word) => {
    store.set(KEY, word);

    expect(read(use()).enabled).toBe(true);
  });

  it("is one choice for everything in the tab that reads it", () => {
    const setting = use();
    const chat = use();

    choose(setting, false);
    expect(read(chat)).toEqual({ enabled: false, tabOnly: false });

    choose(chat, true);
    expect(read(setting)).toEqual({ enabled: true, tabOnly: false });
  });

  it("follows the choice made in another tab", () => {
    const view = use();

    fromAnotherTab("off");
    expect(read(view).enabled).toBe(false);

    fromAnotherTab(null);
    expect(read(view).enabled).toBe(true);
  });

  it("stops listening for other tabs once nothing reads it", () => {
    const added = vitest.spyOn(window, "addEventListener");
    const removed = vitest.spyOn(window, "removeEventListener");
    const heard = (spy: typeof added | typeof removed) =>
      spy.mock.calls.filter(([type]) => type === "storage").map(([, listener]) => listener);
    const view = use();
    expect(heard(added).length).toBeGreaterThan(0);
    expect(heard(removed)).toEqual([]);

    view.unmount();

    expect(heard(removed)).toEqual(heard(added));
  });
});

describe("a choice the browser will not store", () => {
  it("is taken all the same, and is said to be the tab's alone", () => {
    refusingStorage();
    const view = use();
    expect(read(view)).toEqual({ enabled: true, tabOnly: false });

    choose(view, false);
    expect(read(view)).toEqual({ enabled: false, tabOnly: true });

    choose(view, true);
    expect(read(view)).toEqual({ enabled: true, tabOnly: true });
  });

  it("is there for whatever reads it next in the tab", () => {
    refusingStorage();
    const setting = use();
    choose(setting, false);
    setting.unmount();

    expect(read(use())).toEqual({ enabled: false, tabOnly: true });
  });

  it("outranks what the browser has stored, which the tab could not change", () => {
    fullStorage(store);
    const view = use();

    choose(view, false);
    expect(store.size).toBe(0);
    expect(read(view)).toEqual({ enabled: false, tabOnly: true });

    fromAnotherTab(null);
    expect(read(view)).toEqual({ enabled: false, tabOnly: true });
  });

  it("is let go once the browser stores a choice again", () => {
    fullStorage(store);
    const view = use();
    choose(view, false);

    // A full store still forgets: turning it on again removes the word, which needs no room.
    choose(view, true);
    expect(read(view)).toEqual({ enabled: true, tabOnly: false });

    store = memoryStorage();
    choose(view, false);
    expect(read(view)).toEqual({ enabled: false, tabOnly: false });
    expect([...store]).toEqual([[KEY, "off"]]);
  });
});
