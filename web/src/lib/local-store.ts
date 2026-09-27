// This device's small memories: a remembered choice, an unsent draft, what was already seen.
//
// A browser can refuse storage outright (a private window, site data blocked, a full quota),
// and every read and write goes through here so that a refusal means the same thing
// everywhere: nothing is stored, and the page keeps working on its own copy until it reloads.

/** Runs `use` on the storage; a refusal, or a stored value that does not parse, gives `fallback`. */
function attempt<T>(use: (storage: Storage) => T, fallback: T): T {
  try {
    return use(window.localStorage);
  } catch {
    return fallback;
  }
}

/** The text stored under `key`, or null. */
export function readText(key: string): string | null {
  return attempt((storage) => storage.getItem(key), null);
}

/** Stores `text` under `key`; null removes the entry. */
export function writeText(key: string, text: string | null): void {
  attempt((storage) => (text === null ? storage.removeItem(key) : storage.setItem(key, text)), undefined);
}

/** The value stored under `key` as JSON, or null. */
export function readJson(key: string): unknown {
  return attempt((storage) => {
    const raw = storage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as unknown);
  }, null);
}

/** Stores `value` under `key` as JSON. */
export function writeJson(key: string, value: unknown): void {
  attempt((storage) => storage.setItem(key, JSON.stringify(value)), undefined);
}
