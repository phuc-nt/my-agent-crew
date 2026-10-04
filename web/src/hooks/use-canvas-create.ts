/**
 * Making a canvas from the dock's list. The dock lends what the request must touch: its count of
 * moves, so a reply that finds the dock moved on opens nothing, and the two ways it shows the
 * request, as progress while it is out and as the canvas it opens.
 */

import { useCallback } from "react";
import { artifactApi } from "../api/artifact-client";
import type { CreatableKind, NewArtifact } from "../api/artifact-types";
import { vi } from "../i18n/vi";
import { canvasTemplate } from "../lib/canvas-templates";

type Lend = {
  conversationId: string | null;
  /** The dock's count of moves; asking for a canvas is one, and any later move cancels the reply. */
  moves: { current: number };
  /** Shows the request as out, or as failed. */
  progress(next: { creating: boolean; createFailed: boolean }): void;
  /** Opens the canvas just made, with its title ready to type over. */
  opened(id: string): void;
};

/** Asks for a canvas of `kind`, markdown unless said, in the open conversation, holding what a new
 *  canvas of that kind starts from; does nothing before a conversation is open. */
export function useCanvasCreate({ conversationId, moves, progress, opened }: Lend): (kind?: CreatableKind) => Promise<void> {
  return useCallback(async (kind: CreatableKind = "markdown") => {
    if (conversationId === null) return;
    const ticket = ++moves.current;
    progress({ creating: true, createFailed: false });
    const body: NewArtifact = {
      title: vi.canvas.untitled,
      kind,
      content: canvasTemplate(kind),
      conversation_id: conversationId,
    };
    try {
      const made = await artifactApi.create(body);
      if (moves.current === ticket) opened(made.id);
    } catch {
      if (moves.current === ticket) progress({ creating: false, createFailed: true });
    }
  }, [conversationId, moves, progress, opened]);
}
