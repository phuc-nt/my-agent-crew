import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // jsdom keeps one localStorage for a whole file, so a component that remembers a choice
  // there (the activity strip's expanded flag) carries it into the next test — which then
  // renders in a state it never set up. Node only exposes localStorage when started with
  // --localstorage-file, so this leak is invisible on a machine without that flag and real
  // on one with it; clearing here makes both behave the same.
  try {
    window.localStorage.clear();
    window.sessionStorage.clear();
  } catch {
    // A browser (or a Node without the flag) may refuse storage entirely; nothing to clear.
  }
});
