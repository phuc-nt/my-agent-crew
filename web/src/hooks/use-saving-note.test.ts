import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { SAVING_NOTE_DELAY_MS, useSavingNote } from "./use-saving-note";

beforeEach(() => {
  vitest.useFakeTimers();
});

afterEach(() => {
  vitest.useRealTimers();
});

/** A wait the test settles by hand. */
function gate<T>() {
  let settle: { resolve(value: T): void; reject(reason: unknown): void } = { resolve() {}, reject() {} };
  const work = new Promise<T>((resolve, reject) => {
    settle = { resolve, reject };
  });
  return { work, ...settle };
}

describe("the note shown while a message waits for a save", () => {
  it("says nothing for a wait that ends within a moment", async () => {
    const { result } = renderHook(() => useSavingNote());
    const wait = gate<number>();

    let outcome: Promise<number> = Promise.resolve(0);
    act(() => {
      outcome = result.current.during(wait.work);
    });
    act(() => {
      vitest.advanceTimersByTime(SAVING_NOTE_DELAY_MS - 1);
    });
    expect(result.current.shown).toBe(false);

    await act(async () => {
      wait.resolve(7);
      await outcome;
    });
    act(() => {
      vitest.advanceTimersByTime(10 * SAVING_NOTE_DELAY_MS);
    });

    expect(result.current.shown).toBe(false);
    expect(vitest.getTimerCount()).toBe(0);
  });

  it("says so once the wait has gone on for 300 ms, and stops when it ends", async () => {
    const { result } = renderHook(() => useSavingNote());
    const wait = gate<number>();

    let outcome: Promise<number> = Promise.resolve(0);
    act(() => {
      outcome = result.current.during(wait.work);
    });
    act(() => {
      vitest.advanceTimersByTime(SAVING_NOTE_DELAY_MS);
    });
    expect(result.current.shown).toBe(true);

    await act(async () => {
      wait.resolve(7);
      await outcome;
    });

    expect(result.current.shown).toBe(false);
  });

  it("gives back what the work came to", async () => {
    const { result } = renderHook(() => useSavingNote());

    let value = 0;
    await act(async () => {
      value = await result.current.during(Promise.resolve(42));
    });

    expect(value).toBe(42);
  });

  it("stops saying it when the work fails, and passes the failure on", async () => {
    const { result } = renderHook(() => useSavingNote());
    const wait = gate<number>();
    const failure = new Error("no save");

    let outcome: Promise<number> = Promise.resolve(0);
    act(() => {
      outcome = result.current.during(wait.work);
    });
    act(() => {
      vitest.advanceTimersByTime(SAVING_NOTE_DELAY_MS);
    });
    expect(result.current.shown).toBe(true);

    await act(async () => {
      wait.reject(failure);
      await expect(outcome).rejects.toBe(failure);
    });

    expect(result.current.shown).toBe(false);
    expect(vitest.getTimerCount()).toBe(0);
  });
});
