import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { api, ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import type { ThreadAction } from "../state/thread-reducer";
import { useThreadSend } from "./use-thread-send";

/** A send made while this tab's own turn runs, so it joins the queue behind it: what it tells
 *  the thread, and the requests it still holds, are all there is to look at. */
function sendBehindATurn() {
  const dispatch = vitest.fn<(action: ThreadAction) => void>();
  const queueing = { current: new Set<AbortController>() };
  const { result } = renderHook(() =>
    useThreadSend({ conversationId: "c1", busy: true, dispatch, runTurn: vitest.fn(), queueing }),
  );
  return { send: result.current, dispatch, queueing };
}

afterEach(() => {
  vitest.restoreAllMocks();
});

describe("a message queued behind this tab's own turn that the server refuses", () => {
  it("is worded as any refused message is: a validation dump never reaches the notice", async () => {
    // What the server answers for a message over its length limit is a list, not a sentence.
    const dump = JSON.stringify([
      { type: "string_too_long", loc: ["body", "text"], msg: "String should have at most 20000 characters" },
    ]);
    vitest.spyOn(api, "sendMessage").mockRejectedValue(new ApiError(422, dump));
    const { send, dispatch } = sendBehindATurn();

    await expect(send("một tin quá dài")).resolves.toEqual({ status: "failed", error: vi.sendFailed.other });
    expect(dispatch).toHaveBeenCalledWith({ type: "queue_failed", message: vi.requestErrors.invalid });
  });
});
