import { vi as vitest } from "vitest";

/**
 * A link that takes `ms` to carry a save to the server: a PUT reaches it only then, and one given
 * up on before that never does. Call it after `startServer()`, whose clock and `fetch` it runs on;
 * `stopServer()` takes it away again.
 */
export function slowUploads(ms: number): void {
  const reach = globalThis.fetch;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit = {}) => {
    if (init.method === "PUT") await carried(ms, init.signal);
    return reach(input, init);
  });
}

/** Resolves `ms` from now, unless `signal` gives up first. */
function carried(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}
