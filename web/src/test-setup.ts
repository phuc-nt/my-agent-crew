import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // jsdom keeps one localStorage for a whole file, so a component that remembers a choice
  // there (the activity strip's expanded flag) carries it into the next test — which then
  // renders in a state it never set up. The workers run with Node's own web storage off
  // (vite.config.ts), so this is jsdom's storage on every Node version.
  try {
    window.localStorage.clear();
    window.sessionStorage.clear();
  } catch {
    // A browser may refuse storage entirely; nothing to clear then.
  }
});
