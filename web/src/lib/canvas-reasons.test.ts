import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { canvasReason } from "./canvas-reasons";

const reasons = vi.canvas.reasons;

describe("why a canvas request failed", () => {
  it.each([
    [404, reasons.gone],
    [413, reasons.tooLarge],
    [507, reasons.full],
    [500, reasons.server],
    [503, reasons.server],
    [422, reasons.invalid],
    [400, reasons.invalid],
  ])("reads %i as its reason, never the server's own words", (status, reason) => {
    expect(canvasReason(new ApiError(status, "<b>from the server</b>"))).toBe(reason);
  });

  it("reads a request that never reached the server as a lost connection", () => {
    expect(canvasReason(new TypeError("Failed to fetch"))).toBe(reasons.offline);
  });
});
