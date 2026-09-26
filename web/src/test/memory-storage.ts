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
  });
}
