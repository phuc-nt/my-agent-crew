/**
 * What the panel says about its canvas: the status beside the version line, and the notices above
 * the text. Every reason is chosen here by the status, in the app's own words: the server's text,
 * and a 409's content, never show through these.
 */

import { useMemo } from "react";
import type { StorageFull } from "../../api/artifact-types";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import { SMALLEST_CAP } from "../../lib/canvas-caps";
import type { CanvasStatus } from "../../lib/canvas-machine";
import { formatBytes } from "../../lib/format-bytes";
import { hasHiddenChars } from "../../lib/hidden-chars";

/** What a "too large" stop was held to, said in the size the person reads. */
const limitText = (cap: number | null) => formatBytes(cap ?? SMALLEST_CAP);

/** The status beside the version line. `cap` is what a "too large" stop was held to. */
export function statusText(status: CanvasStatus, cap: number | null = null): string {
  const { canvas } = vi;
  if (status === "loading") return canvas.loading;
  if (status === "loadFailed") return canvas.loadFailed;
  if (status === "gone") return canvas.gone;
  if (status === "tooLarge") return canvas.notSaved(canvas.reasons.tooLarge(limitText(cap)));
  if (status === "full" || status === "invalid") return canvas.notSaved(canvas.reasons[status]);
  return canvas.status[status];
}

/** Why no version holds the text, said after "Chưa lưu được:" or "Không khôi phục được:". */
export function stuckReason(status: CanvasStatus, cap: number | null = null): string {
  const { reasons } = vi.canvas;
  if (status === "conflict") return reasons.conflict;
  if (status === "tooLarge") return reasons.tooLarge(limitText(cap));
  if (status === "full" || status === "invalid") return reasons[status];
  if (status === "offline") return reasons.offline;
  if (status === "serverDown") return reasons.server;
  if (status === "slow") return reasons.slow;
  if (status === "gone") return reasons.gone;
  return reasons.timeout;
}

/** The server has no room for canvases: the largest ones show where room could be made. */
export function FullBanner({ full, hint }: { full: StorageFull; hint?: string }) {
  return (
    <div className="notice error canvas-notice" role="alert">
      <p>{vi.canvas.fullTitle}</p>
      <ul className="canvas-largest">
        {full.largest.map((item) => (
          <li key={item.id}>{`${item.title || vi.canvas.untitled} · ${formatBytes(item.size)}`}</li>
        ))}
      </ul>
      {hint && <p>{hint}</p>}
    </div>
  );
}

type Props = {
  canvas: CanvasController;
  /** Leaving was asked for and no save landed. */
  stuck: boolean;
  onForceClose(): void;
};

/** The notices above the text, the most pressing first. */
export function CanvasNotices({ canvas, stuck, onForceClose }: Props) {
  const { state, status, draftFailed } = canvas;
  const hidden = useMemo(() => hasHiddenChars(state.text), [state.text]);
  const reopened = state.opened === "draft" || state.opened === "merged";
  return (
    <>
      {status === "loadFailed" && (
        <div className="notice error canvas-notice" role="alert">
          <span>{vi.canvas.loadFailed}</span>
          <button type="button" className="link-button" onClick={canvas.reload}>
            {vi.canvas.retry}
          </button>
        </div>
      )}
      {state.stop === "full" && state.full && <FullBanner full={state.full} hint={vi.canvas.fullHint} />}
      {state.gone && (
        <div className="notice warn canvas-notice" role="alert">
          <strong>{vi.canvas.gone}</strong> <span>{vi.canvas.goneHint}</span>
        </div>
      )}
      {stuck && status !== "saved" && (
        <div className="notice error canvas-notice" role="alert">
          <span>{vi.canvas.stuck(stuckReason(status, state.cap))}</span>
          <button type="button" className="link-button" onClick={onForceClose}>
            {draftFailed ? vi.canvas.closeAnywayLoses : vi.canvas.closeAnyway}
          </button>
        </div>
      )}
      {draftFailed && (
        <div className="notice warn canvas-notice" role="alert">
          {vi.canvas.draftFailed}
        </div>
      )}
      {reopened && status !== "saved" && (
        <div className="notice canvas-notice info" role="status">
          {state.opened === "merged" ? vi.canvas.merged : vi.canvas.draftOpened}
        </div>
      )}
      {hidden && (
        <div className="notice warn canvas-notice" role="note">
          <strong>{vi.canvas.hiddenChars}</strong> <span>{vi.canvas.hiddenCharsHint}</span>
        </div>
      )}
    </>
  );
}
