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

/** Stores `text` under `key`; null removes the entry. False when the browser refused. */
export function writeText(key: string, text: string | null): boolean {
  return attempt((storage) => {
    if (text === null) storage.removeItem(key);
    else storage.setItem(key, text);
    return true;
  }, false);
}

/** The value stored under `key` as JSON, or null. */
export function readJson(key: string): unknown {
  return attempt((storage) => {
    const raw = storage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as unknown);
  }, null);
}

/** Stores `value` under `key` as JSON. False when the browser refused. */
export function writeJson(key: string, value: unknown): boolean {
  return attempt((storage) => {
    storage.setItem(key, JSON.stringify(value));
    return true;
  }, false);
}

/** Every stored key that starts with `prefix`; none when storage is refused. */
export function keys(prefix: string): string[] {
  return attempt((storage) => {
    const found: string[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key !== null && key.startsWith(prefix)) found.push(key);
    }
    return found;
  }, []);
}
