/**
 * An HTML or Mermaid canvas run as the page it is, in a frame the browser keeps apart from the
 * app: `sandbox="allow-scripts"` without `allow-same-origin` gives the page an origin of its own,
 * written "null", from which it reads nothing of the app's; the policy the server sends with the
 * page says the same. The panel never posts into the frame. It listens: to the reports the frame's
 * own window makes, and to the port the page's reporter hands over, which says when a person
 * presses inside the page (`use-frame-messages.ts`).
 *
 * The frame shows the version it was put up with. A newer one replaces it a second after the last
 * change, unless the person has the frame's focus, who is using the page, when a button offers it
 * instead, or the tab is hidden, when it waits for the tab to come back. A page is replaced by a new
 * frame, never by a new address, which would add an entry to the history that Back walks through.
 *
 * Moving the frame to another address is not something a policy can stop. A second `load` of one
 * frame means it happened (a change of hash fires none), so the frame is taken out and the person is
 * told. That is a defence on top, not a barrier: an address can carry the page's data away before
 * it. A page that goes on taking the keyboard the person did not offer it is taken out the same
 * way (`use-frame-focus-guard.ts`). A stopped page stays stopped until the person asks for it again,
 * and then the focus, if it went with the button they pressed, is put on the box of the new frame.
 *
 * While the frame has the keyboard the box says so, in words and with a line around the page: what
 * is typed then goes to the page, and nothing else on the screen shows it.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { artifactApi } from "../../api/artifact-client";
import { useFrameFocusGuard } from "../../hooks/use-frame-focus-guard";
import { useFrameKeyboard } from "../../hooks/use-frame-keyboard";
import { useFrameMessages } from "../../hooks/use-frame-messages";
import { useReloadOnReconnect } from "../../hooks/use-reload-on-reconnect";
import { vi } from "../../i18n/vi";
import type { FrameError } from "../../lib/frame-messages";

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
  /** The page on show said as much as one page is heard out on: nothing it says from here on is read. */
  onSilenced(): void;
};

/** What a page was stopped for: it moved itself to another address, or went on taking the keyboard. */
type Stop = "navigated" | "grabbing";

type Page = {
  /** Tells one frame from the next. */
  n: number;
  version: number;
  phase: "loading" | "shown" | Stop;
  /** A newer version is waiting, offered by a button because the person has the frame's focus. */
  held: boolean;
};

const isStop = (phase: Page["phase"]): phase is Stop => phase === "navigated" || phase === "grabbing";

export function CanvasFrame({ artifactId, title, version, connected, onMount, onError, onSilenced }: Props) {
  const [page, setPage] = useState<Page>({ n: 0, version, phase: "loading", held: false });
  const frame = useRef<HTMLIFrameElement>(null);
  const latest = useRef({ version, page });
  latest.current = { version, page };
  // The person asked for a stopped page again: the button they pressed goes, and the focus with it.
  const asked = useRef(false);

  const mount = useCallback((next: number) => {
    setPage((was) => ({ n: was.n + 1, version: next, phase: "loading", held: false }));
  }, []);

  // Decides what a version the frame does not show yet comes to now, when a second has gone by
  // since the last change or the tab is back in sight.
  const refresh = useCallback(() => {
    const now = latest.current;
    if (isStop(now.page.phase) || now.version === now.page.version) return;
    if (document.visibilityState === "hidden") return;
    if (document.activeElement === frame.current) setPage((was) => ({ ...was, held: true }));
    else mount(now.version);
  }, [mount]);

  // Before the page can say anything: layout effects run before the frame's first request is answered.
  const stopped = isStop(page.phase);
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
    if (!isStop(latest.current.page.phase)) mount(latest.current.version);
  });

  const grabbing = useCallback(() => setPage((was) => ({ ...was, phase: "grabbing", held: false })), []);
  const { box, attest } = useFrameFocusGuard(frame, grabbing);
  const shown = stopped ? null : page.n;
  useFrameMessages(frame, shown, { onError, onSilenced, onPress: attest });
  const keyboard = useFrameKeyboard(frame, shown);

  useEffect(() => {
    if (!asked.current) return;
    asked.current = false;
    // In a browser whose buttons take no focus when pressed, it is still where the person had it.
    if (document.activeElement === document.body) box.current?.focus({ preventScroll: true });
  }, [page.n, box]);

  const again = () => {
    asked.current = true;
    mount(version);
  };

  // The phase is the count of the frame on show: a first load shows it, a second stops it. A frame
  // being replaced stays in the page until the next one is drawn, and its load is none of the next's.
  const loaded = (n: number) =>
    setPage((was) => {
      if (was.n !== n) return was;
      return was.phase === "loading" ? { ...was, phase: "shown" } : { ...was, phase: "navigated", held: false };
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
      {isStop(page.phase) ? (
        <div key="stopped" className="notice canvas-frame-note" role="status">
          <span>{vi.canvas.page[page.phase]}</span>
          <button type="button" className="ghost" onClick={again}>
            {vi.canvas.page.reload}
          </button>
        </div>
      ) : (
        <div key="box" ref={box} className="canvas-frame-box" tabIndex={-1} data-keyboard={keyboard ? "" : undefined}>
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
          {keyboard && (
            <p className="badge accent canvas-frame-keyboard" role="status">
              {vi.canvas.page.keyboard}
            </p>
          )}
        </div>
      )}
    </>
  );
}
