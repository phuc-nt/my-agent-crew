/**
 * The top of a canvas panel: the name, renamed in place; the way back to the list and out; the
 * version, who saved it and when, beside the save line; and the tools. A deleted canvas keeps its
 * name to read and its text to copy, and offers nothing that needs the canvas.
 */

import { useId } from "react";
import { artifactApi } from "../../api/artifact-client";
import type { CanvasController } from "../../hooks/use-canvas";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { authorLabel } from "../../lib/canvas-author";
import { hasNoText, showsPage } from "../../lib/canvas-kinds";
import { isDirty } from "../../lib/canvas-state";
import { timeAgo } from "../../lib/relative-time";
import { CopyButton } from "../copy-button";
import { EditableTitle } from "../editable-title";
import { Icon } from "../ui/icon";
import type { CanvasPanelProps } from "./canvas-panel";
import { statusText } from "./canvas-status";

export type CanvasMode = "view" | "edit";

type Shared = "artifactId" | "created" | "agentName" | "standaloneHref" | "onShowList" | "onClose";

type Props = Pick<CanvasPanelProps, Shared> & {
  canvas: CanvasController;
  mode: CanvasMode | null;
  /** A turn to View is waiting for the canvas to be saved. */
  switching: boolean;
  history: boolean;
  onChoose(mode: CanvasMode): void;
  onHistory(): void;
  onRename(title: string): void;
};

export function CanvasHeader({ canvas, artifactId, created, agentName, standaloneHref, mode, switching, history, ...on }: Props) {
  const now = useNow(60_000);
  const whyNotOwnPage = useId();
  const { state, status } = canvas;
  const { summary, gone } = state;
  const kind = summary?.kind ?? "markdown";
  const modes = hasNoText(kind) ? (["view"] as const) : (["view", "edit"] as const);
  const unsaved = isDirty(state);
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
          {modes.map((each) => {
            const busy = switching && each === "view";
            return (
              <button key={each} type="button" aria-pressed={mode === each} aria-busy={busy || undefined} onClick={() => on.onChoose(each)}>
                {busy ? vi.canvas.status.saving : vi.canvas[each]}
              </button>
            );
          })}
        </div>
        {!gone && (
          <button type="button" className="ghost" aria-expanded={history} onClick={on.onHistory}>
            <Icon name="clock" />
            {vi.canvas.history}
          </button>
        )}
        {state.phase === "ready" && !gone && showsPage(kind) && (
          <button
            type="button"
            className="ghost"
            // Only text that is saved is on the server to open, and the opening happens in this click.
            disabled={unsaved}
            onClick={() => window.open(artifactApi.renderUrl(artifactId), "_blank", "noopener,noreferrer")}
          >
            <Icon name="arrow-right" />
            {vi.canvas.page.open}
          </button>
        )}
        {state.phase === "ready" && !gone && standaloneHref !== undefined && (
          <>
            <button
              type="button"
              className="ghost"
              // The page that opens reads the canvas from the server: words not yet saved would not be
              // on it. aria-disabled rather than disabled: the keyboard still reaches the button, and
              // there the reason is said.
              aria-disabled={unsaved}
              aria-describedby={unsaved ? whyNotOwnPage : undefined}
              title={unsaved ? vi.canvas.standaloneUnsaved : undefined}
              onClick={() => {
                if (!unsaved) window.open(standaloneHref, "_blank", "noopener,noreferrer");
              }}
            >
              <Icon name="document" />
              {vi.canvas.openStandalone}
            </button>
            {unsaved && (
              <span id={whyNotOwnPage} className="sr-only">
                {vi.canvas.standaloneUnsaved}
              </span>
            )}
          </>
        )}
        {!hasNoText(kind) && <CopyButton text={state.text} label={vi.canvas.copy} />}
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
