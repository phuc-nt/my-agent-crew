import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { saveBody } from "../api/artifact-client";
import type { CanvasSeed } from "../test/fake-canvas";
import { FakeBackend } from "../test/fake-backend";
import { memoryStorage } from "../test/memory-storage";
import { readDraft } from "./canvas-draft";
import { type HandoffFailure, KEEPALIVE_MAX, onHandoffFailed, saveInBackground, withKeepalive } from "./canvas-handoff";
import { openState } from "./canvas-machine";
import { CanvasRunner } from "./canvas-runner";

let backend: FakeBackend;
let heard: HandoffFailure[];
let unsubscribe: () => void;

beforeEach(() => {
  backend = new FakeBackend();
  memoryStorage();
  vitest.stubGlobal("fetch", backend.fetch);
  heard = [];
  unsubscribe = onHandoffFailed((failure) => heard.push(failure));
});

afterEach(() => {
  unsubscribe();
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
});

const puts = () => backend.requests.filter((request) => request.method === "PUT");

/** A runner on canvas a1, "a" at v1 unless `seed` says otherwise, once its first read landed. */
async function opened(seed: CanvasSeed = {}): Promise<CanvasRunner> {
  backend.canvas.add({ content: "a", ...seed });
  const runner = new CanvasRunner("a1", () => {});
  runner.start();
  await vitest.waitFor(() => expect(runner.state.phase).toBe("ready"));
  return runner;
}

describe("the last save of a canvas the person left", () => {
  it("counts the person's own save as saved when the retry meets the one whose reply was lost", async () => {
    const runner = await opened();
    runner.edit("ab");
    backend.canvas.loseNext("PUT");
    expect(await runner.flush()).toBeNull();

    runner.detach();
    await saveInBackground(runner);

    expect(heard).toEqual([]);
    expect(readDraft("a1")).toBeNull();
    expect(backend.canvas.content("a1")).toBe("ab");
    expect(puts()).toHaveLength(2);
  });

  it("keeps the draft and says so when the save fails, and tries no more once the panel is gone", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    const runner = await opened({ title: "Ghi chú" });
    runner.edit("a!");
    runner.detach();
    backend.canvas.refuseNext("PUT", 503);

    await saveInBackground(runner);

    expect(heard).toEqual([{ id: "a1", title: "Ghi chú" }]);
    expect(readDraft("a1")?.text).toBe("a!");
    await vitest.advanceTimersByTimeAsync(60_000);
    expect(puts()).toHaveLength(1);
  });

  it("sends what was typed after the save in flight once that save lands", async () => {
    const runner = await opened();
    const release = backend.canvas.holdNext("PUT", "reply");
    runner.edit("ab");
    runner.send({ type: "saveDue", reason: "manual" });
    runner.edit("abc");

    runner.detach();
    const done = saveInBackground(runner);
    await release();
    await done;

    expect(heard).toEqual([]);
    expect(puts().map((request) => request.body)).toEqual([
      { content: "ab", base_version: 1 },
      { content: "abc", base_version: 2 },
    ]);
    expect(backend.canvas.content("a1")).toBe("abc");
    expect(readDraft("a1")).toBeNull();
  });

  it("tells only the listeners still subscribed, with no title when it never had one", async () => {
    const leaving = { id: "a9", state: openState("a9", null), flush: async () => null };

    await saveInBackground(leaving);
    unsubscribe();
    await saveInBackground(leaving);

    expect(heard).toEqual([{ id: "a9", title: null }]);
  });
});

describe("the keepalive budget", () => {
  const asked = (content: string, hidden = true) =>
    withKeepalive(hidden, content, 1, async (keepalive) => keepalive);

  it("keeps a body alive up to its cap in bytes, and no larger", async () => {
    const room = KEEPALIVE_MAX - saveBody("", 1).length;

    expect(await asked("x".repeat(room))).toBe(true);
    expect(await asked("x".repeat(room + 1))).toBe(false);
    // Two bytes each: few enough characters for the cap, too many bytes.
    expect(await asked("é".repeat(Math.floor(room / 2) + 1))).toBe(false);
    expect(await asked("é".repeat(Math.floor(room / 2)))).toBe(true);
  });

  it("sends a plain request while the page is visible", async () => {
    expect(await asked("a", false)).toBe(false);
  });

  it("keeps one save alive at a time, and the next once the first has landed", async () => {
    let land = () => {};
    const first = withKeepalive(true, "a", 1, (keepalive) => new Promise<boolean>((resolve) => {
      land = () => resolve(keepalive);
    }));

    expect(await asked("b")).toBe(false);
    land();
    expect(await first).toBe(true);
    expect(await asked("c")).toBe(true);
  });

  it("frees the budget when a kept-alive save fails", async () => {
    const failed = withKeepalive(true, "a", 1, async () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(failed).rejects.toThrow("Failed to fetch");
    expect(await asked("b")).toBe(true);
  });
});
