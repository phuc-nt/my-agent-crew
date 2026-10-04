/**
 * The canvas section of the manage screen: the library of every canvas, or the page of the one the
 * address names.
 *
 * A canvas left behind, in a conversation or on its page here, hands its last save on, and the
 * person may be anywhere in this section by the time it fails, so the section says so above
 * whatever it shows, as the chat does. The dock it borrows for that belongs to no conversation: it
 * reads no list, and has no message to speak of.
 */

import type { Conversation } from "../../api/types";
import { useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { isArtifactId } from "../../lib/artifact-tag";
import { ErrorBoundary } from "../error-boundary";
import { CanvasChatNotices } from "./canvas-dock";
import { CanvasLibrary } from "./canvas-library";
import { CanvasPage } from "./canvas-page";

type Props = {
  connected: boolean;
  agentName: (id: string) => string;
  /** What the address names after the section; anyone can type one, so it is not yet an id. */
  canvasId?: string;
  /** Rewrites the address to name a canvas, or none for the library. */
  onOpenCanvas(id: string | null): void;
  conversations: Conversation[];
  onOpenConversation(id: string): void;
};

export function CanvasSection({ connected, agentName, canvasId, onOpenCanvas, conversations, onOpenConversation }: Props) {
  const dock = useCanvasDock(null, connected, false);
  const back = () => onOpenCanvas(null);
  // Only what the server could have named is ever asked of it; anything else shows the library.
  const id = canvasId !== undefined && isArtifactId(canvasId) ? canvasId : null;
  return (
    <>
      <CanvasChatNotices dock={dock} />
      {id === null ? (
        <CanvasLibrary connected={connected} agentName={agentName} onOpen={onOpenCanvas} />
      ) : (
        <>
          {/* Outside the boundary below: a page that breaks leaves the way back standing. */}
          <button type="button" className="link-button canvas-back" onClick={back}>
            {vi.canvas.back}
          </button>
          <ErrorBoundary key={id}>
            <CanvasPage
              id={id}
              connected={connected}
              dock={dock}
              agentName={agentName}
              conversations={conversations}
              onBack={back}
              onOpenConversation={onOpenConversation}
            />
          </ErrorBoundary>
        </>
      )}
    </>
  );
}
