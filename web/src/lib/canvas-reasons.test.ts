import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { canvasReason } from "./canvas-reasons";

const reasons = vi.canvas.reasons;

describe("why a canvas request failed", () => {
  it.each([
    [404, reasons.gone],
    [507, reasons.full],
    [500, reasons.server],
    [503, reasons.server],
    [422, reasons.invalid],
    [400, reasons.invalid],
  ])("reads %i as its reason, never the server's own words", (status, reason) => {
    expect(canvasReason(new ApiError(status, "<b>from the server</b>"))).toBe(reason);
  });

  it("reads 413 as the limit the server held the canvas to, in its own figure", () => {
    const refused = (cap: number) => new ApiError(413, "<b>from the server</b>", { size: cap + 1, cap });

    expect(canvasReason(refused(4 * 1024 * 1024))).toBe(reasons.tooLarge("4 MB"));
    expect(canvasReason(refused(2 * 1024 * 1024))).toBe(reasons.tooLarge("2 MB"));
  });

  it("reads a 413 that names no limit as the smallest one any canvas has", () => {
    expect(canvasReason(new ApiError(413, "<b>from the server</b>"))).toBe(reasons.tooLarge("512 KB"));
    expect(canvasReason(new ApiError(413, "", { cap: "4 MB" }))).toBe(reasons.tooLarge("512 KB"));
  });

  it("reads a request that never reached the server as a lost connection", () => {
    expect(canvasReason(new TypeError("Failed to fetch"))).toBe(reasons.offline);
  });
});
