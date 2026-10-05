import { render, screen, within } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { CanvasWritingView } from "../components/canvas/canvas-writing-view";
import { vi } from "../i18n/vi";
import type { WritingItem } from "../lib/canvas-writing";

/** The frame of a canvas being written, on its own: what the tests of the frame draw and ask of it. */

export const writingItem = (fields: Partial<WritingItem> = {}): WritingItem => ({
  key: 7,
  callId: null,
  updates: 2,
  rewrite: false,
  id: null,
  title: "Kế hoạch tuần",
  kind: "markdown",
  content: "# Việc một\n\n- mua rau",
  bytes: 24,
  ...fields,
});

/** The frame with a button outside it, where a person's keyboard may be. */
function Screen({ fields, asked, onLeave }: { fields: Partial<WritingItem>; asked: number | null; onLeave(): void }) {
  return (
    <>
      <button type="button">Ngoài khung</button>
      <CanvasWritingView item={writingItem(fields)} asked={asked} onLeave={onLeave} />
    </>
  );
}

/** Draws the frame; `again` draws it once more, as a later piece of the canvas does. */
export function openFrame(fields: Partial<WritingItem> = {}, asked: number | null = null) {
  const onLeave = vitest.fn();
  const view = render(<Screen fields={fields} asked={asked} onLeave={onLeave} />);
  const again = (next: Partial<WritingItem>, nextAsked: number | null = asked) =>
    view.rerender(<Screen fields={next} asked={nextAsked} onLeave={onLeave} />);
  return { onLeave, again };
}

export const frame = () => screen.getByTestId("canvas-writing");
export const outside = () => screen.getByRole("button", { name: "Ngoài khung" });
export const closeButton = () => within(frame()).getByRole("button", { name: vi.canvas.writing.close });
/** Where the canvas's text is drawn, apart from the frame's own head and its icon. */
export const frameBody = () => frame().querySelector(".canvas-body") as HTMLElement;
