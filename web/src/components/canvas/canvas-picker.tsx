/**
 * The open conversation's canvases, the newest first, and the way to make one. The list says
 * when it is loading, empty or could not be read, and offers a retry for the last; a failed read
 * keeps the canvases an earlier one found.
 */

import type { CanvasList } from "../../hooks/use-canvas-list";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { timeAgo } from "../../lib/relative-time";
import { Icon } from "../ui/icon";

type Props = {
  list: Pick<CanvasList, "items" | "failed" | "retry">;
  creating: boolean;
  createFailed: boolean;
  onOpen(id: string): void;
  onCreate(): void;
};

export function CanvasPicker({ list, creating, createFailed, onOpen, onCreate }: Props) {
  const now = useNow(60_000);
  const { canvas } = vi;
  const { items } = list;
  return (
    <div className="canvas-picker">
      <div className="canvas-picker-head">
        <h2>{canvas.listTitle}</h2>
        <button type="button" className="primary" onClick={onCreate} disabled={creating}>
          <Icon name="plus" />
          {canvas.newCanvas}
        </button>
      </div>
      {createFailed && (
        <div className="notice error canvas-notice" role="alert">
          {canvas.createFailed}
        </div>
      )}
      {list.failed && (
        <div className="notice error canvas-notice" role="alert">
          <span>{canvas.listFailed}</span>
          <button type="button" className="link-button" onClick={list.retry}>
            {canvas.retry}
          </button>
        </div>
      )}
      {items === null && !list.failed && <p className="muted">{canvas.listLoading}</p>}
      {items?.length === 0 && <p className="muted">{canvas.listEmpty}</p>}
      {items !== null && items.length > 0 && (
        <ul className="canvas-list">
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className="canvas-row" onClick={() => onOpen(item.id)}>
                <Icon name="document" />
                <span className="canvas-row-title">{item.title || canvas.untitled}</span>
                <span className="canvas-row-meta">
                  {`${canvas.kinds[item.kind] ?? item.kind} · v${item.head_version} · ${timeAgo(item.updated_at, now)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
