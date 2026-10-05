import { vi } from "../../i18n/vi";
import { type WritingItem, writingTitle } from "../../lib/canvas-writing";
import { formatBytes } from "../../lib/format-bytes";
import { Icon } from "../ui/icon";

type Props = {
  item: WritingItem;
  /** Asked to show the canvas with this key in the dock. */
  onShow(key: number): void;
};

/**
 * A canvas the agent is still writing, in the thread: what it goes by so far, whether it is being
 * made or written again, how much has been written, and a button that shows it filling in.
 *
 * It never shows the text itself, which is the canvas's and not the thread's. The size changes
 * with every piece that arrives, so it is kept from being read out each time.
 */
export function CanvasWritingCard({ item, onShow }: Props) {
  const text = vi.canvas.writing;
  const title = writingTitle(item);
  return (
    <div className="tool-card canvas-card canvas-writing-card" data-testid="canvas-writing-card">
      <Icon name="document" className="tool-icon" />
      <div className="canvas-card-text">
        <span className="canvas-writing-name">
          <span className="canvas-card-title">{title}</span>
          {item.kind !== null && <span className="badge">{vi.canvas.kinds[item.kind]}</span>}
        </span>
        <span className="canvas-card-line tool-status running">
          <span className="writing-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="canvas-writing-words">{item.rewrite ? text.rewriting : text.creating}</span>
          <span className="canvas-writing-size" aria-live="off">
            <span className="canvas-writing-dot" aria-hidden="true">
              ·
            </span>
            {text.written(formatBytes(item.bytes))}
          </span>
        </span>
      </div>
      <button type="button" className="ghost canvas-card-open" aria-label={text.showLabel(title)} onClick={() => onShow(item.key)}>
        {text.show}
      </button>
    </div>
  );
}
