/**
 * Making a canvas from the dock's list. The dock lends what the request must touch: its count of
 * moves, so a reply that finds the dock moved on opens nothing, and the two ways it shows the
 * request, as progress while it is out and as the canvas it opens.
 */

import { useCallback } from "react";
import { artifactApi } from "../api/artifact-client";
import { vi } from "../i18n/vi";

type Lend = {
  conversationId: string | null;
  /** The dock's count of moves; asking for a canvas is one, and any later move cancels the reply. */
  moves: { current: number };
  /** Shows the request as out, or as failed. */
  progress(next: { creating: boolean; createFailed: boolean }): void;
  /** Opens the canvas just made, with its title ready to type over. */
  opened(id: string): void;
};

/** Asks for an empty canvas in the open conversation; does nothing before one is open. */
export function useCanvasCreate({ conversationId, moves, progress, opened }: Lend): () => Promise<void> {
  return useCallback(async () => {
    if (conversationId === null) return;
    const ticket = ++moves.current;
    progress({ creating: true, createFailed: false });
    const body = { title: vi.canvas.untitled, kind: "markdown", content: "", conversation_id: conversationId } as const;
    try {
      const made = await artifactApi.create(body);
      if (moves.current === ticket) opened(made.id);
    } catch {
      if (moves.current === ticket) progress({ creating: false, createFailed: true });
    }
  }, [conversationId, moves, progress, opened]);
}
