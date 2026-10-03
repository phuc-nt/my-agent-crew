import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DRAFT_DELAY_MS } from "../../lib/canvas-runner";
import { startServer, stopServer, wait } from "../../test/canvas-hook";
import { openPanel, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { memoryStorage, refusingStorage } from "../../test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

describe("what the open panel lends the dock", () => {
  it("says how long the save in flight may still go unanswered, and nothing while none is out", async () => {
    backend.canvas.add({ content: "a" });
    const { handles } = await openPanel();
    expect(handles.at(-1)?.waitMs()).toBe(0);
    const release = backend.canvas.holdNext("PUT");
    typeInto("ab");

    act(() => void handles.at(-1)?.flush());
    expect(handles.at(-1)?.waitMs()).toBe(30_001);
    wait(10_000);
    expect(handles.at(-1)?.waitMs()).toBe(20_001);

    await act(release);
    expect(handles.at(-1)?.waitMs()).toBe(0);
  });

  it("says whether this device could keep a draft of the typing, and when it can again", async () => {
    backend.canvas.add({ content: "a" });
    refusingStorage();
    const { handles } = await openPanel();
    expect(handles.at(-1)?.draftFailed()).toBe(false);

    typeInto("ab");
    wait(DRAFT_DELAY_MS);
    expect(handles.at(-1)?.draftFailed()).toBe(true);

    memoryStorage();
    typeInto("abc");
    wait(DRAFT_DELAY_MS);
    expect(handles.at(-1)?.draftFailed()).toBe(false);
  });
});
