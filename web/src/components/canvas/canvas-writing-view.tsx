/**
 * A canvas the agent is still writing, in the dock: its name, a band saying nothing of it is saved
 * yet, and the text as far as it has come, following its last line until the person scrolls up.
 *
 * The text is what the model has written and nothing has checked it, so it is only ever read:
 * markdown goes through the same view as a stored canvas, and every other kind is shown as its
 * source. A page, a drawing or a diagram is not built from text that may stop anywhere, and says
 * that the canvas itself comes once the agent is done. There is nothing here to type in, save,
 * download or ask about, for no canvas is stored yet.
 *
 * It takes the keyboard only when the person asked to see it, and then only to its close button.
 */

import { useEffect, useRef } from "react";
import { useAutoScroll } from "../../hooks/use-auto-scroll";
import { vi } from "../../i18n/vi";
import { type WritingItem, writingTitle, writtenAsSource } from "../../lib/canvas-writing";
import { Icon } from "../ui/icon";
import { CanvasView } from "./canvas-view";

type Props = {
  item: WritingItem;
  /** Counts the times the person asked to see it; null when it came up by itself. */
  asked: number | null;
  onLeave(): void;
};

export function CanvasWritingView({ item, asked, onLeave }: Props) {
  const text = vi.canvas.writing;
  const frame = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const scroll = useAutoScroll<HTMLDivElement>();

  useEffect(() => {
    if (asked === null) return;
    if (!frame.current?.contains(document.activeElement)) close.current?.focus();
  }, [asked]);

  return (
    <div className="canvas-writing" data-testid="canvas-writing" ref={frame}>
      <header className="canvas-header">
        <div className="canvas-title-row">
          <h2 className="title-heading">{writingTitle(item)}</h2>
          {item.kind !== null && <span className="badge">{vi.canvas.kinds[item.kind]}</span>}
          <button type="button" className="icon-button" ref={close} aria-label={text.close} title={text.close} onClick={onLeave}>
            <Icon name="close" />
          </button>
        </div>
        <p className="canvas-writing-band" role="status">
          {item.callId === null ? text.unsaved : text.saving}
        </p>
      </header>
      <div className="canvas-body" ref={scroll.ref} onScroll={scroll.onScroll}>
        {writtenAsSource(item) && <div className="notice canvas-notice info">{text.source}</div>}
        <CanvasView text={item.content} kind={item.kind ?? "code"} />
      </div>
    </div>
  );
}
