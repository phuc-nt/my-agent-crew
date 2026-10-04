/**
 * An SVG drawing or an image as a picture: an `<img>` of the version the server holds, which the
 * browser draws without running anything in it. The same address serves the bytes of an image and
 * the text of a drawing, so the page can show what it has not been sent yet only after a save.
 *
 * A picture that does not load is told apart by asking for it again. No answer at all means the
 * network is gone, and the picture is set again when the activity stream returns. A 404 means this
 * version was folded into a newer one, so the canvas is read again and its new version replaces
 * this picture. A 200 means the picture itself is broken; for an SVG, which the server stores as
 * typed, that is also reported to the agent's list of errors, since a drawing half typed is no
 * reason for the server to refuse it.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { artifactApi } from "../../api/artifact-client";
import { useReloadOnReconnect } from "../../hooks/use-reload-on-reconnect";
import { vi } from "../../i18n/vi";
import type { FrameError } from "../../lib/frame-messages";

type Props = {
  artifactId: string;
  title: string;
  kind: string;
  /** The version drawn; a new one is a new picture, so the parent keys this by it. */
  version: number;
  connected: boolean;
  /** A picture of `version` was put up: what the one before reported is gone. */
  onMount(version: number): void;
  /** The picture is broken in a way the person can send to the agent. */
  onError(error: FrameError): void;
  /** Reads the canvas again, for a version that no longer exists. */
  onReread(): void;
};

type Look = "ok" | "waiting" | "broken";

export function CanvasImage({ artifactId, title, kind, version, connected, onMount, onError, onReread }: Props) {
  const [look, setLook] = useState<Look>("ok");
  const checks = useRef(0);
  const src = artifactApi.rawUrl(artifactId, { version });

  useLayoutEffect(() => {
    onMount(version);
  }, [version, onMount]);
  // A check still out when the picture goes away says nothing of the next one.
  useEffect(
    () => () => {
      checks.current++;
    },
    [],
  );
  // The picture is drawn anew by the render that follows: while it is not "ok" there is no `<img>`.
  useReloadOnReconnect(connected, () => {
    if (look === "waiting") setLook("ok");
  });

  const classify = async () => {
    const mine = ++checks.current;
    let next: Look = "broken";
    let invalid = false;
    try {
      const response = await fetch(src);
      void response.body?.cancel().catch(() => undefined);
      if (response.status === 404) onReread();
      else invalid = response.ok;
    } catch {
      next = "waiting";
    }
    if (checks.current !== mine) return;
    setLook(next);
    if (invalid && kind === "svg") onError({ message: vi.canvas.page.svgInvalid, source: "", line: 0, column: 0 });
  };

  if (look === "waiting") {
    return (
      <p className="muted canvas-picture-note" role="status">
        {vi.canvas.page.imageWaiting}
      </p>
    );
  }
  if (look === "broken") {
    return (
      <p className="notice canvas-picture-note" role="status">
        {vi.canvas.page.imageBroken}
      </p>
    );
  }
  return (
    <img
      className={kind === "svg" ? "canvas-picture vector" : "canvas-picture"}
      src={src}
      alt={title}
      onError={() => void classify()}
    />
  );
}
