import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { REQUEST_TIMEOUT_MS, UPLOAD_BYTES_PER_S, requestSave, saveDeadlineMs } from "./canvas-requests";
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
    expect(requestSave("a1", "ệ".repeat(100_000), 1, false, send)).toBe(35_860);
    // The same count in one-byte characters would give a fifth of the wait.
    expect(requestSave("a1", "x".repeat(100_000), 1, false, send)).toBe(31_954);
    await landed();
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
    expect(deadline).toBe(30_001);

    wait(deadline - 1);
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
    expect(deadline).toBe(91_441);

    wait(31_000);
    await landed();
    wait(deadline - 31_000 - 1);
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
