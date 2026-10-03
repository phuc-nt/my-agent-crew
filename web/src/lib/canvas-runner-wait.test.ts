import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import type { CanvasSeed } from "../test/fake-canvas";
import { CanvasRunner } from "./canvas-runner";

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

    runner.edit("ab");

    expect(runner.waitMs()).toBe(0);
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

    await landed();

    expect(runner.state.saving).toBeNull();
    expect(runner.waitMs()).toBe(0);
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
