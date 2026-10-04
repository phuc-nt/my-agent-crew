import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import {
  MAX_STRETCH,
  REQUEST_TIMEOUT_MS,
  UPLOAD_BYTES_PER_S,
  requestRead,
  requestSave,
  saveDeadlineMs,
} from "./canvas-requests";
import type { CanvasInput } from "./canvas-types";

const MB = 1024 * 1024;

let backend: FakeBackend;
let heard: CanvasInput[];

beforeEach(() => {
  backend = startServer();
  heard = [];
});

afterEach(stopServer);

const send = (input: CanvasInput) => void heard.push(input);

describe("how long a save may go unanswered", () => {
  it("is 30 seconds, and a second more for each 50 KiB the body holds, rounded up", () => {
    expect(REQUEST_TIMEOUT_MS).toBe(30_000);
    expect(UPLOAD_BYTES_PER_S).toBe(50 * 1024);

    expect(saveDeadlineMs(0)).toBe(30_000);
    expect(saveDeadlineMs(1)).toBe(30_001);
    expect(saveDeadlineMs(50 * 1024)).toBe(31_000);
    expect(saveDeadlineMs(50 * 1024 + 1)).toBe(31_001);
    expect(saveDeadlineMs(3 * MB)).toBe(91_440);
    expect(saveDeadlineMs(4 * MB)).toBe(111_920);
  });

  it("is measured on the body in UTF-8 bytes, which is what goes over the wire", async () => {
    backend.canvas.add({ content: "a" });

    // 100000 characters of 3 bytes each, and 30 bytes of JSON around them.
    expect(requestSave("a1", "ệ".repeat(100_000), 1, false, send)).toEqual({ ms: 35_860, firstMs: 35_860 });
    // The same count in one-byte characters would give a fifth of the wait.
    expect(requestSave("a1", "x".repeat(100_000), 1, false, send)).toEqual({ ms: 31_954, firstMs: 31_954 });
    await landed();
  });
});

describe("how long a save may go unanswered after saves in a row had no reply in time", () => {
  it("is twice the time for the body after each of them, and the same 30 seconds to answer", () => {
    expect(saveDeadlineMs(4 * MB, 0)).toBe(111_920);
    expect(saveDeadlineMs(4 * MB, 1)).toBe(193_840);
    expect(saveDeadlineMs(4 * MB, 2)).toBe(357_680);
    expect(saveDeadlineMs(4 * MB, 3)).toBe(685_360);
    // Nothing to carry is nothing to stretch.
    expect(saveDeadlineMs(0, 3)).toBe(30_000);
  });

  it("stops growing at eight times the body's time, however many there were", () => {
    expect(MAX_STRETCH).toBe(8);

    expect(saveDeadlineMs(4 * MB, 4)).toBe(685_360);
    expect(saveDeadlineMs(4 * MB, 40)).toBe(685_360);
    expect(saveDeadlineMs(4 * MB, 4000)).toBe(685_360);
  });

  it("keeps the first deadline what it was however many there were: only the save's own grows", async () => {
    backend.canvas.add({ kind: "html", content: "<p>a</p>" });
    const page = "x".repeat(3 * MB);

    expect(requestSave("a1", page, 1, false, send, 2)).toEqual({ ms: 275_763, firstMs: 91_441 });
    expect(requestSave("a1", page, 1, false, send, 3)).toEqual({ ms: 521_525, firstMs: 91_441 });
    expect(requestSave("a1", page, 1, false, send, 30)).toEqual({ ms: 521_525, firstMs: 91_441 });
    await landed();
  });

  it("leaves a small save at half a minute: 34 bytes get milliseconds more, never a minute", () => {
    expect(saveDeadlineMs(34, 0)).toBe(30_001);
    expect(saveDeadlineMs(34, 1)).toBe(30_002);
    expect(saveDeadlineMs(34, 9)).toBe(30_006);
  });

  it("is what the request is given: the longer deadline is answered, and kept to", async () => {
    backend.canvas.add({ kind: "html", content: "<p>a</p>" });
    backend.canvas.holdNext("PUT");

    // With it comes the deadline the same body had on the first try, which is all a message waits.
    const deadline = requestSave("a1", "x".repeat(3 * MB), 1, false, send, 1);
    expect(deadline).toEqual({ ms: 152_882, firstMs: 91_441 });

    // The first try's deadline passes, and the request is still out.
    wait(deadline.firstMs);
    await landed();
    wait(deadline.ms - deadline.firstMs - 1);
    await landed();
    expect(heard).toEqual([]);

    wait(1);
    await landed();
    expect(heard).toEqual([{ type: "saveTimedOut" }]);
    expect(vitest.getTimerCount()).toBe(0);
  });
});

