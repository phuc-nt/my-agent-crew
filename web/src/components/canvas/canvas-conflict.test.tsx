import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, type Mock, vi as vitest } from "vitest";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import { CanvasConflict } from "./canvas-conflict";

const THEIRS = "Dòng một của agent\nDòng hai\n";
const MINE = "Dòng một của tôi\nDòng hai\n";

let calls: Record<"keepMine" | "loadTheirs" | "undo", Mock>;

beforeEach(() => {
  calls = { keepMine: vitest.fn(), loadTheirs: vitest.fn(), undo: vitest.fn() };
});

type Shown = { conflict: { theirs: { version: number; author: string; content: string } } | null; undo: string | null };

function openBar(shown: Shown) {
  const canvas = { state: { text: MINE, ...shown }, ...calls } as unknown as CanvasController;
  return render(<CanvasConflict canvas={canvas} agentName={(id) => (id === "ming" ? "Ming" : id)} />);
}

const AGENT_SAVED: Shown = { conflict: { theirs: { version: 2, author: "agent:ming", content: THEIRS } }, undo: null };

describe("the bar over a canvas an agent saved while the person typed", () => {
  it("names who saved which version, and keeping mine asks for nothing else", () => {
    openBar(AGENT_SAVED);
    expect(screen.getByRole("alert")).toHaveTextContent(vi.canvas.conflictBy("Ming", 2));

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.keepMine }));

    expect(calls.keepMine).toHaveBeenCalledTimes(1);
    expect(calls.loadTheirs).not.toHaveBeenCalled();
  });

  it("loads their version when asked", () => {
    openBar(AGENT_SAVED);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.loadTheirs }));

    expect(calls.loadTheirs).toHaveBeenCalledTimes(1);
    expect(calls.keepMine).not.toHaveBeenCalled();
  });

  it("shows what keeping mine would change in theirs, and hides it again", () => {
    const { container } = openBar(AGENT_SAVED);
    const toggle = screen.getByRole("button", { name: vi.canvas.showDiff });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(toggle).toHaveTextContent(vi.canvas.hideDiff);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector(".canvas-diff .removed")).toHaveTextContent("Dòng một của agent");
    expect(container.querySelector(".canvas-diff .added")).toHaveTextContent("Dòng một của tôi");

    fireEvent.click(toggle);

    expect(toggle).toHaveTextContent(vi.canvas.showDiff);
    expect(container.querySelector(".canvas-diff")).toBeNull();
  });
});

describe("the text that loading the new version replaced", () => {
  it("can be brought back until the person types", () => {
    openBar({ conflict: null, undo: "Chữ cũ của tôi\n" });
    expect(screen.getByRole("status")).toHaveTextContent(vi.canvas.undoHint);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.undoLoad }));

    expect(calls.undo).toHaveBeenCalledTimes(1);
  });

  it("leaves no bar once there is nothing to bring back", () => {
    const { container } = openBar({ conflict: null, undo: null });

    expect(container).toBeEmptyDOMElement();
  });
});
