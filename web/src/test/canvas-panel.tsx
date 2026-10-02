import { fireEvent, render, screen } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { CanvasPanel, type CanvasPanelProps } from "../components/canvas/canvas-panel";
import type { PanelHandle } from "../hooks/use-canvas-dock";
import { vi } from "../i18n/vi";
import { landed } from "./canvas-hook";

/**
 * One canvas panel on the fake server of `startServer`, with the test in the dock's place: the
 * handles the panel binds are kept, and the dock's flush asks the newest of them, without the
 * dock's time limit.
 */
export async function openPanel(overrides: Partial<CanvasPanelProps> = {}) {
  const handles: PanelHandle[] = [];
  const unbind = vitest.fn();
  const props: CanvasPanelProps = {
    artifactId: "a1",
    created: false,
    connected: true,
    stuck: false,
    agentName: (id) => (id === "ming" ? "Ming" : id),
    bind: (handle) => {
      handles.push(handle);
      return unbind;
    },
    flush: () => handles.at(-1)?.flush() ?? Promise.resolve(null),
    onShowList: vitest.fn(),
    onClose: vitest.fn(),
    onForceClose: vitest.fn(),
    ...overrides,
  };
  const view = render(<CanvasPanel {...props} />);
  await landed();
  return { ...view, props, handles, unbind };
}

/** The field holding the canvas's text, or null in reading mode. */
export const editor = () => screen.queryByRole("textbox", { name: vi.canvas.editor }) as HTMLTextAreaElement | null;

/** What the panel says about the save, beside the version line. */
export const saveState = () => document.querySelector(".canvas-save-state")?.textContent ?? null;

/** "v2 · Ming · 4 phút". */
export const versionLine = () => document.querySelector(".canvas-version")?.textContent ?? null;

/** The mode chosen: "Xem" or "Sửa". */
export const mode = () => screen.getByRole("button", { pressed: true }).textContent;

/** The person types until the field holds `text`. */
export function typeInto(text: string): void {
  const field = editor();
  if (!field) throw new Error("the canvas is not being edited");
  fireEvent.change(field, { target: { value: text } });
}
