import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { inboxReadAt, markInboxRead, resetInboxRead, subscribeInboxRead } from "./inbox-read";

function memoryStorage(refuse = false) {
  const store = new Map<string, string>();
  const no = () => {
    throw new Error("refused");
  };
  vitest.stubGlobal("localStorage", {
    getItem: refuse ? no : (k: string) => store.get(k) ?? null,
    setItem: refuse ? no : (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
  return store;
}

beforeEach(() => resetInboxRead());
afterEach(() => vitest.unstubAllGlobals());

describe("when the inbox was last read", () => {
  it("is never at first, then the moment it was read, kept for the next page load", () => {
    const store = memoryStorage();
    expect(inboxReadAt()).toBeNull();
    markInboxRead("2026-11-01T02:00:00.000Z");
    expect(inboxReadAt()).toBe("2026-11-01T02:00:00.000Z");
    resetInboxRead();
    expect(store.get("inbox.readAt")).toBe("2026-11-01T02:00:00.000Z");
    expect(inboxReadAt()).toBe("2026-11-01T02:00:00.000Z");
  });

  // Another tab may have read it later; a slow tab closing must not wind that back.
  it("never moves back to an earlier moment", () => {
    memoryStorage();
    markInboxRead("2026-11-01T03:00:00.000Z");
    markInboxRead("2026-11-01T02:00:00.000Z");
    expect(inboxReadAt()).toBe("2026-11-01T03:00:00.000Z");
  });

  it("tells its subscribers, and still holds in the tab when storage is refused", () => {
    memoryStorage(true);
    const heard = vitest.fn();
    const stop = subscribeInboxRead(heard);
    markInboxRead("2026-11-01T02:00:00.000Z");
    expect(heard).toHaveBeenCalledTimes(1);
    expect(inboxReadAt()).toBe("2026-11-01T02:00:00.000Z");
    stop();
  });
});
