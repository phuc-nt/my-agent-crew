import { vi as vitest } from "vitest";

/**
 * A `localStorage` the test owns. Node exposes its own only when started with
 * --localstorage-file, so a test that reads back what a component remembered brings one.
 */
export function memoryStorage(): Map<string, string> {
  const store = new Map<string, string>();
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  });
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
  vitest.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: () => {
      throw new DOMException("The quota has been exceeded.", "QuotaExceededError");
    },
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: (i: number) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  });
}
