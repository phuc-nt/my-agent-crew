import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, type Mock, vi as vitest } from "vitest";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import type { LineEdit } from "../../lib/line-edits";
import { CanvasEditor } from "./canvas-editor";

type Shown = Pick<CanvasController["state"], "text" | "gone" | "replaced">;

let calls: Record<"save" | "blur" | "composition", Mock>;
let replace: (text: string, edits: LineEdit[]) => void;

beforeEach(() => {
  calls = { save: vitest.fn(), blur: vitest.fn(), composition: vitest.fn() };
});

/** The editor over a canvas whose text the person types into and the test replaces, as a merge would. */
function Editable({ text, kind }: { text: string; kind: string }) {
  const [state, setState] = useState<Shown>({ text, gone: false, replaced: null });
  replace = (next, edits) =>
    setState((was) => ({ ...was, text: next, replaced: { seq: (was.replaced?.seq ?? 0) + 1, before: was.text, edits } }));
  const canvas = { state, edit: (next: string) => setState((was) => ({ ...was, text: next })), ...calls };
  return <CanvasEditor canvas={canvas as unknown as CanvasController} kind={kind} />;
}

function openEditor(text = "one\ntwo\n", kind = "markdown"): HTMLTextAreaElement {
  render(<Editable text={text} kind={kind} />);
  return screen.getByRole("textbox", { name: vi.canvas.editor }) as HTMLTextAreaElement;
}

/** A line arriving above everything the person sees. */
const LINE_ABOVE: LineEdit[] = [{ start: 0, end: 0, lines: ["zero"] }];

describe("the canvas editor's keys and events", () => {
  it("saves at once on Ctrl+S or Cmd+S, with Shift or not, instead of the browser's save dialog", () => {
    const field = openEditor();

    expect(fireEvent.keyDown(field, { key: "s", ctrlKey: true })).toBe(false);
    expect(fireEvent.keyDown(field, { key: "s", metaKey: true })).toBe(false);
    expect(fireEvent.keyDown(field, { key: "S", ctrlKey: true, shiftKey: true })).toBe(false);
    expect(calls.save).toHaveBeenCalledTimes(3);
  });

  it("leaves a plain s to the text", () => {
    const field = openEditor();

    expect(fireEvent.keyDown(field, { key: "s" })).toBe(true);
    expect(calls.save).not.toHaveBeenCalled();
  });

  it("tells the canvas while a composition is open and when the field loses focus", () => {
    const field = openEditor();

    fireEvent.compositionStart(field);
    expect(calls.composition).toHaveBeenLastCalledWith(true);
    fireEvent.compositionEnd(field);
    expect(calls.composition).toHaveBeenLastCalledWith(false);
    fireEvent.blur(field);
    expect(calls.blur).toHaveBeenCalledTimes(1);
  });

  it("sets code in the code face without a spell check", () => {
    const code = openEditor("print(1)\n", "code");

    expect(code).toHaveClass("canvas-editor", "code");
    expect(code).toHaveAttribute("spellcheck", "false");
  });

  it("checks the spelling of prose", () => {
    const prose = openEditor("Dòng một\n", "markdown");

    expect(prose).not.toHaveClass("code");
    expect(prose).toHaveAttribute("spellcheck", "true");
  });
});

// The field notes the caret and the scroll on each select, scroll and keystroke.
describe("the caret when the machine replaces the person's text", () => {
  it("stays on the characters it was on when a line arrives above", () => {
    const field = openEditor("one\ntwo\n");
    field.setSelectionRange(5, 7);
    fireEvent.scroll(field);

    act(() => replace("zero\none\ntwo\n", LINE_ABOVE));

    expect(field.value).toBe("zero\none\ntwo\n");
    expect([field.selectionStart, field.selectionEnd]).toEqual([10, 12]);
  });

  it("starts from where typing left the caret, not from where it was last selected", () => {
    const field = openEditor("one\ntwo\n");
    field.setSelectionRange(0, 0);
    fireEvent.scroll(field);
    fireEvent.change(field, { target: { value: "one\nXtwo\n", selectionStart: 5, selectionEnd: 5 } });

    act(() => replace("zero\none\nXtwo\n", LINE_ABOVE));

    expect([field.selectionStart, field.selectionEnd]).toEqual([10, 10]);
  });

  it("keeps the scroll where the person left it", () => {
    const field = openEditor("one\ntwo\n");
    // jsdom lays nothing out, so its scrollTop would stay 0 whatever is set.
    Object.defineProperty(field, "scrollTop", { value: 0, writable: true, configurable: true });
    field.scrollTop = 120;
    fireEvent.scroll(field);
    field.scrollTop = 0; // as a browser may jump when the value is replaced

    act(() => replace("zero\none\ntwo\n", LINE_ABOVE));

    expect(field.scrollTop).toBe(120);
  });
});