describe("a save going out", () => {
  it("sends how it went, and leaves no timer running", async () => {
    backend.canvas.add({ content: "a" });

    requestSave("a1", "ab", 1, false, send);
    await landed();

    expect(heard).toEqual([{ type: "saved", meta: expect.objectContaining({ version: 2 }) }]);
    expect(vitest.getTimerCount()).toBe(0);
    wait(10 * 60_000);
    await landed();
    expect(heard).toHaveLength(1);
  });

  it("says a save with no reply at its deadline is too slow, not lost, and gives up on the request", async () => {
    backend.canvas.add({ content: "a" });
    backend.canvas.holdNext("PUT");

    const deadline = requestSave("a1", "ab", 1, false, send);
    expect(deadline).toEqual({ ms: 30_001, firstMs: 30_001 });

    wait(deadline.ms - 1);
    await landed();
    expect(heard).toEqual([]);

    wait(1);
    await landed();
    expect(heard).toEqual([{ type: "saveTimedOut" }]);
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("waits longer for a big save: 3 MB of html is not cut off at 31 seconds, nor at 90", async () => {
    backend.canvas.add({ kind: "html", content: "<p>a</p>" });
    backend.canvas.holdNext("PUT");

    const deadline = requestSave("a1", "x".repeat(3 * MB), 1, false, send);
    expect(deadline).toEqual({ ms: 91_441, firstMs: 91_441 });

    wait(31_000);
    await landed();
    wait(deadline.ms - 31_000 - 1);
    await landed();
    expect(heard).toEqual([]);

    wait(1);
    await landed();
    expect(heard).toEqual([{ type: "saveTimedOut" }]);
  });

  it("says a reply that never came back is lost, with no status to tell it from a timeout", async () => {
    backend.canvas.add({ content: "a" });
    backend.canvas.loseNext("PUT");

    requestSave("a1", "ab", 1, false, send);
    await landed();

    expect(heard).toEqual([{ type: "saveFailed", status: null, conflict: null, full: null, cap: null }]);
  });

  it.each([
    ["markdown", 512 * 1024],
    ["html", 4 * MB],
    ["svg", 2 * MB],
  ])("carries the limit a %s canvas was held to when the server refuses it as too large", async (kind, cap) => {
    backend.canvas.add({ kind, content: "a" });
    backend.canvas.refuseNext("PUT", 413);

    requestSave("a1", "ab", 1, false, send);
    await landed();

    expect(heard).toEqual([{ type: "saveFailed", status: 413, conflict: null, full: null, cap }]);
  });
});

describe("a read coming back", () => {
  it("sends what the server holds, and leaves no timer running", async () => {
    backend.canvas.add({ content: "a" });

    requestRead("a1", send);
    await landed();

    expect(heard).toEqual([{ type: "read", detail: expect.objectContaining({ id: "a1", content: "a", head_version: 1 }) }]);
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("says the canvas could not be read when what came back cannot be taken in, instead of leaving it loading", async () => {
    backend.canvas.add({ content: "a" });
    vitest.spyOn(console, "error").mockImplementation(() => {});
    const unreadable = (input: CanvasInput) => {
      heard.push(input);
      if (input.type === "read") throw new Error("a detail the machine cannot take in");
    };

    requestRead("a1", unreadable);
    await landed();

    expect(heard.map((input) => input.type)).toEqual(["read", "readFailed"]);
    expect(heard[1]).toEqual({ type: "readFailed", status: null });
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("says in the console what it could not take in: the canvas only says it could not be read", async () => {
    backend.canvas.add({ content: "a" });
    const logged = vitest.spyOn(console, "error").mockImplementation(() => {});
    const crash = new Error("a detail the machine cannot take in");
    const unreadable = (input: CanvasInput) => {
      heard.push(input);
      if (input.type === "read") throw crash;
    };

    requestRead("a1", unreadable);
    await landed();

    expect(logged).toHaveBeenCalledTimes(1);
    expect(logged).toHaveBeenCalledWith("a canvas reply could not be taken in", crash);
  });

  it("says a read the server refused failed, with its status, once, and nothing in the console", async () => {
    const logged = vitest.spyOn(console, "error").mockImplementation(() => {});

    requestRead("gone", send);
    await landed();

    expect(heard).toEqual([{ type: "readFailed", status: 404 }]);
    expect(logged).not.toHaveBeenCalled();
  });
});
