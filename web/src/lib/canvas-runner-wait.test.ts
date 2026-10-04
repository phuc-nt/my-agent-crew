import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import type { CanvasSeed } from "../test/fake-canvas";
import { slowUploads } from "../test/slow-link";
import { CanvasRunner } from "./canvas-runner";

const MB = 1024 * 1024;

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

/** A runner on canvas a1, "a" at v1 unless `seed` says otherwise, once its first read landed. */
async function opened(seed: CanvasSeed = {}): Promise<CanvasRunner> {
  backend.canvas.add({ content: "a", ...seed });
  const runner = new CanvasRunner("a1", () => {});
  runner.start();
  await landed();
  expect(runner.state.phase).toBe("ready");
  return runner;
}

const save = (runner: CanvasRunner) => runner.send({ type: "saveDue", reason: "manual" });

describe("how long the save in flight may still go unanswered", () => {
  it("is nothing while no save is out, whatever has been typed", async () => {
    const runner = await opened();
    expect(runner.waitMs()).toBe(0);
    expect(runner.waitMs(true)).toBe(0);

    runner.edit("ab");

    expect(runner.waitMs()).toBe(0);
    expect(runner.waitMs(true)).toBe(0);
  });

  it("is the whole deadline as the save goes out, and less as time passes", async () => {
    const runner = await opened();
    backend.canvas.holdNext("PUT");
    runner.edit("ab");

    save(runner);
    expect(runner.waitMs()).toBe(30_001);

    wait(10_000);
    expect(runner.waitMs()).toBe(20_001);
  });

  it("is longer for a bigger save, which the link has more to carry", async () => {
    const runner = await opened({ kind: "html", content: "<p>a</p>" });
    backend.canvas.holdNext("PUT");
    runner.edit("x".repeat(3 * 1024 * 1024));

    save(runner);

    expect(runner.waitMs()).toBe(91_441);
  });

  it("is nothing again once the save has landed", async () => {
    const runner = await opened();
    runner.edit("ab");
    save(runner);
    expect(runner.waitMs()).toBeGreaterThan(0);
    expect(runner.waitMs(true)).toBeGreaterThan(0);

    await landed();

    expect(runner.state.saving).toBeNull();
    expect(runner.waitMs()).toBe(0);
    expect(runner.waitMs(true)).toBe(0);
  });

  it("is nothing, never less, when the clock jumped past the deadline before its timer ran", async () => {
    const runner = await opened();
    backend.canvas.holdNext("PUT");
    runner.edit("ab");
    save(runner);

    // A tab put to sleep wakes with its timers still waiting: the clock is over the deadline and
    // the save has not been counted as slow yet.
    vitest.setSystemTime(Date.now() + 31_000);

    expect(runner.state.saving).not.toBeNull();
    expect(runner.waitMs()).toBe(0);
  });

  it("is nothing once the deadline has passed without a reply, the save counted as slow", async () => {
    const runner = await opened();
    backend.canvas.holdNext("PUT");
    runner.edit("ab");
    save(runner);

    wait(30_000);
    expect(runner.waitMs()).toBe(1);
    wait(1);
    await landed();

    expect(runner.state.saving).toBeNull();
    expect(runner.state.slow).toBe(true);
    expect(runner.waitMs()).toBe(0);
  });
});

