import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { saveBody } from "../api/artifact-client";
import { leftCanvas } from "../test/canvas-left";
import { askedToStay } from "../test/close-page";
import { FakeBackend } from "../test/fake-backend";
import type { CanvasSeed } from "../test/fake-canvas";
import { memoryStorage, refusingStorage } from "../test/memory-storage";
import { readDraft, writeDraft } from "./canvas-draft";
import { type HandoffFailure, KEEPALIVE_MAX, onHandoffFailed, saveInBackground, withKeepalive } from "./canvas-handoff";
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

    expect(heard).toEqual([{ id: "a1", title: "Ghi chú", draft: true }]);
    expect(readDraft("a1")?.text).toBe("a!");
    await vitest.advanceTimersByTimeAsync(60_000);
    expect(puts()).toHaveLength(1);
  });

  // The person deleted the canvas themselves: a save that finds it gone has failed at nothing.
  it("says nothing and keeps no draft when the canvas was deleted before its last save got there", async () => {
    const runner = await opened({ title: "Ghi chú" });
    runner.edit("a!");
    runner.detach();
    expect(readDraft("a1")?.text).toBe("a!");
    backend.canvas.remove("a1");

    await saveInBackground(runner);

    expect(puts()).toHaveLength(1);
    expect(runner.state.gone).toBe(true);
    expect(heard).toEqual([]);
    expect(readDraft("a1")).toBeNull();
  });

  // A draft this tab alone holds goes the same way, and with it the question before the page closes.
  it("lets go of words only this tab held for a canvas deleted before its last save got there", async () => {
    const runner = await opened();
    refusingStorage();
    runner.edit("a!");
    runner.detach();
    expect(runner.draftFailed).toBe(true);
    backend.canvas.remove("a1");

    await saveInBackground(runner);

    expect(heard).toEqual([]);
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
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
    const leaving = leftCanvas("a9", async () => null);

    await saveInBackground(leaving);
    unsubscribe();
    await saveInBackground(leaving);

    expect(heard).toEqual([{ id: "a9", title: null, draft: true }]);
  });
});

/** A canvas left behind whose save stays out until `land` is called. */
function stuck(id: string, draftFailed: boolean) {
  let land: (version: number | null) => void = () => undefined;
  const done = saveInBackground(
    leftCanvas(id, () => new Promise<number | null>((resolve) => (land = resolve)), { draftFailed }),
  );
  return { done, land: (version: number | null) => land(version) };
}

describe("a canvas left behind whose draft this device could not keep", () => {
  it("asks before the page closes while its last save is out, and stops when it lands", async () => {
    const left = stuck("a1", true);
    expect(askedToStay()).toBe(true);

    left.land(3);
    await left.done;

    expect(askedToStay()).toBe(false);
  });

  it("asks nothing for a canvas whose draft is kept", async () => {
    const left = stuck("a1", false);
    expect(askedToStay()).toBe(false);

    left.land(3);
    await left.done;
  });

  it("asks until the last of them has settled", async () => {
    const first = stuck("a1", true);
    const second = stuck("a2", true);

    first.land(1);
    await first.done;
    expect(askedToStay()).toBe(true);

    second.land(1);
    await second.done;
    expect(askedToStay()).toBe(false);
  });

  it("stops asking when the save fails, and says no draft was kept", async () => {
    const left = stuck("a1", true);

    left.land(null);
    await left.done;

    expect(askedToStay()).toBe(false);
    expect(heard).toEqual([{ id: "a1", title: null, draft: false }]);
  });

  it("stops asking when the save crashes", async () => {
    const done = saveInBackground(leftCanvas("a1", () => Promise.reject(new Error("boom")), { draftFailed: true }));

    await expect(done).rejects.toThrow("boom");

    expect(askedToStay()).toBe(false);
  });

  it("is a runner whose draft the browser refused: this tab holds its text, and the page goes on asking", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    const runner = await opened({ title: "Ghi chú" });
    refusingStorage();
    runner.edit("a!");
    runner.detach();
    expect(runner.draftFailed).toBe(true);
    backend.canvas.refuseNext("PUT", 503);

    const done = saveInBackground(runner);
    expect(askedToStay()).toBe(true);
    await done;

    expect(heard).toEqual([{ id: "a1", title: "Ghi chú", draft: false }]);
    expect(readDraft("a1")?.text).toBe("a!");
    expect(askedToStay()).toBe(true);
  });
});

describe("the draft of a canvas whose last save landed", () => {
  const BASE = "one\ntwo\nthree\nfour\nfive";
  const MINE = "ONE\ntwo\nthree\nfour\nfive";
  const THEIRS = "one\ntwo\nthree\nfour\nFIVE";
  const MERGED = "ONE\ntwo\nthree\nfour\nFIVE";

  it("goes when the version holds it merged with someone else's, in words the draft never had", async () => {
    const runner = await opened({ content: BASE });
    refusingStorage();
    runner.edit(MINE);
    runner.detach();
    backend.canvas.write("a1", THEIRS);

    await saveInBackground(runner);

    expect(heard).toEqual([]);
    expect(backend.canvas.content("a1")).toBe(MERGED);
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("stays when the person has typed more in the canvas since, opened again", async () => {
    const runner = await opened();
    const release = backend.canvas.holdNext("PUT", "reply");
    runner.edit("ab");
    runner.detach();
    const done = saveInBackground(runner);
    writeDraft({ artifact_id: "a1", base_version: 1, base: "a", text: "abc", saved_at: Date.now(), sent: [] });

    await release();
    await done;

    expect(backend.canvas.content("a1")).toBe("ab");
    expect(readDraft("a1")?.text).toBe("abc");
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
