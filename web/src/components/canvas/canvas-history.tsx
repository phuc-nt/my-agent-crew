/**
 * The versions of the open canvas, in the text's place: who saved each and when, what a version
 * changed from the one before it, and the restore of an older one as the newest. The typing stays
 * with the panel's machine meanwhile, so closing the history shows it as it was.
 */

import { useMemo } from "react";
import { artifactApi } from "../../api/artifact-client";
import type { CanvasController } from "../../hooks/use-canvas";
import { type HistoryProblem, useCanvasHistory } from "../../hooks/use-canvas-history";
import { useNow } from "../../hooks/use-now";
import { vi } from "../../i18n/vi";
import { authorLabel } from "../../lib/canvas-author";
import { type CanvasDiffLine, canvasDiff } from "../../lib/canvas-diff";
import type { CanvasStatus } from "../../lib/canvas-machine";
import { formatBytes } from "../../lib/format-bytes";
import { timeAgo } from "../../lib/relative-time";
import { CanvasDiffView } from "../diff-view";
import { Icon } from "../ui/icon";
import { FullBanner, stuckReason } from "./canvas-status";

type Props = {
  canvas: CanvasController;
  artifactId: string;
  agentName(id: string): string;
  /** The dock's flush: the typing is saved before a restore. */
  flush(): Promise<number | null>;
  onClose(): void;
};

/** "Khôi phục từ v2" for a restore's note; any other note as written. */
function noteText(note: string): string {
  const restore = /^restore:(\d+)$/.exec(note);
  return restore ? vi.canvas.restoredFrom(Number(restore[1])) : note;
}

function problemText(problem: HistoryProblem, status: CanvasStatus, cap: number | null): string | null {
  const { canvas } = vi;
  if (problem.type === "versionGone") return canvas.versionGone;
  if (problem.type === "versionFailed") return canvas.versionFailed;
  if (problem.type === "restoreFailed") return canvas.restoreFailed(problem.reason);
  // The save that held the restore back may land meanwhile; the reason follows the save line.
  if (problem.type === "blocked") return status === "saved" ? null : canvas.restoreFailed(stuckReason(status, cap));
  return null;
}

export function CanvasHistory({ canvas, artifactId, agentName, flush, onClose }: Props) {
  const now = useNow(60_000);
  const history = useCanvasHistory({
    artifactId,
    headVersion: canvas.state.summary?.head_version,
    flush,
    onRestored: (version, content) => {
      canvas.restored(version, content);
      onClose();
    },
  });
  const { versions, shown, against, texts, problem } = history;
  // Undefined until a version is read; null once it is, for a picture, which has no text to compare.
  const shownText = shown ? texts.get(shown.version) : undefined;
  const againstText = against ? texts.get(against.version) : undefined;
  const picture = shownText === null;
  // The oldest version kept has nothing before it: all of its lines read as added.
  const lines = useMemo<CanvasDiffLine[] | null | undefined>(() => {
    if (typeof shownText !== "string") return undefined;
    if (against === null) return shownText.split("\n").map((text) => ({ op: "add", text }));
    return typeof againstText === "string" ? canvasDiff(againstText, shownText) : undefined;
  }, [shownText, against, againstText]);
  const said = problem ? problemText(problem, canvas.status, canvas.state.cap) : null;

  return (
    <section className="canvas-history" aria-label={vi.canvas.historyTitle}>
      <div className="canvas-history-head">
        <h3>{vi.canvas.historyTitle}</h3>
        <button type="button" className="icon-button" aria-label={vi.canvas.close} onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      {problem?.type === "full" && <FullBanner full={problem.full} />}
      {said && (
        <div className="notice error canvas-notice" role="alert">
          {said}
        </div>
      )}
      {history.listFailed && (
        <div className="notice error canvas-notice" role="alert">
          <span>{vi.canvas.historyFailed}</span>
          <button type="button" className="link-button" onClick={history.retry}>
            {vi.canvas.retry}
          </button>
        </div>
      )}
      {versions === null && !history.listFailed && <p className="muted">{vi.canvas.historyLoading}</p>}
      {versions !== null && (
        <ul className="canvas-versions">
          {versions.map((meta) => (
            <li key={meta.version}>
              <button
                type="button"
                className="canvas-version-row"
                aria-current={meta === shown ? "true" : undefined}
                onClick={() => history.pick(meta.version)}
              >
                <span>
                  {`v${meta.version} · ${authorLabel(meta.author, agentName)} · ${timeAgo(meta.updated_at, now)} · ${formatBytes(meta.size)}`}
                </span>
                {meta.note && <span className="canvas-version-note">{noteText(meta.note)}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {shown && (
        <div className="canvas-version-detail">
          {against === null ? (
            <p className="muted">{vi.canvas.firstVersion}</p>
          ) : (
            !picture && (
              <label className="canvas-compare">
                <input
                  type="checkbox"
                  checked={history.compareFirst}
                  onChange={(event) => history.setCompareFirst(event.target.checked)}
                />
                {vi.canvas.compareFirst}
              </label>
            )
          )}
          {picture && (
            <img
              className="canvas-picture"
              src={artifactApi.rawUrl(artifactId, { version: shown.version })}
              alt={vi.canvas.versionImage(shown.version)}
            />
          )}
          {lines !== undefined && <CanvasDiffView lines={lines} />}
          {shown !== versions?.[0] && (
            <button
              type="button"
              className="primary"
              disabled={history.restoring || shownText === undefined}
              onClick={() => void history.restore()}
            >
              <Icon name="refresh" />
              {vi.canvas.restore}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