describe("a save the link was too slow for", () => {
  /** A 4 MB page typed into an html canvas and sent, its save still out. */
  async function bigSaveOut(): Promise<CanvasRunner> {
    const runner = await opened({ kind: "html", content: "<p>a</p>" });
    runner.edit("x".repeat(4 * MB));
    save(runner);
    return runner;
  }

  /** The save out gets no reply by its deadline, and the next one goes out `retryMs` later. */
  async function timesOut(runner: CanvasRunner, retryMs: number): Promise<void> {
    wait(runner.waitMs());
    await landed();
    expect(runner.state.slow).toBe(true);
    wait(retryMs);
    await landed();
  }

  it("gets through in the end with nobody touching the canvas: 4 MB over a link that takes 150 seconds", async () => {
    const runner = await opened({ kind: "html", content: "<p>a</p>" });
    const page = "x".repeat(4 * MB);
    slowUploads(150_000);
    runner.edit(page);
    save(runner);
    expect(runner.waitMs()).toBe(111_921);

    // Ten minutes, a second at a time, so that a reply and a deadline never share a step.
    for (let second = 0; second < 600; second++) {
      wait(1000);
      await landed();
    }

    // Compared outside `expect`, which would print all 4 MB of a page that did not arrive.
    expect(backend.canvas.content("a1") === page).toBe(true);
    expect(runner.state.base.version).toBe(2);
    expect(runner.state.failures).toBe(0);
    expect(runner.waitMs()).toBe(0);
  });

  it("may go unanswered for twice the time its body needs when it is sent again, and waitMs says so", async () => {
    backend.canvas.holdNext("PUT");
    const runner = await bigSaveOut();
    expect(runner.waitMs()).toBe(111_921);
    backend.canvas.holdNext("PUT");

    await timesOut(runner, 2_000);

    expect(runner.waitMs()).toBe(193_842);
    // Past the first deadline the save is still inside its own: nothing calls it slow yet.
    wait(111_921);
    await landed();
    expect(runner.state.saving).not.toBeNull();
    expect(runner.waitMs()).toBe(81_921);
  });

  it("is given twice as long again after a second one in a row", async () => {
    backend.canvas.holdNext("PUT");
    const runner = await bigSaveOut();
    backend.canvas.holdNext("PUT");
    await timesOut(runner, 2_000);
    backend.canvas.holdNext("PUT");

    await timesOut(runner, 5_000);

    expect(runner.waitMs()).toBe(357_683);
    expect(runner.waitMs(true)).toBe(111_921);
  });

  it("has, for a message, only what is left of the deadline it was first given, however long its own has grown", async () => {
    backend.canvas.holdNext("PUT");
    const runner = await bigSaveOut();
    expect(runner.waitMs(true)).toBe(111_921);
    backend.canvas.holdNext("PUT");

    await timesOut(runner, 2_000);
    expect(runner.waitMs()).toBe(193_842);
    expect(runner.waitMs(true)).toBe(111_921);

    // Counted from when this save went out, as its own deadline is.
    wait(100_000);
    expect(runner.waitMs(true)).toBe(11_921);
    wait(11_921);
    await landed();

    // The save is still out and inside its own deadline: a message waits on it no more.
    expect(runner.state.saving).not.toBeNull();
    expect(runner.waitMs()).toBe(81_921);
    expect(runner.waitMs(true)).toBe(0);
    wait(50_000);
    expect(runner.waitMs(true)).toBe(0);
  });

  it("is back to the first deadline once a save has landed", async () => {
    backend.canvas.holdNext("PUT");
    const runner = await bigSaveOut();
    await timesOut(runner, 2_000);
    expect(runner.state.base.version).toBe(2);
    backend.canvas.holdNext("PUT");

    runner.edit("y".repeat(4 * MB));
    save(runner);

    expect(runner.waitMs()).toBe(111_921);
  });

  it("keeps the longer deadline through a save the server refused: only one that lands resets it", async () => {
    backend.canvas.holdNext("PUT");
    const runner = await bigSaveOut();
    backend.canvas.refuseNext("PUT", 500);
    await timesOut(runner, 2_000);
    expect(runner.state.slow).toBe(false);
    backend.canvas.holdNext("PUT");

    wait(5_000);
    await landed();

    expect(runner.waitMs()).toBe(193_842);
  });

  it("is not given more time after saves that were lost or refused: the link was not what was slow", async () => {
    backend.canvas.loseNext("PUT");
    const runner = await bigSaveOut();
    await landed();
    backend.canvas.refuseNext("PUT", 500);
    wait(2_000);
    await landed();
    expect(runner.state.failures).toBe(2);
    backend.canvas.holdNext("PUT");

    wait(5_000);
    await landed();

    expect(runner.state.saving).not.toBeNull();
    expect(runner.waitMs()).toBe(111_921);
  });

  it("still has half a minute when it is small: only the time for its body grows", async () => {
    const runner = await opened();
    backend.canvas.holdNext("PUT");
    runner.edit("ab");
    save(runner);
    expect(runner.waitMs()).toBe(30_001);
    backend.canvas.holdNext("PUT");

    await timesOut(runner, 2_000);

    expect(runner.waitMs()).toBe(30_002);
  });
});
