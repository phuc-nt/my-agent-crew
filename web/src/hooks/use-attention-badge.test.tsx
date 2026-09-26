import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { useAttention } from "./use-attention-badge";

function Counted({ runs }: { runs: RunInfo[] }) {
  useAttention(runs);
  return null;
}

const waiting = (id: string) => fakeRun({ id, status: "awaiting_approval", finished_at: null });
const failed = (id: string) => fakeRun({ id, status: "error" });

/** Installs the badge calls a browser may or may not have, restored after each test. */
function badgeApi(setAppBadge: unknown, clearAppBadge: unknown) {
  Object.defineProperty(navigator, "setAppBadge", { value: setAppBadge, configurable: true });
  Object.defineProperty(navigator, "clearAppBadge", { value: clearAppBadge, configurable: true });
}

beforeEach(() => {
  document.title = "Agent Crew";
});

afterEach(() => {
  Reflect.deleteProperty(navigator, "setAppBadge");
  Reflect.deleteProperty(navigator, "clearAppBadge");
});

describe("the count carried outside the page", () => {
  // A failure keeps until it is read; only a request with a deadline is worth pulling the
  // person back from another tab or app.
  it("prefixes the tab title with the requests waiting, not the failures", () => {
    const { rerender } = render(<Counted runs={[waiting("a"), waiting("b"), failed("c")]} />);
    expect(document.title).toBe("(2) Agent Crew");

    rerender(<Counted runs={[waiting("a")]} />);
    expect(document.title).toBe("(1) Agent Crew");

    rerender(<Counted runs={[failed("c")]} />);
    expect(document.title).toBe("Agent Crew");
  });

  it("sets and clears the installed app's badge where the browser has one", () => {
    const set = vitest.fn(() => Promise.resolve());
    const clear = vitest.fn(() => Promise.resolve());
    badgeApi(set, clear);

    const { rerender } = render(<Counted runs={[waiting("a"), waiting("b")]} />);
    expect(set).toHaveBeenCalledWith(2);

    rerender(<Counted runs={[]} />);
    expect(clear).toHaveBeenCalled();
  });

  it("carries on when the browser has no badge", () => {
    render(<Counted runs={[waiting("a")]} />);

    expect(document.title).toBe("(1) Agent Crew");
  });

  // Chromium rejects without permission, and some builds throw instead of rejecting.
  it("swallows a badge the browser refuses, whether it rejects or throws", async () => {
    // A plain function: a vitest spy would handle the rejection itself while recording it.
    const asked: number[] = [];
    const rejected = (n: number) => {
      asked.push(n);
      return Promise.reject(new DOMException("no", "NotAllowedError"));
    };
    const thrown = vitest.fn(() => {
      throw new DOMException("no", "NotAllowedError");
    });
    badgeApi(rejected, thrown);
    const unhandled = vitest.fn();
    process.on("unhandledRejection", unhandled);
    try {
      const { rerender } = render(<Counted runs={[waiting("a")]} />);
      rerender(<Counted runs={[]} />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    } finally {
      process.off("unhandledRejection", unhandled);
    }

    expect(asked).toEqual([1]);
    expect(thrown).toHaveBeenCalled();
    expect(unhandled).not.toHaveBeenCalled();
    expect(document.title).toBe("Agent Crew");
  });
});
