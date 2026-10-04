import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { useSaveThenShow } from "./use-save-then-show";

/** A save that answers only when told to: `lands` with a version, or `throws`. */
function heldSave() {
  let settle: { resolve: (version: number | null) => void; reject: (reason: unknown) => void } | null = null;
  const flush = vitest.fn(
    () =>
      new Promise<number | null>((resolve, reject) => {
        settle = { resolve, reject };
      }),
  );
  const answer = (how: (held: NonNullable<typeof settle>) => void) => {
    if (!settle) throw new Error("no save is out");
    how(settle);
  };
  return {
    flush,
    lands: (version: number | null) => answer((held) => held.resolve(version)),
    throws: () => answer((held) => held.reject(new Error("the save broke"))),
  };
}

describe("a turn to a view that shows what the server holds", () => {
  it("is made at once when there is nothing to wait for, and asks for no save", () => {
    const save = heldSave();
    const show = vitest.fn();
    const { result } = renderHook(() => useSaveThenShow(save.flush));

    act(() => result.current.turn(false, show));

    expect(show).toHaveBeenCalledTimes(1);
    expect(save.flush).not.toHaveBeenCalled();
    expect(result.current.waiting).toBe(false);
  });

  it("waits for the save, saying so meanwhile, and is made when it answers", async () => {
    const save = heldSave();
    const show = vitest.fn();
    const { result } = renderHook(() => useSaveThenShow(save.flush));

    act(() => result.current.turn(true, show));
    expect(save.flush).toHaveBeenCalledTimes(1);
    expect(result.current.waiting).toBe(true);
    expect(show).not.toHaveBeenCalled();

    save.lands(2);

    await waitFor(() => expect(show).toHaveBeenCalledTimes(1));
    expect(result.current.waiting).toBe(false);
  });

  it("is made all the same when the save throws, and stops saying it waits", async () => {
    const save = heldSave();
    const show = vitest.fn();
    const { result } = renderHook(() => useSaveThenShow(save.flush));
    act(() => result.current.turn(true, show));

    save.throws();

    await waitFor(() => expect(show).toHaveBeenCalledTimes(1));
    expect(result.current.waiting).toBe(false);
  });

  it("gives way to a later turn: the one still waiting is not made when its save answers", async () => {
    const save = heldSave();
    const [early, late] = [vitest.fn(), vitest.fn()];
    const { result } = renderHook(() => useSaveThenShow(save.flush));
    act(() => result.current.turn(true, early));

    act(() => result.current.turn(false, late));
    expect(result.current.waiting).toBe(false);
    await act(async () => save.lands(2));

    expect(late).toHaveBeenCalledTimes(1);
    expect(early).not.toHaveBeenCalled();
    expect(result.current.waiting).toBe(false);
  });

  it("is dropped by a cancel, which stops saying it waits", async () => {
    const save = heldSave();
    const show = vitest.fn();
    const { result } = renderHook(() => useSaveThenShow(save.flush));
    act(() => result.current.turn(true, show));

    act(() => result.current.cancel());
    expect(result.current.waiting).toBe(false);
    await act(async () => save.lands(2));

    expect(show).not.toHaveBeenCalled();
    expect(result.current.waiting).toBe(false);
  });
});
