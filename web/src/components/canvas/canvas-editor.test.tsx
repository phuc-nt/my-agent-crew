import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, type Mock, vi as vitest } from "vitest";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import type { CanvasSelection } from "../../lib/canvas-selection";
import type { LineEdit } from "../../lib/line-edits";
import { CanvasEditor } from "./canvas-editor";

type Shown = Pick<CanvasController["state"], "text" | "gone" | "replaced">;
type Selected = (selection: CanvasSelection | null) => void;

let calls: Record<"save" | "blur" | "composition", Mock>;
let replace: (text: string, edits: LineEdit[]) => void;

beforeEach(() => {
  calls = { save: vitest.fn(), blur: vitest.fn(), composition: vitest.fn() };
});

/** The editor over a canvas whose text the person types into and the test replaces, as a merge would. */
function Editable({ text, kind, onSelection }: { text: string; kind: string; onSelection?: Selected }) {
  const [state, setState] = useState<Shown>({ text, gone: false, replaced: null });
  replace = (next, edits) =>
    setState((was) => ({ ...was, text: next, replaced: { seq: (was.replaced?.seq ?? 0) + 1, before: was.text, edits } }));
  const canvas = { state, edit: (next: string) => setState((was) => ({ ...was, text: next })), ...calls };
  return <CanvasEditor canvas={canvas as unknown as CanvasController} kind={kind} onSelection={onSelection} />;
}

function openEditor(text = "one\ntwo\n", kind = "markdown", onSelection?: Selected): HTMLTextAreaElement {
  render(<Editable text={text} kind={kind} onSelection={onSelection} />);
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

  // Everything but prose is written in a language of its own, where a spell check underlines every word.
  it.each(["code", "html", "svg", "mermaid", "pdf"])("sets a %s canvas in the code face without a spell check", (kind) => {
    const code = openEditor("print(1)\n", kind);

    expect(code).toHaveClass("canvas-editor", "code");
    expect(code).toHaveAttribute("spellcheck", "false");
  });

  it("checks the spelling of prose, which is set in the face of the page", () => {
    const prose = openEditor("Dòng một\n", "markdown");

    expect(prose).toHaveClass("canvas-editor");
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

describe("the selection the editor reports", () => {
  it("tells the passage selected, with the lines it lies on", () => {
    const onSelection = vitest.fn();
    const field = openEditor("one\ntwo\nthree\n", "markdown", onSelection);

    field.setSelectionRange(4, 13);
    fireEvent.select(field);

    expect(onSelection).toHaveBeenLastCalledWith({ text: "two\nthree", line_start: 2, line_end: 3, shown: 9 });
  });

  it("tells there is none when only a caret is left", () => {
    const onSelection = vitest.fn();
    const field = openEditor("one\ntwo\n", "markdown", onSelection);

    field.setSelectionRange(5, 5);
    fireEvent.select(field);

    expect(onSelection).toHaveBeenLastCalledWith(null);
  });

  it("reads the text as it was typed", () => {
    const onSelection = vitest.fn();
    const field = openEditor("one\ntwo\n", "markdown", onSelection);
    fireEvent.change(field, { target: { value: "one\ntwo!\n" } });

    field.setSelectionRange(4, 8);
    fireEvent.select(field);

    expect(onSelection).toHaveBeenLastCalledWith({ text: "two!", line_start: 2, line_end: 2, shown: 4 });
  });

  it("still notes the caret for the machine's replacements when nobody listens", () => {
    const field = openEditor("one\ntwo\n");
    field.setSelectionRange(5, 7);

    fireEvent.select(field);
    act(() => replace("zero\none\ntwo\n", LINE_ABOVE));

    expect([field.selectionStart, field.selectionEnd]).toEqual([10, 12]);
  });
});

describe("a selection that no key or mouse made", () => {
  // The handles of a touch screen's selection, a menu's select-all and a script move the selection
  // with no key or mouse event. Chromium then tells the field alone, and the event bubbles up
  // from it: React lets that one pass, so only the editor's own listener on the page hears it.
  const announceAt = (field: HTMLElement) =>
    act(() => {
      field.dispatchEvent(new Event("selectionchange", { bubbles: true }));
    });

  it("is told once the field says the selection changed, while it has the keyboard", () => {
    const onSelection = vitest.fn();
    const field = openEditor("one\ntwo\nthree\n", "markdown", onSelection);
    field.focus();

    field.setSelectionRange(4, 13);
    announceAt(field);

    expect(onSelection).toHaveBeenLastCalledWith({ text: "two\nthree", line_start: 2, line_end: 3, shown: 9 });
  });

  it("is left alone while the keyboard is somewhere else", () => {
    const onSelection = vitest.fn();
    const field = openEditor("one\ntwo\n", "markdown", onSelection);

    field.setSelectionRange(0, 3);
    announceAt(field);

    expect(onSelection).not.toHaveBeenCalled();
  });

  it("moves the caret the machine's replacements keep, as a selection the keys made does", () => {
    const field = openEditor("one\ntwo\n");
    field.focus();
    field.setSelectionRange(5, 7);

    announceAt(field);
    act(() => replace("zero\none\ntwo\n", LINE_ABOVE));

    expect([field.selectionStart, field.selectionEnd]).toEqual([10, 12]);
  });

  it("is listened for only while the editor is on the page", () => {
    // React puts its own listener on the page the first time anything is drawn, and keeps it.
    render(<Editable text="one" kind="markdown" />).unmount();
    const added = vitest.spyOn(document, "addEventListener");
    const removed = vitest.spyOn(document, "removeEventListener");
    const selectionListeners = (spy: typeof added) =>
      spy.mock.calls.filter(([type]) => type === "selectionchange").map(([, listener]) => listener);
    try {
      const { unmount } = render(<Editable text="one" kind="markdown" />);
      const heard = selectionListeners(added);
      expect(heard).toHaveLength(1);

      unmount();

      expect(selectionListeners(removed)).toEqual(heard);
    } finally {
      added.mockRestore();
      removed.mockRestore();
    }
  });
});
