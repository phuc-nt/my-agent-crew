import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { canvasDiff } from "../lib/canvas-diff";
import { CanvasDiffView } from "./diff-view";

const rows = (container: HTMLElement) => [...container.querySelectorAll(".diff > div")].map((row) => [row.className, row.textContent]);
const numbers = Array.from({ length: 12 }, (_, k) => String(k + 1));

describe("two canvas versions side by side", () => {
  it("keeps three unchanged lines around a change and counts the rest", () => {
    const after = numbers.map((line) => (line === "6" ? "six" : line));
    const { container } = render(<CanvasDiffView lines={canvasDiff(numbers.join("\n"), after.join("\n"))} />);

    expect(rows(container)).toEqual([
      ["skipped", vi.canvas.unchanged(2)],
      ["", "  3"],
      ["", "  4"],
      ["", "  5"],
      ["removed", "- 6"],
      ["added", "+ six"],
      ["", "  7"],
      ["", "  8"],
      ["", "  9"],
      ["skipped", vi.canvas.unchanged(3)],
    ]);
  });

  it("shows a change made only of a hidden character", () => {
    const { container } = render(<CanvasDiffView lines={canvasDiff("ab", "a\u202Eb")} />);

    expect(rows(container)).toEqual([
      ["removed", "- ab"],
      ["added", "+ a[U+202E]b"],
    ]);
  });

  it("says when the versions are the same, and when they are too large to compare line by line", () => {
    const { rerender } = render(<CanvasDiffView lines={[]} />);
    expect(screen.getByText(vi.canvas.noChange)).toBeInTheDocument();

    rerender(<CanvasDiffView lines={null} />);
    expect(screen.getByText(vi.canvas.tooBig)).toBeInTheDocument();
  });
});
