/**
 * The top of a canvas panel: the name, renamed in place; the way back to the list and out; the
 * version, who saved it and when, beside the save line; and the tools. A deleted canvas keeps its
 * name to read and its text to copy, and offers nothing that needs the canvas.
 */

import { artifactApi } from "../../api/artifact-client";
import type { CanvasController } from "../../hooks/use-canvas";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { authorLabel } from "../../lib/canvas-author";
import { timeAgo } from "../../lib/relative-time";
import { CopyButton } from "../copy-button";
import { EditableTitle } from "../editable-title";
import { Icon } from "../ui/icon";
import type { CanvasPanelProps } from "./canvas-panel";
import { statusText } from "./canvas-status";

export type CanvasMode = "view" | "edit";

type Props = Pick<CanvasPanelProps, "artifactId" | "created" | "agentName" | "onShowList" | "onClose"> & {
  canvas: CanvasController;
  mode: CanvasMode | null;
  history: boolean;
  onChoose(mode: CanvasMode): void;
  onHistory(): void;
  onRename(title: string): void;
};

export function CanvasHeader({ canvas, artifactId, created, agentName, mode, history, ...on }: Props) {
  const now = useNow(60_000);
  const { state, status } = canvas;
  const { summary, gone } = state;
  return (
    <header className="canvas-header">
      <div className="canvas-title-row">
        {gone ? (
          <h2 className="title-heading">{summary?.title || vi.canvas.untitled}</h2>
        ) : (
          summary && (
            <EditableTitle
              level={2}
              maxLength={200}
              label={vi.canvas.rename}
              hint={vi.canvas.renameHint}
              placeholder={vi.canvas.untitled}
              startEditing={created}
              title={summary.title}
              onRename={on.onRename}
            />
          )
        )}
        <button type="button" className="icon-button" aria-label={vi.canvas.toList} title={vi.canvas.toList} onClick={on.onShowList}>
          <Icon name="grid" />
        </button>
        <button type="button" className="icon-button" aria-label={vi.canvas.close} title={vi.canvas.close} onClick={on.onClose}>
          <Icon name="close" />
        </button>
      </div>
      {state.phase === "ready" && summary && (
        <p className="canvas-meta">
          <span className="canvas-version">
            {vi.canvas.meta(state.base.version, authorLabel(state.base.author, agentName), timeAgo(summary.updated_at, now))}
          </span>
          <span className="canvas-save-state" role="status">
            {statusText(status, state.cap)}
          </span>
        </p>
      )}
      <div className="canvas-toolbar">
        <div className="segmented" role="group" aria-label={vi.canvas.mode}>
          {(["view", "edit"] as const).map((each) => (
            <button key={each} type="button" aria-pressed={mode === each} onClick={() => on.onChoose(each)}>
              {vi.canvas[each]}
            </button>
          ))}
        </div>
        {!gone && (
          <button type="button" className="ghost" aria-expanded={history} onClick={on.onHistory}>
            <Icon name="clock" />
            {vi.canvas.history}
          </button>
        )}
        <CopyButton text={state.text} label={vi.canvas.copy} />
        {!gone && (
          <a className="canvas-download" href={artifactApi.rawUrl(artifactId, { download: true })} download>
            <Icon name="download" />
            {vi.canvas.download}
          </a>
        )}
      </div>
    </header>
  );
}
