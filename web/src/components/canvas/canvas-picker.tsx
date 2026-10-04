/**
 * The open conversation's canvases, the newest first, and the way to make one. The list says
 * when it is loading, empty or could not be read, and offers a retry for the last; a failed read
 * keeps the canvases an earlier one found.
 */

import { useState } from "react";
import type { CreatableKind } from "../../api/artifact-types";
import type { CanvasList } from "../../hooks/use-canvas-list";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { CREATABLE_KINDS } from "../../lib/canvas-templates";
import { timeAgo } from "../../lib/relative-time";
import { Icon } from "../ui/icon";

type Props = {
  list: Pick<CanvasList, "items" | "failed" | "retry">;
  creating: boolean;
  createFailed: boolean;
  onOpen(id: string): void;
  /** A new canvas of the kind the person chose, which starts as Markdown. */
  onCreate(kind: CreatableKind): void;
};

export function CanvasPicker({ list, creating, createFailed, onOpen, onCreate }: Props) {
  const now = useNow(60_000);
  const [kind, setKind] = useState<CreatableKind>("markdown");
  const { canvas } = vi;
  const { items } = list;
  return (
    <div className="canvas-picker">
      <div className="canvas-picker-head">
        <h2>{canvas.listTitle}</h2>
        <select
          className="canvas-kind"
          aria-label={canvas.kindLabel}
          value={kind}
          onChange={(event) => setKind(event.target.value as CreatableKind)}
          disabled={creating}
        >
          {CREATABLE_KINDS.map((each) => (
            <option key={each} value={each}>
              {canvas.kinds[each]}
            </option>
          ))}
        </select>
        <button type="button" className="primary" onClick={() => onCreate(kind)} disabled={creating}>
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
