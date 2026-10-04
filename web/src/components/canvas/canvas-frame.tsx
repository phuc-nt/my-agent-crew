/**
 * An HTML or Mermaid canvas run as the page it is, in a frame the browser keeps apart from the
 * app: `sandbox="allow-scripts"` without `allow-same-origin` gives the page an origin of its own,
 * written "null", from which it reads nothing of the app's; the policy the server sends with the
 * page says the same. The panel never posts into the frame, and takes only the reports its own
 * window makes, fifty messages of one frame at most: a page that goes on posting is not read.
 *
 * The frame shows the version it was put up with. A newer one replaces it a second after the last
 * change, unless the person has the frame's focus, who is using the page, when a button offers it
 * instead, or the tab is hidden, when it waits for the tab to come back. A page is replaced by a new
 * frame, never by a new address, which would add an entry to the history that Back walks through.
 *
 * Moving the frame to another address is not something a policy can stop. A second `load` of one
 * frame means it happened (a change of hash fires none), so the frame is taken out and the person is
 * told. That is a defence on top, not a barrier: an address can carry the page's data away before
 * it. A stopped page stays stopped until the person asks for it again.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { artifactApi } from "../../api/artifact-client";
import { useOnline } from "../../hooks/use-online";
import { useReloadOnReconnect } from "../../hooks/use-reload-on-reconnect";
import { vi } from "../../i18n/vi";
import {
  FRAME_REPORTS_MAX,
  type FrameError,
  isFromFrame,
  isLoadFailure,
  parseFrameMessage,
} from "../../lib/frame-messages";

/** How long the version must stand still before the page is put up again. */
export const RELOAD_DELAY_MS = 1000;

type Props = {
  artifactId: string;
  title: string;
  /** The newest version the server holds. */
  version: number;
  /** The activity stream is up; the page is put up again each time it comes back. */
  connected: boolean;
  /** A page of `version` was put up, or the one on show was stopped: what the one before reported is gone. */
  onMount(version: number): void;
  onError(error: FrameError): void;
};

type Page = {
  /** Tells one frame from the next. */
  n: number;
  version: number;
  phase: "loading" | "shown" | "stopped";
  /** A newer version is waiting, offered by a button because the person has the frame's focus. */
  held: boolean;
};

export function CanvasFrame({ artifactId, title, version, connected, onMount, onError }: Props) {
  const online = useOnline();
  const [page, setPage] = useState<Page>({ n: 0, version, phase: "loading", held: false });
  const frame = useRef<HTMLIFrameElement>(null);
  // How many messages each frame was heard out on. A frame that replaces another starts from none.
  const [heardOf] = useState(() => new WeakMap<HTMLIFrameElement, number>());
  const latest = useRef({ version, page, online });
  latest.current = { version, page, online };

  const mount = useCallback((next: number) => {
    setPage((was) => ({ n: was.n + 1, version: next, phase: "loading", held: false }));
  }, []);

  // Decides what a version the frame does not show yet comes to now, when a second has gone by
  // since the last change or the tab is back in sight.
  const refresh = useCallback(() => {
    const now = latest.current;
    if (now.page.phase === "stopped" || now.version === now.page.version) return;
    if (document.visibilityState === "hidden") return;
    if (document.activeElement === frame.current) setPage((was) => ({ ...was, held: true }));
    else mount(now.version);
  }, [mount]);

  // Before the page can say anything: layout effects run before the frame's first request is answered.
  const stopped = page.phase === "stopped";
  useLayoutEffect(() => {
    onMount(page.version);
  }, [page.n, stopped, onMount]);

  useEffect(() => {
    if (version === page.version) return;
    const timer = setTimeout(refresh, RELOAD_DELAY_MS);
    return () => clearTimeout(timer);
  }, [version, page.version, refresh]);

  useEffect(() => {
    const seen = () => refresh();
    document.addEventListener("visibilitychange", seen);
    return () => document.removeEventListener("visibilitychange", seen);
  }, [refresh]);

  useReloadOnReconnect(connected, () => {
    if (latest.current.page.phase !== "stopped") mount(latest.current.version);
  });

  useEffect(() => {
    const heard = (event: MessageEvent) => {
      const from = frame.current;
      // Whose message it is and whether the page may still speak are settled before any of it is
      // read. A message that is no report counts too, or a page could be read without end.
      if (!isFromFrame(event, from)) return;
      const before = heardOf.get(from) ?? 0;
      if (before >= FRAME_REPORTS_MAX) return;
      heardOf.set(from, before + 1);
      const error = parseFrameMessage(event, from);
      // With no network at all, the files a page asks for cannot arrive and there is nothing to tell.
      if (error === null || (!latest.current.online && isLoadFailure(error))) return;
      onError(error);
    };
    window.addEventListener("message", heard);
    return () => window.removeEventListener("message", heard);
  }, [onError, heardOf]);

  // The phase is the count of the frame on show: a first load shows it, a second stops it. A frame
  // being replaced stays in the page until the next one is drawn, and its load is none of the next's.
  const loaded = (n: number) =>
    setPage((was) => {
      if (was.n !== n) return was;
      return was.phase === "loading" ? { ...was, phase: "shown" } : { ...was, phase: "stopped", held: false };
    });

  return (
    <>
      {page.phase === "loading" && (
        <p className="muted canvas-frame-note" role="status">
          {vi.canvas.page.loading}
        </p>
      )}
      {page.held && (
        <button type="button" className="ghost canvas-frame-newer" onClick={() => mount(version)}>
          {vi.canvas.page.newer}
        </button>
      )}
      {page.phase === "stopped" ? (
        <div className="notice canvas-frame-note" role="status">
          <span>{vi.canvas.page.navigated}</span>
          <button type="button" className="ghost" onClick={() => mount(version)}>
            {vi.canvas.page.reload}
          </button>
        </div>
      ) : (
        <iframe
          key={page.n}
          ref={frame}
          className="canvas-frame"
          title={title}
          sandbox="allow-scripts"
          allow="fullscreen"
          referrerPolicy="no-referrer"
          src={artifactApi.renderUrl(artifactId)}
          onLoad={() => loaded(page.n)}
        />
      )}
    </>
  );
}
