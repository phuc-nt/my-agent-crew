/**
 * The canvas being edited: a plain textarea filling the panel. Cmd/Ctrl+S saves at once instead of
 * opening the browser's save dialog, and leaving the field saves too. Escape here does nothing:
 * the app's shortcut leaves a field's keys to the field.
 *
 * When the text is replaced under the person — a newer version loaded, or a merge after a 409 — the
 * caret and the selection move with the lines around them and the scroll stays put, so the words
 * they were at are still under the caret.
 */

import { type KeyboardEvent, useLayoutEffect, useRef } from "react";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import { mapOffset } from "../../lib/line-edits";

export function CanvasEditor({ canvas, kind }: { canvas: CanvasController; kind: string }) {
  const { state } = canvas;
  const field = useRef<HTMLTextAreaElement>(null);
  const caret = useRef({ start: 0, end: 0, scroll: 0 });
  const replaced = useRef(state.replaced);
  replaced.current = state.replaced;

  const remember = () => {
    const el = field.current;
    if (el) caret.current = { start: el.selectionStart, end: el.selectionEnd, scroll: el.scrollTop };
  };

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
      className={kind === "code" ? "canvas-editor code" : "canvas-editor"}
      aria-label={vi.canvas.editor}
      value={state.text}
      readOnly={state.gone}
      spellCheck={kind !== "code"}
      onChange={(event) => {
        canvas.edit(event.target.value);
        remember();
      }}
      onSelect={remember}
      onScroll={remember}
      onKeyDown={onKeyDown}
      onBlur={canvas.blur}
      onCompositionStart={() => canvas.composition(true)}
      onCompositionEnd={() => canvas.composition(false)}
    />
  );
}
