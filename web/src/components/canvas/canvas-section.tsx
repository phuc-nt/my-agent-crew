/**
 * The canvas section of the manage screen: the library of every canvas.
 *
 * A canvas left behind in a conversation hands its last save on, and the person may be here by the
 * time it fails, so this section says so as the chat does. The dock it borrows for that belongs to
 * no conversation: it reads no list, and has no message to speak of.
 */

import { useCanvasDock } from "../../hooks/use-canvas-dock";
import { CanvasChatNotices } from "./canvas-dock";
import { CanvasLibrary } from "./canvas-library";

type Props = { connected: boolean; agentName: (id: string) => string };

export function CanvasSection({ connected, agentName }: Props) {
  const dock = useCanvasDock(null, connected, false);
  return (
    <>
      <CanvasChatNotices dock={dock} />
      <CanvasLibrary connected={connected} agentName={agentName} />
    </>
  );
}
