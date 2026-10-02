/**
 * Keeps the server's idea of the open canvas in step with this tab's, in the two places a message
 * does not do it by itself. Call it after `useCanvasDock`: both read the dock's moves as the
 * conversation changes, and the dock has to count that move first.
 *
 * Coming into a conversation on a wide screen, the canvas the server has open there is read and
 * opened again, quietly. The answer may come after the person went to another conversation, or
 * opened and closed another canvas, so it opens only if the dock has not moved since the question
 * was asked. A narrow screen opens nothing by itself and asks nothing.
 *
 * Closing the canvas on a wide screen tells the server once. Opening one does not: a message
 * waiting in the queue would then name the canvas just opened instead of the one it was sent with.
 */

import { useEffect, useRef } from "react";
import { artifactApi } from "../api/artifact-client";
import type { CanvasDock } from "./use-canvas-dock";

export function useCanvasFocus(
  conversationId: string | null,
  wide: boolean,
  { focusId, ticket, restore }: Pick<CanvasDock, "focusId" | "ticket" | "restore">,
): void {
  // Only a change of conversation asks again; the width and the dock's moves must not.
  useEffect(() => {
    if (conversationId === null || !wide) return;
    const mark = ticket();
    artifactApi.getFocus(conversationId).then(
      (focus) => {
        if (focus) restore(focus.artifact_id, mark);
      },
      (error: unknown) => console.error("could not read the canvas open in this conversation", error),
    );
  }, [conversationId]);

  const was = useRef({ conversationId, focusId });
  useEffect(() => {
    const before = was.current;
    was.current = { conversationId, focusId };
    const closedHere = focusId === null && before.focusId !== null && before.conversationId === conversationId;
    if (!closedHere || conversationId === null) return;
    artifactApi.putFocus(conversationId, { artifact_id: null }).catch((error: unknown) => {
      console.error("could not tell the server the canvas was closed", error);
    });
  }, [conversationId, focusId]);
}
