import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { errorText, turnErrorText } from "./error-text";

describe("errorText", () => {
  it("keeps what the server wrote as a sentence, in whatever language", () => {
    expect(errorText(new ApiError(409, "Agent coach đã có."))).toBe("Agent coach đã có.");
    expect(errorText(new ApiError(422, "Cost cap is too high"))).toBe("Cost cap is too high");
  });

  it("puts a validation dump in words", () => {
    const dump = JSON.stringify([{ type: "greater_than_equal", loc: ["body", "cost_cap_usd"] }]);
    expect(errorText(new ApiError(422, dump))).toBe(vi.requestErrors.invalid);
    expect(errorText(new ApiError(422, JSON.stringify({ error: "x" })))).toBe(vi.requestErrors.invalid);
  });

  it("names what a stock 404 lost, where the caller knows it", () => {
    expect(errorText(new ApiError(404, "conversation not found"))).toBe(vi.requestErrors.notFound);
    expect(errorText(new ApiError(404, "Not Found"), "Cuộc đã xoá.")).toBe("Cuộc đã xoá.");
    // A 404 the server put in words says more than the stock sentence would.
    expect(errorText(new ApiError(404, "Không có mẫu coder."))).toBe("Không có mẫu coder.");
  });

  it("says the server failed rather than echoing its crash", () => {
    expect(errorText(new ApiError(500, "Internal Server Error"))).toBe(vi.requestErrors.server(500));
    expect(errorText(new ApiError(502, "Bad Gateway"))).toBe(vi.requestErrors.server(502));
  });

  it("says the server could not be reached when fetch never got an answer", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toBe(vi.requestErrors.network);
    expect(errorText(new TypeError("Load failed"))).toBe(vi.requestErrors.network);
  });

  it("falls back to the status when a refusal carries no words at all", () => {
    expect(errorText(new ApiError(403, ""))).toBe(vi.requestErrors.status(403));
  });

  it("leaves an error of the page's own as it is", () => {
    expect(errorText(new Error("Hỏng"))).toBe("Hỏng");
    expect(errorText("thô")).toBe("thô");
  });
});

describe("turnErrorText", () => {
  it("says a 409 is a conversation waiting on a decision, whatever the server wrote", () => {
    expect(turnErrorText(new ApiError(409, "conversation is awaiting approval"))).toBe(vi.busyConflict);
    expect(turnErrorText(new ApiError(409, "conversation is awaiting approval"), true)).toBe(vi.busyConflict);
  });

  it("puts a 422 for a message that carried a selection in words: it is the selection", () => {
    const refused = new ApiError(422, "selection does not match the canvas");
    expect(turnErrorText(refused, true)).toBe(vi.sendFailed.selection);
    // With no selection on the request a 422 is something else, and keeps its own words.
    expect(turnErrorText(refused)).toBe("selection does not match the canvas");
  });

  it("leaves every other failure to errorText, selection or not", () => {
    for (const withSelection of [false, true]) {
      expect(turnErrorText(new ApiError(429, "Hàng chờ đã đầy."), withSelection)).toBe("Hàng chờ đã đầy.");
      expect(turnErrorText(new ApiError(500, "boom"), withSelection)).toBe(vi.requestErrors.server(500));
      expect(turnErrorText(new TypeError("Failed to fetch"), withSelection)).toBe(vi.requestErrors.network);
    }
  });
});
