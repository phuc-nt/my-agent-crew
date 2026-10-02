import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, type Mock, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { CanvasHandle } from "./canvas-handle";

let resize: Mock;

beforeEach(() => {
  resize = vitest.fn();
});

function openHandle() {
  const view = render(<CanvasHandle width={400} min={360} max={800} resize={resize} />);
  return { ...view, handle: screen.getByRole("separator", { name: vi.canvas.resize }) };
}

/** A pointer event as the handle reads it, by its button and x; jsdom may not have PointerEvent. */
function pointer(type: string, clientX: number, button = 0): MouseEvent {
  return new MouseEvent(type, { bubbles: true, cancelable: true, button, clientX });
}

// The canvas sits right of the conversation, so dragging its edge left widens it.
describe("dragging the canvas's edge", () => {
  it("widens the canvas as the pointer moves left and keeps where the button came up", () => {
    const { handle } = openHandle();

    // Prevented, so the drag selects no text on its way.
    expect(fireEvent(handle, pointer("pointerdown", 500))).toBe(false);
    window.dispatchEvent(pointer("pointermove", 450));
    expect(resize).toHaveBeenLastCalledWith(450);

    window.dispatchEvent(pointer("pointerup", 440));
    expect(resize).toHaveBeenLastCalledWith(460, true);

    window.dispatchEvent(pointer("pointermove", 300));
    expect(resize).toHaveBeenCalledTimes(2);
  });

  it("does not drag with any button but the main one", () => {
    const { handle } = openHandle();

    expect(fireEvent(handle, pointer("pointerdown", 500, 2))).toBe(true);
    window.dispatchEvent(pointer("pointermove", 450));

    expect(resize).not.toHaveBeenCalled();
  });

  it("lets go of the pointer when the canvas closes mid-drag", () => {
    const { handle, unmount } = openHandle();
    fireEvent(handle, pointer("pointerdown", 500));

    unmount();
    window.dispatchEvent(pointer("pointermove", 450));
    window.dispatchEvent(pointer("pointerup", 450));

    expect(resize).not.toHaveBeenCalled();
  });
});
