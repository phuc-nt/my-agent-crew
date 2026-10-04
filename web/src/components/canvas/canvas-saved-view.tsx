/**
 * The view of a canvas whose kind is shown as what the server holds: an HTML or Mermaid page in a
 * frame, an SVG or an image as a picture. Neither can show text the person has typed and not yet
 * saved, so the panel saves before turning here and says so when some text is still not in the
 * version on show.
 *
 * What the page or the picture reports goes to one list, which the person can read and send to the
 * agent. An image has nothing the agent could mend, so it reports nothing and its list stays empty.
 */

import type { MessageCanvas } from "../../api/artifact-types";
import type { CanvasController } from "../../hooks/use-canvas";
import { usePageReport } from "../../hooks/use-page-report";
import { vi } from "../../i18n/vi";
import { showsPage } from "../../lib/canvas-kinds";
import { isDirty } from "../../lib/canvas-state";
import type { SendResult } from "../../lib/send-result";
import type { AskDisabled } from "./canvas-ask";
import { CanvasErrors } from "./canvas-errors";
import { CanvasFrame } from "./canvas-frame";
import { CanvasImage } from "./canvas-image";

type Props = {
  canvas: CanvasController;
  artifactId: string;
  kind: string;
  connected: boolean;
  askDisabled: AskDisabled;
  flush(): Promise<number | null>;
  onAsk?(canvas: MessageCanvas, question: string): Promise<SendResult>;
};

export function CanvasSavedView({ canvas, artifactId, kind, connected, askDisabled, flush, onAsk }: Props) {
  const { state } = canvas;
  const { version } = state.base;
  const title = state.summary?.title || vi.canvas.untitled;
  const { report, add, reset } = usePageReport(version);
  return (
    <div className="canvas-saved">
      {isDirty(state) && (
        <p className="canvas-saved-note" role="status">
          {vi.canvas.page.savedVersion(version)}
        </p>
      )}
      {showsPage(kind) ? (
        <CanvasFrame artifactId={artifactId} title={title} version={version} connected={connected} onMount={reset} onError={add} />
      ) : (
        <CanvasImage
          // Named apart from the list below: both are counted from one, and two children of one
          // element must not share a key.
          key={`picture-${version}`}
          artifactId={artifactId}
          title={title}
          kind={kind}
          version={version}
          connected={connected}
          onMount={reset}
          onError={add}
          onReread={canvas.reload}
        />
      )}
      <CanvasErrors
        key={`report-${report.mount}`}
        artifactId={artifactId}
        title={title}
        report={report}
        disabled={askDisabled}
        flush={flush}
        onAsk={onAsk}
      />
    </div>
  );
}
