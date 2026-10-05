import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { CanvasLinks } from "./canvas-card";
import { CanvasRefChip } from "./canvas-ref-chip";

const PLAN = "00ff00ff00ff";
const NOTE = "0123456789ab";
const LINE = `FILE: artifact:${PLAN}`;
const { card } = vi.canvas;

/** What the thread knows of canvases, with every call recorded; by default it knows nothing. */
function links(known: { titles?: Record<string, string>; gone?: string[] } = {}) {
  return {
    titleOf: vitest.fn((id: string) => known.titles?.[id] ?? null),
    isGone: vitest.fn((id: string) => (known.gone ?? []).includes(id)),
    verify: vitest.fn(),
    open: vitest.fn(),
  } satisfies CanvasLinks;
}

const chip = () => screen.getByTestId("canvas-ref");
const show = (id: string, canvas?: CanvasLinks, line = LINE) => render(<CanvasRefChip id={id} line={line} canvas={canvas} />);

describe("a line of a reply that sends a canvas", () => {
  it("is the canvas by the name the thread knows it by, with a button that opens it and no other", () => {
    const canvas = links({ titles: { [PLAN]: "Kế hoạch tuần", [NOTE]: "Ghi chú" } });
    show(PLAN, canvas);

    expect(chip().textContent).toBe(`Kế hoạch tuần${card.open}`);
    expect(chip().querySelector(".tool-icon")).not.toBeNull();
    fireEvent.click(within(chip()).getByRole("button", { name: card.openLabel("Kế hoạch tuần") }));

    expect(canvas.open.mock.calls).toEqual([[PLAN]]);
  });

  it("does not print the line it was read from", () => {
    show(PLAN, links({ titles: { [PLAN]: "Kế hoạch tuần" } }));

    expect(chip()).not.toHaveTextContent("FILE:");
    expect(chip()).not.toHaveTextContent(PLAN);
  });

  it("goes by a plain word until the thread knows the name, and still opens", () => {
    const canvas = links();
    show(PLAN, canvas);

    expect(chip().textContent).toBe(`${card.untitled}${card.open}`);
    fireEvent.click(within(chip()).getByRole("button", { name: card.openLabel(card.untitled) }));
    expect(canvas.open.mock.calls).toEqual([[PLAN]]);
  });

  it("writes out what nobody would see in a title", () => {
    show(PLAN, links({ titles: { [PLAN]: "an\u{202E}toàn" } }));

    expect(chip().querySelector(".canvas-chip-title")?.textContent).toBe("an[U+202E]toàn");
    expect(screen.getByRole("button", { name: card.openLabel("an[U+202E]toàn") })).toBeInTheDocument();
  });

  it("asks once whether the canvas is still there, and again only when it names another", () => {
    const canvas = links();
    const view = show(PLAN, canvas);
    expect(canvas.verify.mock.calls).toEqual([[PLAN]]);

    view.rerender(<CanvasRefChip id={PLAN} line={LINE} canvas={canvas} />);
    expect(canvas.verify).toHaveBeenCalledTimes(1);

    view.rerender(<CanvasRefChip id={NOTE} line={`FILE: artifact:${NOTE}`} canvas={canvas} />);
    expect(canvas.verify.mock.calls).toEqual([[PLAN], [NOTE]]);
  });

  it("says a canvas the server no longer has is deleted, by its name, with nothing to open", () => {
    const canvas = links({ titles: { [PLAN]: "Kế hoạch tuần" }, gone: [PLAN] });
    show(PLAN, canvas);

    expect(chip().textContent).toBe(`Kế hoạch tuần${vi.canvas.gone}`);
    expect(within(chip()).queryByRole("button")).toBeNull();
    expect(canvas.open).not.toHaveBeenCalled();
  });

  it("reads a name that could be no canvas's as one that is not there, and asks the server nothing", () => {
    const canvas = links({ titles: { "": "Không phải canvas" } });
    show("", canvas, "FILE: artifact:xyz");

    expect(chip().textContent).toBe(`${card.untitled}${vi.canvas.gone}`);
    expect(within(chip()).queryByRole("button")).toBeNull();
    expect(canvas.verify).not.toHaveBeenCalled();
    expect(canvas.titleOf).not.toHaveBeenCalled();
    expect(canvas.isGone).not.toHaveBeenCalled();
  });

  it("is the line as it was written where the thread knows nothing of canvases", () => {
    const { container } = show(PLAN, undefined, `MEDIA: artifact:${PLAN}`);

    expect(screen.queryByTestId("canvas-ref")).toBeNull();
    expect(container.querySelector("button, a")).toBeNull();
    expect(container.textContent).toBe(`MEDIA: artifact:${PLAN}`);
    expect(container.querySelector("p")?.textContent).toBe(`MEDIA: artifact:${PLAN}`);
  });
});
