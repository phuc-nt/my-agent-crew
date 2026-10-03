import { vi as vitest } from "vitest";

const quotaError = () => new DOMException("The quota has been exceeded.", "QuotaExceededError");

/** Stubs `localStorage` over `store`, whose writes go through `setItem`. */
function stub(store: Map<string, string>, setItem: (key: string, value: string) => void): void {
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem,
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  });
}

/**
 * A `localStorage` the test owns. Node exposes its own only when started with
 * --localstorage-file, so a test that reads back what a component remembered brings one.
 */
export function memoryStorage(): Map<string, string> {
  const store = new Map<string, string>();
  stub(store, (k, v) => void store.set(k, String(v)));
  return store;
}

/** A browser that refuses storage outright: a private window, or site data blocked. */
export function refusingStorage(): void {
  const refuse = () => {
    throw new DOMException("The operation is insecure.", "SecurityError");
  };
  vitest.stubGlobal("localStorage", {
    getItem: refuse,
    setItem: refuse,
    removeItem: refuse,
    clear: refuse,
    key: refuse,
    get length(): number {
      return refuse();
    },
  });
}

/** A browser whose quota is used up: a write fails, while reading and removing still work. */
export function fullStorage(store: Map<string, string>): void {
  stub(store, () => {
    throw quotaError();
  });
}

/** A browser whose quota holds `limit` characters, keys and values together: a write that would pass
 *  it fails, and one that replaces a key counts only what it adds. Reading and removing still work. */
export function limitedStorage(store: Map<string, string>, limit: number): void {
  const size = (k: string, v: string | undefined) => (v === undefined ? 0 : k.length + v.length);
  const used = () => [...store].reduce((sum, [k, v]) => sum + size(k, v), 0);
  stub(store, (k, v) => {
    const value = String(v);
    if (used() - size(k, store.get(k)) + size(k, value) > limit) throw quotaError();
    store.set(k, value);
  });
}
