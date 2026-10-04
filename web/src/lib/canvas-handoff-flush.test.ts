import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { watch } from "../test/canvas-hook";
import { type LeftCanvas, leftCanvas } from "../test/canvas-left";
import { flushAll, handoffOut, handoffsSettled, saveInBackground, within } from "./canvas-handoff";

const outstanding: Array<() => void> = [];

beforeEach(() => vitest.useFakeTimers());

// The saves out are module state: one left out would hold up every later wait in this file.
afterEach(async () => {
  vitest.useRealTimers();
  for (const land of outstanding.splice(0)) land();
  await handoffsSettled();
});

/** A save in the background that stays out until the test lets it land; `over` says what its canvas
 *  reports, such as how long its save may still go unanswered. */
function leaving(id = "a1", over: Partial<LeftCanvas> = {}) {
  let land: (version: number | null) => void = () => undefined;
  const flush = () => new Promise<number | null>((resolve) => (land = resolve));
  saveInBackground(leftCanvas(id, flush, over));
  outstanding.push(() => land(1));
  return { land: (version: number | null) => land(version) };
}

const settle = () => vitest.advanceTimersByTimeAsync(0);

describe("handoffsSettled", () => {
  it("answers at once when no save is out", async () => {
    await expect(handoffsSettled()).resolves.toBeUndefined();
  });

  it("waits for every save out, those that failed or crashed included", async () => {
    const slow = leaving("a1");
    const failed = leaving("a2");
    const crashed = saveInBackground(leftCanvas("a3", () => Promise.reject(new Error("boom"))));
    const waiting = watch(handoffsSettled());

    await settle();
    expect(waiting.settled).toBe(false);
    failed.land(null);
    await settle();
    expect(waiting.settled).toBe(false);
    slow.land(3);
    await settle();

    expect(waiting.settled).toBe(true);
    await expect(crashed).rejects.toThrow("boom");
  });

  it("does not wait for a save that starts after it was asked", async () => {
    const early = leaving("a1");
    const waiting = watch(handoffsSettled());
    leaving("a2");

    early.land(1);
    await settle();

    expect(waiting.settled).toBe(true);
  });
});

describe("handoffOut", () => {
  it("is true of a canvas whose save left behind is still out, and of no other", async () => {
    leaving("a1");

    expect(handoffOut("a1")).toBe(true);
    expect(handoffOut("a2")).toBe(false);
  });

  it.each<[string, number | null]>([
    ["landed", 3],
    ["failed", null],
  ])("is false again once that save has %s", async (_name, version) => {
    const first = leaving("a1");
    leaving("a2");

    first.land(version);
    await settle();

    expect(handoffOut("a1")).toBe(false);
    expect(handoffOut("a2")).toBe(true);
  });
});

