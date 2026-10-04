/**
 * The canvas being edited: a plain textarea filling the panel. Cmd/Ctrl+S saves at once instead of
 * opening the browser's save dialog, and leaving the field saves too. Escape here does nothing:
 * the app's shortcut leaves a field's keys to the field.
 *
 * When the text is replaced under the person — a newer version loaded, or a merge after a 409 — the
 * caret and the selection move with the lines around them and the scroll stays put, so the words
 * they were at are still under the caret.
 */

import { type KeyboardEvent, type RefObject, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import { type CanvasSelection, fromTextarea } from "../../lib/canvas-selection";
import { mapOffset } from "../../lib/line-edits";

type Props = {
  canvas: CanvasController;
  kind: string;
  /** Lets the panel see whether the keyboard is in the field. */
  fieldRef?: RefObject<HTMLTextAreaElement | null>;
  /** Told what is selected in the field each time that changes: null for a caret, or blank text. */
  onSelection?: (selection: CanvasSelection | null) => void;
};

export function CanvasEditor({ canvas, kind, fieldRef, onSelection }: Props) {
  const { state } = canvas;
  const own = useRef<HTMLTextAreaElement>(null);
  const field = fieldRef ?? own;
  const caret = useRef({ start: 0, end: 0, scroll: 0 });
  const replaced = useRef(state.replaced);
  replaced.current = state.replaced;

  const remember = useCallback(() => {
    const el = field.current;
    if (el) caret.current = { start: el.selectionStart, end: el.selectionEnd, scroll: el.scrollTop };
  }, [field]);

  // React hears of a change of selection from the mouse and the keys, which is how a drag, the
  // shift keys and select-all make it. A browser tells the rest, such as the handles of a touch
  // screen's selection, only as a `selectionchange` aimed at the field, which React lets pass; so
  // the document is listened to as well, for the field while it has the keyboard.
  const report = useCallback(() => {
    const el = field.current;
    if (!el) return;
    remember();
    onSelection?.(fromTextarea(el, el.value));
  }, [field, remember, onSelection]);

  useEffect(() => {
    const heard = () => {
      if (document.activeElement === field.current) report();
    };
    document.addEventListener("selectionchange", heard);
    return () => document.removeEventListener("selectionchange", heard);
  }, [field, report]);

  const seq = state.replaced?.seq;
  useLayoutEffect(() => {
    const el = field.current;
    const change = replaced.current;
    if (!el || !change || seq === undefined) return;
    const { start, end, scroll } = caret.current;
    el.setSelectionRange(
      mapOffset(change.before, el.value, change.edits, start),
      mapOffset(change.before, el.value, change.edits, end),
    );
    el.scrollTop = scroll;
    remember();
  }, [seq]);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      canvas.save();
    }
  };

  return (
    <textarea
      ref={field}
      className={kind === "markdown" ? "canvas-editor" : "canvas-editor code"}
      aria-label={vi.canvas.editor}
      value={state.text}
      readOnly={state.gone}
      spellCheck={kind === "markdown"}
      onChange={(event) => {
        canvas.edit(event.target.value);
        remember();
      }}
      onSelect={report}
      onScroll={remember}
      onKeyDown={onKeyDown}
      onBlur={canvas.blur}
      onCompositionStart={() => canvas.composition(true)}
      onCompositionEnd={() => canvas.composition(false)}
    />
  );
}
