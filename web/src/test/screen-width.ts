import { act } from "@testing-library/react";
import { vi as vitest } from "vitest";

let width = 1440;
const listeners = new Set<() => void>();

/** A window `px` wide whose width queries follow `resize`; any other query answers false. */
export function screenAt(px: number) {
  width = px;
  vitest.stubGlobal("innerWidth", px);
  vitest.stubGlobal("matchMedia", (media: string) => ({
    get matches() {
      const min = /min-width:\s*(\d+)px/.exec(media);
      const max = /max-width:\s*(\d+)px/.exec(media);
      if (!min && !max) return false;
      return (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
    },
    media,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  }));
}

/** The window is resized to `px`. */
export function resize(px: number) {
  act(() => {
    width = px;
    vitest.stubGlobal("innerWidth", px);
    for (const fn of [...listeners]) fn();
    window.dispatchEvent(new Event("resize"));
  });
}

/** Forgets who was listening to the width, for the start of the next test. */
export function forgetScreenListeners() {
  listeners.clear();
}