describe("within", () => {
  it("answers what the work gave when it settles in time, and clears its timer", async () => {
    expect(await within(100, Promise.resolve("done"), "late")).toBe("done");
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("answers the late value once the time is up, and not before", async () => {
    const answer = watch(within(100, new Promise<string>(() => undefined), "late"));

    await vitest.advanceTimersByTimeAsync(99);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: "late" });
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("passes the work's failure on, and clears its timer", async () => {
    await expect(within(100, Promise.reject(new Error("boom")), "late")).rejects.toThrow("boom");
    expect(vitest.getTimerCount()).toBe(0);
  });
});

describe("flushAll", () => {
  it("answers the version the panel's save landed once every save out is done", async () => {
    const out = leaving();
    const answer = watch(flushAll(5000, Promise.resolve(7)));

    await vitest.advanceTimersByTimeAsync(4000);
    expect(answer.settled).toBe(false);
    out.land(2);
    await settle();

    expect(answer).toEqual({ settled: true, value: 7 });
  });

  it("keeps the panel's version when a save out has not landed by the cap", async () => {
    leaving();
    const answer = watch(flushAll(5000, Promise.resolve(7)));

    await vitest.advanceTimersByTimeAsync(4999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: 7 });
  });

  it("waits for the panel and the saves out under one cap, answering null when the panel is not in", async () => {
    leaving();
    const answer = watch(flushAll(5000, new Promise<number | null>(() => undefined)));

    await vitest.advanceTimersByTimeAsync(4999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: null });
  });

  it.each<[string, () => Promise<number | null>]>([
    ["landed nothing", () => Promise.resolve(null)],
    ["failed", () => Promise.reject(new Error("boom"))],
  ])("answers null when the panel's save %s", async (_name, save) => {
    await expect(flushAll(5000, save())).resolves.toBeNull();
  });

  it("waits only for the saves out when there is no panel, and answers null", async () => {
    const out = leaving();
    const answer = watch(flushAll(5000, null));

    await vitest.advanceTimersByTimeAsync(1000);
    expect(answer.settled).toBe(false);
    out.land(1);
    await settle();

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("gives up on the saves out at the cap when there is no panel", async () => {
    leaving();
    const answer = watch(flushAll(5000, null));

    await vitest.advanceTimersByTimeAsync(5000);

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("clears its timer once everything is in", async () => {
    await flushAll(5000, Promise.resolve(1));
    expect(vitest.getTimerCount()).toBe(0);
  });
});

describe("flushAll while a save is still inside its own deadline", () => {
  const never = () => new Promise<number | null>(() => undefined);

  it("waits for the panel's save as long as it may still go unanswered, on top of the cap", async () => {
    const answer = watch(flushAll(5000, never(), 60_000));

    await vitest.advanceTimersByTimeAsync(64_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("waits for a save left behind as long as it may still go unanswered, on top of the cap", async () => {
    leaving("a1", { waitMs: () => 60_000 });
    const answer = watch(flushAll(5000, null));

    await vitest.advanceTimersByTimeAsync(64_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("waits for a save left behind only as long as it was first given, not for the deadline it has grown", async () => {
    leaving("a1", { waitMs: (first?: boolean) => (first ? 60_000 : 600_000) });
    const answer = watch(flushAll(5000, null));

    await vitest.advanceTimersByTimeAsync(64_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("waits for the longest of the saves left behind, not for their sum", async () => {
    leaving("a1", { waitMs: () => 10_000 });
    leaving("a2", { waitMs: () => 20_000 });
    const answer = watch(flushAll(5000, null));

    await vitest.advanceTimersByTimeAsync(24_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer.settled).toBe(true);
  });

  it("waits for the longest of the panel's and the saves left behind, not for their sum", async () => {
    leaving("a1", { waitMs: () => 20_000 });
    const answer = watch(flushAll(5000, never(), 60_000));

    await vitest.advanceTimersByTimeAsync(64_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer.settled).toBe(true);
  });

  it("never waits less than the cap, whatever the saves report", async () => {
    leaving("a1", { waitMs: () => 0 });
    const answer = watch(flushAll(5000, null, 0));

    await vitest.advanceTimersByTimeAsync(4999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer.settled).toBe(true);
  });

  it("keeps the panel's version while it waits on a slow save left behind", async () => {
    leaving("a1", { waitMs: () => 30_000 });
    const answer = watch(flushAll(5000, Promise.resolve(7)));

    await vitest.advanceTimersByTimeAsync(34_999);
    expect(answer.settled).toBe(false);
    await vitest.advanceTimersByTimeAsync(1);

    expect(answer).toEqual({ settled: true, value: 7 });
  });

  it("answers as soon as everything has landed, not at the end of the wait", async () => {
    const out = leaving("a1", { waitMs: () => 60_000 });
    const answer = watch(flushAll(5000, Promise.resolve(7), 60_000));

    await vitest.advanceTimersByTimeAsync(1000);
    expect(answer.settled).toBe(false);
    out.land(8);
    await settle();

    expect(answer).toEqual({ settled: true, value: 7 });
  });
});
