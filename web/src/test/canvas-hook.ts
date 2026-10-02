import { act, cleanup, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { vi as vitest } from "vitest";
import { useCanvas } from "../hooks/use-canvas";
import { emitArtifactEvent } from "../lib/artifact-events";
import { FakeBackend } from "./fake-backend";
import { memoryStorage } from "./memory-storage";

/**
 * `useCanvas` on a fake clock, for tests that type, wait and leave at exact moments. The test
 * stubs `fetch` with a `FakeBackend` and fakes `setTimeout` and `Date` only, so promises still
 * settle on their own: a request is recorded the moment it goes out, and its reply arrives at the
 * next `landed()`.
 */

export type CanvasProps = { id: string; connected: boolean };

/** A fresh server, clock and storage for one test, with `fetch` and the stream's events on them. */
export function startServer(): FakeBackend {
  vitest.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  const backend = new FakeBackend();
  backend.canvas.onEvent = emitArtifactEvent;
  memoryStorage();
  vitest.stubGlobal("fetch", backend.fetch);
  return backend;
}

/** Unmounts before the real clock and network come back: leaving may still send a save. */
export function stopServer(): void {
  cleanup();
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
}

/** Mounts the hook on canvas `id`, a1 unless said otherwise, and lets its first read land. */
export async function openCanvas(props: Partial<CanvasProps> = {}, options: { strict?: boolean } = {}) {
  const view = renderHook((p: CanvasProps) => useCanvas(p.id, p.connected), {
    initialProps: { id: "a1", connected: true, ...props },
    wrapper: options.strict ? StrictMode : undefined,
  });
  await landed();
  return view;
}

/** Lets every reply already on its way arrive, without moving the clock. */
export async function landed(): Promise<void> {
  await act(async () => {
    await vitest.advanceTimersByTimeAsync(0);
  });
}

/** Moves the clock by `ms`, firing each timer it passes. */
export function wait(ms: number): void {
  act(() => {
    vitest.advanceTimersByTime(ms);
  });
}

/** What `work` came to, as far as the timers and promises a test has let run so far. */
export function watch<T>(work: Promise<T>) {
  const seen: { settled: boolean; value?: T } = { settled: false };
  void work.then(
    (value) => Object.assign(seen, { settled: true, value }),
    () => Object.assign(seen, { settled: true }),
  );
  return seen;
}

/** The tab hides or shows. */
export function setVisibility(state: DocumentVisibilityState): void {
  vitest.spyOn(document, "visibilityState", "get").mockReturnValue(state);
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

/** The requests sent to canvas `id` with `method`, oldest first. */
export function sent(backend: FakeBackend, method: "GET" | "PUT", id = "a1") {
  return backend.requests.filter((request) => request.method === method && request.path === `/artifacts/${id}`);
}
