import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { openDock, opened, panel, startDockServer } from "../test/canvas-dock-hook";
import { stopServer } from "../test/canvas-hook";

beforeEach(() => void startDockServer());

afterEach(stopServer);

describe("whether the person is typing in the open canvas", () => {
  it("is no when no panel is open to say so", async () => {
    const { result } = await openDock();

    expect(result.current.typing()).toBe(false);
    opened(result);
    expect(result.current.typing()).toBe(false);
  });

  it("is what the open panel says, asked afresh each time", async () => {
    const { result } = await openDock();
    let typing = false;
    const asked = vitest.fn(() => typing);
    opened(result, undefined, panel(undefined, asked));

    expect(result.current.typing()).toBe(false);
    typing = true;
    expect(result.current.typing()).toBe(true);
    typing = false;
    expect(result.current.typing()).toBe(false);
    expect(asked).toHaveBeenCalledTimes(3);
  });

  it("is no again once the panel lets go", async () => {
    const { result } = await openDock();
    let unbind = () => {};
    opened(result);
    act(() => {
      unbind = result.current.bind(panel(undefined, () => true));
    });
    expect(result.current.typing()).toBe(true);

    act(() => unbind());

    expect(result.current.typing()).toBe(false);
  });

  it("is the same function whatever the dock does", async () => {
    const { result, rerender } = await openDock();
    const typing = result.current.typing;

    opened(result);
    rerender({ conversationId: "c2", wide: false });

    expect(result.current.typing).toBe(typing);
  });
});
