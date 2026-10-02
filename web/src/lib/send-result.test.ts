import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import type { AgentEvent } from "../api/types";
import { vi } from "../i18n/vi";
import { sendErrorText, settlement } from "./send-result";

const queued: AgentEvent = { type: "queued", item_id: 1, kind: "follow_up", position: 1 };
const word: AgentEvent = { type: "text_delta", text: "Để tôi " };

describe("settlement", () => {
  it("answers queued for a queued event, and sent for any other first event", async () => {
    const held = settlement();
    held.heard(queued);
    await expect(held.promise).resolves.toEqual({ status: "queued" });

    const started = settlement();
    started.heard(word);
    await expect(started.promise).resolves.toEqual({ status: "sent" });
  });

  it("keeps its first answer: what comes later changes nothing", async () => {
    const s = settlement();
    expect(s.done).toBe(false);
    s.heard(word);
    s.heard(queued);
    s.failed(new TypeError("Failed to fetch"));
    s.ended();
    await expect(s.promise).resolves.toEqual({ status: "sent" });
    expect(s.done).toBe(true);
  });

  it("answers failed, with a reason, when the send fails before anything was heard", async () => {
    const s = settlement();
    s.failed(new ApiError(429, "Hàng chờ đã đủ 20 tin."));
    await expect(s.promise).resolves.toEqual({ status: "failed", error: vi.sendFailed.tooFast });
    expect(s.done).toBe(true);
  });

  it("answers sent when the send ends having heard nothing: cut off on purpose, or silent", async () => {
    const s = settlement();
    s.ended();
    await expect(s.promise).resolves.toEqual({ status: "sent" });
    expect(s.done).toBe(true);
  });
});

describe("sendErrorText", () => {
  it.each([
    ["a full queue", new ApiError(429, "Hàng chờ của cuộc trò chuyện này đã đủ 20 tin."), vi.sendFailed.tooFast],
    ["a conversation waiting on approval", new ApiError(409, "conversation is awaiting approval"), vi.busyConflict],
    ["a connection that never opened", new TypeError("Failed to fetch"), vi.requestErrors.network],
    ["a crash on the server", new ApiError(500, "boom"), vi.sendFailed.other],
    ["a conversation that is gone", new ApiError(404, "not found"), vi.sendFailed.other],
    // Whatever words the server used, a refusal reaches the person in ours.
    ["a refusal in English", new ApiError(422, "selection does not match the canvas"), vi.sendFailed.other],
    ["something that is not an error at all", "boom", vi.sendFailed.other],
  ])("says %s in our own words", (_name, error, text) => {
    expect(sendErrorText(error)).toBe(text);
  });
});
